"""Portable contracts behind Windows relocation; real Windows CI tests rename."""

import pytest

from contextopus.core import relocation


@pytest.mark.parametrize(
    "path",
    [
        ".pcw/.rag/lock",
        ".pcw/.control/project/lock",
        ".pcw/project/.pcw-runtime/lock",
        "core/rag/lock",
        "modules/workspace/control/project/lock",
    ],
)
def test_only_named_advisory_lock_paths_are_runtime_state(path):
    assert relocation._runtime_lock(path)


@pytest.mark.parametrize(
    "path",
    [
        ".pcw/project/knowledge/lock",
        ".pcw/project/knowledge/lock.md",
        "modules/workspace/control/project/lock.md",
        "project/lock",
    ],
)
def test_authoring_files_named_lock_remain_revision_bound(path):
    assert not relocation._runtime_lock(path)


def test_windows_seed_byte_is_not_authoring_revision_change(tmp_path, monkeypatch):
    # Exercise Windows inventory semantics on every platform. Actual Windows
    # exercises the same nested-handle closing protocol before directory rename.
    monkeypatch.setattr(relocation, "_WINDOWS", True)
    source = tmp_path / "old"
    source.mkdir()
    destination = tmp_path / "new"
    lock = source / ".pcw/.control/alpha/lock"
    lock.parent.mkdir(parents=True)
    lock.touch()
    authoring = source / ".pcw/alpha/knowledge/topic.md"
    authoring.parent.mkdir(parents=True)
    body = "# Knowledge\nExact durable content\n".encode()
    authoring.write_bytes(body)
    proposal = relocation.plan(source, destination)
    assert ".pcw/.control/alpha/lock" not in {
        entry["path"] for entry in proposal["files"]
    }
    lock.write_bytes(b"\0")
    result = relocation.apply(proposal)
    assert result["status"] == "complete"
    assert (
        destination / "modules/workspace/workspace_contexts/alpha/knowledge/topic.md"
    ).read_bytes() == body
    retained = source / ".contextopus-retained" / proposal["revision"] / ".pcw"
    assert (retained / ".control/alpha/lock").read_bytes() == b"\0"
    assert relocation.apply(proposal)["status"] == "complete"


def test_windows_lock_exclusion_does_not_hide_authoring_edit(tmp_path, monkeypatch):
    monkeypatch.setattr(relocation, "_WINDOWS", True)
    source = tmp_path / "old"
    source.mkdir()
    destination = tmp_path / "new"
    authoring = source / ".pcw/alpha/knowledge/lock"
    authoring.parent.mkdir(parents=True)
    authoring.write_bytes(b"Original")
    proposal = relocation.plan(source, destination)
    authoring.write_bytes(b"Edited")
    with pytest.raises(ValueError, match="Source changed"):
        relocation.apply(proposal)
    assert not (source / ".contextopus-freeze.json").exists()


@pytest.mark.skipif(__import__("os").name == "nt", reason="POSIX access modes")
def test_private_source_root_mode_is_preserved_and_revision_bound(tmp_path):
    import stat

    source = tmp_path / "old"
    source.mkdir(mode=0o700)
    (source / "data").write_bytes(b"Preserved")
    destination = tmp_path / "new"
    proposal = relocation.plan(source, destination)
    assert proposal["source_mode"] == 0o700
    source.chmod(0o750)
    with pytest.raises(ValueError, match="Source root mode changed"):
        relocation.apply(proposal)
    assert not (source / ".contextopus-freeze.json").exists()
    source.chmod(0o700)
    relocation.apply(proposal)
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700


@pytest.mark.skipif(__import__("os").name == "nt", reason="POSIX access modes")
def test_private_mode_preserved_for_retry_of_pre_mode_plan(tmp_path, monkeypatch):
    import stat

    source = tmp_path / "old"
    source.mkdir(mode=0o700)
    (source / "data").write_bytes(b"Preserved")
    destination = tmp_path / "new"
    proposal = relocation.plan(source, destination)
    proposal.pop("source_mode")
    proposal["revision"] = relocation._revision(proposal)
    original = relocation.shutil.copy2

    def interrupted(*args, **kwargs):
        assert stat.S_IMODE(destination.stat().st_mode) == 0o700
        raise OSError("interrupted copy")

    monkeypatch.setattr(relocation.shutil, "copy2", interrupted)
    with pytest.raises(OSError, match="interrupted copy"):
        relocation.apply(proposal)
    monkeypatch.setattr(relocation.shutil, "copy2", original)
    assert relocation.apply(proposal)["status"] == "complete"
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700


def test_windows_close_to_rename_keeps_root_guard_against_supported_writer(
    tmp_path, monkeypatch
):
    import os
    from pathlib import Path
    import subprocess
    import sys
    import time

    monkeypatch.setattr(relocation, "_WINDOWS", True)
    source = tmp_path / "old"
    source.mkdir()
    lock = source / ".pcw/.control/alpha/lock"
    lock.parent.mkdir(parents=True)
    lock.write_bytes(b"\0")
    document = source / ".pcw/alpha/knowledge/topic.md"
    document.parent.mkdir(parents=True)
    document.write_bytes(b"Preserved")
    destination = tmp_path / "new"
    attempt, unsafe, outcome = [
        tmp_path / name for name in ("attempt", "unsafe-write", "outcome")
    ]
    proposal = relocation.plan(source, destination)
    original_replace = relocation.os.replace
    children = []
    repo = Path(__file__).resolve().parents[1]
    code = """
import sys
from pathlib import Path
from contextopus.core.storage import StorageLayout
source, attempt, unsafe, outcome = map(Path, sys.argv[1:])
attempt.write_text("attempting")
try:
    with StorageLayout(source).guard():
        unsafe.write_text("unexpected write")
except RuntimeError as exc:
    outcome.write_text(str(exc))
"""

    def paused_replace(old, new):
        if Path(old) == source / ".pcw":
            assert (source / ".contextopus-freeze.json").is_file()
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    code,
                    str(source),
                    str(attempt),
                    str(unsafe),
                    str(outcome),
                ],
                env={**os.environ, "PYTHONPATH": str(repo / "src")},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            children.append(child)
            deadline = time.monotonic() + 10
            while (
                not attempt.exists()
                and child.poll() is None
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            assert attempt.exists(), (
                "Competing writer never reached its root-guard attempt"
            )
            # The competitor is alive inside the guard acquisition, not merely
            # absent because process startup has not reached the relevant code.
            time.sleep(0.2)
            assert child.poll() is None
            assert not unsafe.exists()
            assert not outcome.exists()
        return original_replace(old, new)

    monkeypatch.setattr(relocation.os, "replace", paused_replace)
    try:
        assert relocation.apply(proposal)["status"] == "complete"
        assert len(children) == 1
        stdout, stderr = children[0].communicate(timeout=10)
        assert children[0].returncode == 0, (stdout, stderr)
        assert "frozen" in outcome.read_text().lower()
        assert not unsafe.exists()
        assert (
            destination
            / "modules/workspace/workspace_contexts/alpha/knowledge/topic.md"
        ).read_bytes() == b"Preserved"
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)


def test_active_mcp_owner_lock_is_never_read_or_copied(tmp_path, monkeypatch):
    from pathlib import Path

    source = tmp_path / "old"
    runtime = source / "runtime"
    runtime.mkdir(parents=True)
    owner_lock = runtime / "mcp-owner.lock"
    owner_lock.write_bytes(b"\0")
    (source / "knowledge.md").write_bytes(b"Permanent content")
    original = Path.open

    def deny_owner_lock(self, *args, **kwargs):
        # Windows denies reads of the byte held by the running MCP owner.
        if self == owner_lock:
            raise PermissionError("active Windows owner lock")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_owner_lock)
    proposal = relocation.plan(source, tmp_path / "new")
    assert "runtime/mcp-owner.lock" not in {entry["path"] for entry in proposal["files"]}
    result = relocation.apply(proposal)
    assert result["status"] == "complete"
    assert not (tmp_path / "new/runtime/mcp-owner.lock").exists()
    assert (tmp_path / "new/knowledge.md").read_bytes() == b"Permanent content"

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
    # exercises the real delete-sharing handle in the relocation integration tests.
    monkeypatch.setattr(relocation, "_WINDOWS", True)
    if __import__("os").name != "nt":
        monkeypatch.setattr(
            relocation, "_legacy_lock_stream", lambda path: path.open("a+b")
        )
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

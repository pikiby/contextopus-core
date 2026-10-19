"""Bounded public relocation reviews retain exact durable manifests."""

import json
from unittest.mock import patch

import pytest

from contextopus.core import relocation
from contextopus.startup import Application


def source_tree(tmp_path):
    source = tmp_path / "source"
    path = source / ".pcw/alpha/knowledge/topic.md"
    path.parent.mkdir(parents=True)
    path.write_text("original bytes")
    return source, tmp_path / "destination"


def test_large_manifest_review_is_bounded_and_handle_survives_application_restart(
    tmp_path,
):
    source, destination = source_tree(tmp_path)
    original = relocation.plan

    def large_manifest(*args):
        value = original(*args)
        value["files"][0]["review_metadata"] = "x" * (6 * 1024 * 1024)
        value["revision"] = relocation._revision(value)
        return value

    with Application(source, discover=False) as app:
        with patch.object(relocation, "plan", side_effect=large_manifest):
            review = app.query(
                "core.relocation_plan", {"destination": str(destination)}
            )
        assert len(json.dumps(review)) < 4096
        assert review["manifest"]["bytes"] > 6 * 1024 * 1024
        assert review["files"] >= 1
        assert review["contexts"] == ["alpha"]
        assert review["effects"]["initializes_missing_instructions"] is False
    with Application(source, discover=False) as restarted:
        result = restarted.execute(
            "core.relocation_apply", {"plan_revision": review["revision"]}
        )
        assert result["status"] == "complete"
    assert (
        destination / "modules/workspace/workspace_contexts/alpha/knowledge/topic.md"
    ).read_text() == "original bytes"


def test_partial_freeze_retry_uses_owned_plan_after_restart(tmp_path):
    source, destination = source_tree(tmp_path)
    with Application(source, discover=False) as app:
        review = app.query("core.relocation_plan", {"destination": str(destination)})
        with patch.object(
            relocation.shutil, "copy2", side_effect=OSError("interrupted")
        ):
            with pytest.raises(OSError):
                app.execute(
                    "core.relocation_apply", {"plan_revision": review["revision"]}
                )
    assert (source / ".contextopus-freeze.json").is_file()
    with Application(source, discover=False) as restarted:
        resumed = restarted.query(
            "core.relocation_plan", {"destination": str(destination)}
        )
        assert resumed == review
        assert (
            restarted.execute(
                "core.relocation_apply", {"plan_revision": review["revision"]}
            )["status"]
            == "complete"
        )


def test_tampered_owned_artifact_and_foreign_handle_are_rejected(tmp_path):
    source, destination = source_tree(tmp_path)
    with Application(source, discover=False) as app:
        review = app.query("core.relocation_plan", {"destination": str(destination)})
        artifact = __import__("pathlib").Path(review["manifest"]["path"])
        value = json.loads(artifact.read_text())
        value["destination"] = str(tmp_path / "unexpected")
        artifact.write_text(json.dumps(value))
        with pytest.raises(ValueError, match="revision"):
            app.execute("core.relocation_apply", {"plan_revision": review["revision"]})
        with pytest.raises(ValueError, match="revision"):
            app.execute("core.relocation_apply", {"plan_revision": "../outside"})
    assert (source / ".pcw").is_dir()
    assert not destination.exists()


def test_permanent_source_change_stales_review_but_observer_query_does_not(tmp_path):
    source, destination = source_tree(tmp_path)
    with Application(source, discover=False) as app:
        review = app.query("core.relocation_plan", {"destination": str(destination)})
        app.query("core.doctor")
        assert (
            app.query("core.relocation_plan", {"destination": str(destination)})
            == review
        )
        (source / ".pcw/alpha/knowledge/topic.md").write_text("changed source")
        with pytest.raises(ValueError, match="Source changed"):
            app.execute("core.relocation_apply", {"plan_revision": review["revision"]})


def test_open_layout_unicode_review_survives_owned_artifact_reload(tmp_path):
    source = tmp_path / "исходный-корень"
    document = source / "modules/workspace/workspace_contexts/проект/knowledge/тема.md"
    document.parent.mkdir(parents=True)
    document.write_text("Исходный текст", encoding="utf-8")
    destination = tmp_path / "новое-место"
    with Application(source, discover=False) as app:
        review = app.query("core.relocation_plan", {"destination": str(destination)})
        assert review["contexts"] == ["проект"]
        assert review["context_count"] == 1
    with Application(source, discover=False) as restarted:
        assert (
            restarted.execute(
                "core.relocation_apply", {"plan_revision": review["revision"]}
            )["status"]
            == "complete"
        )
    assert (
        destination / "modules/workspace/workspace_contexts/проект/knowledge/тема.md"
    ).read_text(encoding="utf-8") == "Исходный текст"


def test_relocation_preserves_unfinished_temporary_cards_and_pending_proposals(tmp_path):
    source, destination = source_tree(tmp_path)
    relative = 'alpha/.tmp/unfinished'
    files = {
        f'{relative}/materials/Readable finding.md': '---\nid: stable-card\ntype: knowledge\nlinks: []\n---\n# Unfinished evidence\n',
        f'{relative}/proposals/pending.json': '{"revision": "exact pending proposal"}\n',
    }
    for name, content in files.items():
        path = source / '.pcw' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    with Application(source, discover=False) as app:
        review = app.query('core.relocation_plan', {'destination': str(destination)})
        assert app.execute('core.relocation_apply', {'plan_revision': review['revision']})['status'] == 'complete'
    for name, content in files.items():
        assert (destination / 'modules/workspace/workspace_contexts' / name).read_text() == content


def test_module_files_are_snapshotted_after_cross_process_writer_drains(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import contextmanager
    from pathlib import Path
    import os
    import sqlite3
    import subprocess
    import sys
    import threading
    import time

    from contextopus.core.module_storage import ModuleStorage
    from contextopus.core.storage import StorageLayout

    source, destination = source_tree(tmp_path)
    storage = ModuleStorage(StorageLayout(source))
    package = tmp_path / "package"
    (package / "migrations").mkdir(parents=True)
    (package / "migrations/001-schema.sql").write_text(
        'CREATE TABLE "{{module}}::items" (value TEXT);'
    )
    contract = {"engine": "sqlite", "schema_version": 1, "migrations": "migrations",
                "compatible_versions": {"min": 1, "max": 1}}
    for module in ("alpha", "beta"):
        review = storage.prepare(module, contract, package)
        storage.apply(module, contract, package, review["revision"])
        storage.execute(module, 'INSERT INTO "{{module}}::items" VALUES (?)', [module])
    staging = storage.path / ".partition-abandoned-alpha.sqlite3"
    staging.write_bytes(b"incomplete disposable staging")
    backup = source / "core/storage/.backups/modules.sqlite3.pre-partition-example"
    backup.parent.mkdir()
    backup.write_bytes(b"durable recovery evidence")
    proposal = relocation.plan(source, destination)
    manifest = {entry["path"] for entry in proposal["files"]}
    assert "core/storage/modules/alpha.sqlite3" in manifest
    assert "core/storage/modules/beta.sqlite3" in manifest
    assert not any(name.endswith(".sqlite3.lock") or "/.partition-" in name for name in manifest)
    assert backup.relative_to(source).as_posix() in manifest
    ready, release, outcome = [tmp_path / name for name in ("writer-ready", "release", "outcome")]
    code = '''
import sys, time
from pathlib import Path
from contextopus.core.storage import StorageLayout
from contextopus.core.module_storage import ModuleStorage
root, ready, release, outcome = map(Path, sys.argv[1:])
storage = ModuleStorage(StorageLayout(root)).for_module("alpha")
with storage._write_guard():
    with storage._connection(write=True) as database:
        database.execute("BEGIN IMMEDIATE")
        ready.touch()
        deadline = time.monotonic() + 10
        while not release.exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("Test release signal absent")
            time.sleep(.01)
        database.execute("ROLLBACK")
try:
    storage.execute("alpha", 'INSERT INTO "{{module}}::items" VALUES (?)', ["unsafe"])
except RuntimeError as error:
    outcome.write_text(str(error))
else:
    outcome.write_text("unsafe write succeeded")
'''
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(source), str(ready), str(release), str(outcome)],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    quiescing, verifying = threading.Event(), threading.Event()
    quiesce, verify = relocation.quiesce_module_writes, relocation._verify_source

    @contextmanager
    def observe_quiesce(*args, **kwargs):
        quiescing.set()
        with quiesce(*args, **kwargs):
            yield

    def observe_verify(*args, **kwargs):
        verifying.set()
        return verify(*args, **kwargs)

    monkeypatch.setattr(relocation, "quiesce_module_writes", observe_quiesce)
    monkeypatch.setattr(relocation, "_verify_source", observe_verify)
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.01)
        assert ready.exists(), process.communicate(timeout=1) if process.poll() is not None else "Writer not ready"
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(relocation.apply, proposal)
            try:
                assert quiescing.wait(3)
                assert not verifying.wait(.1)
                assert not (source / ".contextopus-freeze.json").exists()
            finally:
                release.touch()
            assert result.result(timeout=5)["status"] == "complete"
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 0, (stdout, stderr)
        assert "frozen" in outcome.read_text().lower()
        for module in ("alpha", "beta"):
            relative = f"core/storage/modules/{module}.sqlite3"
            assert (source / relative).is_file()
            assert (destination / ".backups/relocations" / proposal["snapshot_id"] / relative).is_file()
            with sqlite3.connect(destination / relative) as database:
                assert database.execute(f'SELECT value FROM "{module}::items"').fetchall() == [(module,)]
        assert (destination / backup.relative_to(source)).read_bytes() == backup.read_bytes()
        assert not (destination / staging.relative_to(source)).exists()
    finally:
        release.touch()
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=5)

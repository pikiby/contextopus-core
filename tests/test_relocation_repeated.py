"""Repeated relocation retains opaque historical snapshots and current SQLite data."""

from contextlib import closing
import json
from pathlib import Path
import sqlite3

import pytest

from contextopus.core import relocation
from contextopus.core.relocation_snapshots import snapshot_target


DATABASE = "core/storage/modules/alpha.sqlite3"


def database_root(path):
    database = path / DATABASE
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, body TEXT)")
        connection.execute("INSERT INTO items VALUES (1, 'original')")
    return path


def rows(path):
    with closing(sqlite3.connect(path)) as database:
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        return database.execute("SELECT id,body FROM items ORDER BY id").fetchall()


def archive_bytes(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for directory in (root / ".backups/relocations", root / "core/relocation/raw")
            if directory.exists() for path in directory.rglob("*") if path.is_file()}


def legacy_plan(source, destination):
    """Construct persisted v1 coordinates without changing old receipt rules."""
    proposal = relocation.plan(source, destination)
    identity = proposal.pop("snapshot_id")
    proposal["version"] = 1
    for entry in proposal["files"]:
        if entry["target"] == snapshot_target(entry["path"], identity):
            entry["target"] = snapshot_target(entry["path"])
    proposal["revision"] = relocation._revision(proposal)
    return proposal


def test_repeated_relocation_after_sqlite_edit_preserves_each_snapshot(tmp_path):
    first = database_root(tmp_path / "a")
    second, third = tmp_path / "b", tmp_path / "c"
    initial = relocation.plan(first, second)
    relocation.apply(initial)
    previous = archive_bytes(second)
    with sqlite3.connect(second / DATABASE) as database:
        database.execute("INSERT INTO items VALUES (2, 'edited at b')")
    repeated = relocation.plan(second, third)
    assert relocation.apply(repeated)["status"] == "complete"
    assert rows(third / DATABASE) == [(1, "original"), (2, "edited at b")]
    assert initial["snapshot_id"] != repeated["snapshot_id"]
    assert all((third / name).read_bytes() == content for name, content in previous.items())
    fresh = third / ".backups/relocations" / repeated["snapshot_id"] / DATABASE
    assert fresh.read_bytes() == (second / DATABASE).read_bytes()
    assert rows(fresh) == [(1, "original"), (2, "edited at b")]
    assert rows(first / DATABASE) == [(1, "original")]


def test_preview_identity_is_stable_without_writes_and_ignores_observer_changes(tmp_path):
    source = database_root(tmp_path / "source")
    observer = source / "core/analytics/query.log"
    observer.parent.mkdir(parents=True)
    observer.write_text("first observation")
    destination = tmp_path / "destination"
    before = {path.relative_to(source): path.read_bytes() for path in source.rglob("*") if path.is_file()}
    first = relocation.plan(source, destination)
    assert relocation.plan(source, destination) == first
    assert before == {path.relative_to(source): path.read_bytes() for path in source.rglob("*") if path.is_file()}
    assert not destination.exists()
    observer.write_text("a later observation")
    repeated = relocation.plan(source, destination)
    assert repeated["snapshot_id"] == first["snapshot_id"]
    assert repeated["revision"] == first["revision"]
    assert repeated["version"] == 2


def test_wal_and_both_archive_layouts_are_preserved_without_sqlite_reprocessing(tmp_path, monkeypatch):
    source = database_root(tmp_path / "source")
    legacy = source / "core/relocation/raw/history.sqlite"
    hidden = source / ".backups/relocations" / ("0" * 64) / "older.sqlite"
    legacy.parent.mkdir(parents=True)
    hidden.parent.mkdir(parents=True)
    legacy.write_bytes((source / DATABASE).read_bytes())
    legacy.with_name(legacy.name + "-wal").write_bytes(b"opaque historical WAL")
    hidden.write_bytes(b"SQLite format 3\x00opaque archived bytes")
    historical = archive_bytes(source)
    seen = []
    original = relocation._sqlite_backup

    def capture(old, new):
        seen.append(Path(old).relative_to(source).as_posix())
        return original(old, new)

    monkeypatch.setattr(relocation, "_sqlite_backup", capture)
    with closing(sqlite3.connect(source / DATABASE)) as keeper:
        keeper.execute("PRAGMA journal_mode=WAL")
        keeper.execute("INSERT INTO items VALUES (2, 'committed WAL')")
        keeper.commit()
        proposal = relocation.plan(source, tmp_path / "destination")
        entries = {entry["path"]: entry for entry in proposal["files"]}
        for name in historical:
            assert entries[name]["kind"] == "binary"
            assert entries[name]["target"] == name
            assert "output_sha256" not in entries[name]
        for suffix in ("-wal", "-shm"):
            name = DATABASE + suffix
            assert entries[name]["target"] == snapshot_target(name, proposal["snapshot_id"])
        destination = Path(proposal["destination"])
        relocation.apply(proposal)
        assert rows(destination / DATABASE) == [(1, "original"), (2, "committed WAL")]
        for suffix in ("", "-wal", "-shm"):
            assert (destination / snapshot_target(DATABASE + suffix, proposal["snapshot_id"])).read_bytes() == (source / (DATABASE + suffix)).read_bytes()
    assert all(name == DATABASE for name in seen)
    assert all((destination / name).read_bytes() == body for name, body in historical.items())


@pytest.mark.parametrize("old_format", [False, True], ids=["v2", "v1"])
def test_partial_copy_restart_reuses_persisted_snapshot_identity(tmp_path, monkeypatch, old_format):
    source = database_root(tmp_path / "source")
    destination = tmp_path / "destination"
    plans = relocation.RelocationPlans(source)
    if old_format:
        proposal = legacy_plan(source, destination)
        artifact = plans._path(proposal["revision"])
        artifact.parent.mkdir()
        artifact.write_text(json.dumps(proposal, sort_keys=True))
    else:
        proposal = plans.review(destination, include_manifest=True)
    raw_relative = snapshot_target(DATABASE, proposal.get("snapshot_id"))
    raw = destination / raw_relative
    temporary = raw.with_name(raw.name + ".relocating")
    copy = relocation.shutil.copy2

    def interrupted(old, new, *args, **kwargs):
        if Path(new) in (raw, temporary):
            Path(new).write_bytes(Path(old).read_bytes()[:31])
            raise OSError("interrupted raw snapshot")
        return copy(old, new, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(relocation.shutil, "copy2", interrupted)
        with pytest.raises(OSError, match="interrupted raw"):
            relocation.apply(proposal)
    artifact = plans._path(proposal["revision"]).read_bytes()
    partial = raw if raw.exists() else temporary
    assert partial.read_bytes() == (source / DATABASE).read_bytes()[:31]
    restarted = relocation.RelocationPlans(source)
    loaded = restarted.load(proposal["revision"])
    assert loaded.get("snapshot_id") == proposal.get("snapshot_id")
    assert restarted.review(destination, include_manifest=True) == proposal
    assert relocation.apply(loaded)["status"] == "complete"
    assert plans._path(proposal["revision"]).read_bytes() == artifact
    assert (destination / raw_relative).read_bytes() == (source / DATABASE).read_bytes()
    if not old_format:
        assert {path.name for path in (destination / ".backups/relocations").iterdir()} == {proposal["snapshot_id"]}
    assert not temporary.exists()
    assert rows(destination / DATABASE) == [(1, "original")]


def test_version_one_retry_keeps_legacy_sqlite_archive_entries_and_receipt(tmp_path, monkeypatch):
    source = database_root(tmp_path / "source")
    archived = source / "core/relocation/raw/history.sqlite"
    archived.parent.mkdir(parents=True)
    archived.write_bytes((source / DATABASE).read_bytes())
    destination = tmp_path / "destination"
    proposal = legacy_plan(source, destination)
    # Historical planners treated the old raw tree as live SQLite. A persisted
    # manifest must retain that interpretation instead of being silently edited.
    entry = next(item for item in proposal["files"] if item["path"] == archived.relative_to(source).as_posix())
    temporary = tmp_path / "legacy-output.sqlite"
    relocation._sqlite_backup(archived, temporary)
    entry.update(kind="sqlite", output_sha256=relocation._digest(temporary))
    proposal["revision"] = relocation._revision(proposal)
    plans = relocation.RelocationPlans(source)
    artifact = plans._path(proposal["revision"])
    artifact.parent.mkdir()
    artifact.write_text(json.dumps(proposal, sort_keys=True))
    original_bytes = artifact.read_bytes()
    backup = relocation._sqlite_backup
    seen = []

    def interrupted(old, new):
        seen.append(Path(old))
        if Path(old) == source / DATABASE:
            raise OSError("old plan interrupted")
        return backup(old, new)

    with monkeypatch.context() as patch:
        patch.setattr(relocation, "_sqlite_backup", interrupted)
        with pytest.raises(OSError, match="old plan"):
            relocation.apply(proposal)
    assert archived in seen
    loaded = relocation.RelocationPlans(source).load(proposal["revision"])
    assert loaded == proposal
    assert relocation.apply(loaded)["status"] == "complete"
    assert artifact.read_bytes() == original_bytes
    assert (destination / snapshot_target(DATABASE)).is_file()
    assert (destination / snapshot_target(entry["path"])).is_file()
    receipt = destination / ".contextopus-receipt.json"
    original_receipt = receipt.read_bytes()
    assert json.loads(original_receipt)["version"] == 1
    assert "snapshot_id" not in json.loads(original_receipt)
    assert relocation.apply(loaded)["status"] == "complete"
    assert receipt.read_bytes() == original_receipt
    assert not (destination / ".backups/relocations").exists()
    assert rows(destination / DATABASE) == [(1, "original")]


@pytest.mark.parametrize("old_format", [False, True], ids=["v2", "v1"])
def test_partial_relocation_rollback_preserves_source_and_snapshot_bytes(tmp_path, monkeypatch, old_format):
    source = database_root(tmp_path / "source")
    document = source / ".pcw/alpha/knowledge/topic.md"
    document.parent.mkdir(parents=True)
    document.write_text("authoring retained")
    destination = tmp_path / "destination"
    proposal = (legacy_plan if old_format else relocation.plan)(source, destination)
    original = relocation._verify_target
    monkeypatch.setattr(relocation, "_verify_target", lambda *args: (_ for _ in ()).throw(OSError("before receipt")))
    with pytest.raises(OSError, match="before receipt"):
        relocation.apply(proposal)
    raw = destination / snapshot_target(DATABASE, proposal.get("snapshot_id"))
    copied = raw.read_bytes()
    assert relocation.rollback(proposal)["status"] == "rolled_back"
    assert not (source / ".contextopus-freeze.json").exists()
    assert not (source / ".contextopus-redirect.json").exists()
    assert document.read_text() == "authoring retained"
    assert raw.read_bytes() == copied == (source / DATABASE).read_bytes()
    assert rows(source / DATABASE) == [(1, "original")]
    monkeypatch.setattr(relocation, "_verify_target", original)


@pytest.mark.parametrize("identity", ["../escape", "f" * 63, "g" * 64, None])
def test_invalid_snapshot_identity_rejected_before_mutation(tmp_path, identity):
    source = database_root(tmp_path / "source")
    destination = tmp_path / "destination"
    proposal = relocation.plan(source, destination)
    proposal["snapshot_id"] = identity
    proposal["revision"] = relocation._revision(proposal)
    with pytest.raises(ValueError, match="snapshot identity"):
        relocation.apply(proposal)
    assert not destination.exists()
    assert not (source / ".contextopus-freeze.json").exists()


def test_snapshot_identity_is_bound_into_final_revision(tmp_path):
    source = database_root(tmp_path / "source")
    proposal = relocation.plan(source, tmp_path / "destination")
    proposal["snapshot_id"] = "f" * 64
    with pytest.raises(ValueError, match="revision mismatch"):
        relocation.apply(proposal)


def test_raw_snapshot_conflict_on_retry_is_never_overwritten(tmp_path, monkeypatch):
    source = database_root(tmp_path / "source")
    destination = tmp_path / "destination"
    proposal = relocation.plan(source, destination)
    with monkeypatch.context() as patch:
        patch.setattr(relocation, "_verify_target", lambda *args: (_ for _ in ()).throw(OSError("before receipt")))
        with pytest.raises(OSError, match="before receipt"):
            relocation.apply(proposal)
    raw = destination / snapshot_target(DATABASE, proposal["snapshot_id"])
    raw.write_bytes(b"unexpected bytes")
    with pytest.raises(ValueError, match="raw snapshot conflict"):
        relocation.apply(proposal)
    assert raw.read_bytes() == b"unexpected bytes"
    assert not (destination / ".contextopus-receipt.json").exists()


def test_raw_snapshot_checksum_failure_remains_retryable(tmp_path, monkeypatch):
    source = database_root(tmp_path / "source")
    destination = tmp_path / "destination"
    proposal = relocation.plan(source, destination)
    raw = destination / snapshot_target(DATABASE, proposal["snapshot_id"])
    temporary = raw.with_name(raw.name + ".relocating")
    copy = relocation.shutil.copy2

    def corrupt_copy(old, new, *args, **kwargs):
        if Path(new) == temporary:
            temporary.write_bytes(b"silently corrupted copy")
            return temporary
        return copy(old, new, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(relocation.shutil, "copy2", corrupt_copy)
        with pytest.raises(IOError, match="raw snapshot checksum mismatch"):
            relocation.apply(proposal)
    assert not raw.exists()
    assert not (destination / ".contextopus-receipt.json").exists()
    assert relocation.apply(proposal)["status"] == "complete"
    assert raw.read_bytes() == (source / DATABASE).read_bytes()
    assert not temporary.exists()


def test_completed_receipt_checks_raw_snapshot_without_rewriting_it(tmp_path):
    source = database_root(tmp_path / "source")
    destination = tmp_path / "destination"
    proposal = relocation.plan(source, destination)
    relocation.apply(proposal)
    receipt = destination / ".contextopus-receipt.json"
    before = receipt.read_bytes()
    (destination / snapshot_target(DATABASE, proposal["snapshot_id"])).write_bytes(b"tampered snapshot")
    with pytest.raises(ValueError, match="SQLite binary snapshot missing"):
        relocation.apply(proposal)
    assert receipt.read_bytes() == before


def test_observer_refresh_keeps_reviewed_snapshot_namespace_with_wal(tmp_path):
    source = database_root(tmp_path / "source")
    observer = source / "core/analytics/events.sqlite"
    observer.parent.mkdir(parents=True)
    destination = tmp_path / "destination"
    with closing(sqlite3.connect(observer)) as database:
        database.execute("PRAGMA journal_mode=WAL")
        database.execute("CREATE TABLE observations (value TEXT)")
        database.execute("INSERT INTO observations VALUES ('preview')")
        database.commit()
        proposal = relocation.plan(source, destination)
        database.execute("INSERT INTO observations VALUES ('before freeze')")
        database.commit()
        repeated = relocation.plan(source, destination)
        assert repeated["snapshot_id"] == proposal["snapshot_id"]
        assert repeated["revision"] == proposal["revision"]
        relocation.apply(proposal)
        receipt = json.loads((destination / ".contextopus-receipt.json").read_text())
        assert receipt["snapshot_id"] == proposal["snapshot_id"]
        assert receipt["revision"] == proposal["revision"]
        relative = observer.relative_to(source).as_posix()
        for suffix in ("", "-wal", "-shm"):
            assert (destination / snapshot_target(relative + suffix, proposal["snapshot_id"])).read_bytes() == (source / (relative + suffix)).read_bytes()
    with closing(sqlite3.connect(destination / "core/analytics/events.sqlite")) as database:
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert database.execute("SELECT value FROM observations").fetchall() == [("preview",), ("before freeze",)]
    assert not (destination / "core/relocation/raw").exists()


def test_existing_archive_cannot_collide_with_new_snapshot_namespace(tmp_path):
    source = database_root(tmp_path / "source")
    identity = "f" * 64
    archive = source / snapshot_target(DATABASE, identity)
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"previous snapshot must survive")
    destination = tmp_path / "destination"
    proposal = relocation.plan(source, destination)
    proposal["snapshot_id"] = identity
    proposal["revision"] = relocation._revision(proposal)
    with pytest.raises(ValueError, match="Duplicate relocation snapshot target"):
        relocation.apply(proposal)
    assert archive.read_bytes() == b"previous snapshot must survive"
    assert not destination.exists()
    assert not (source / ".contextopus-freeze.json").exists()

"""Preservation, fencing and recovery for the explicit legacy SQLite cutover."""

from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import time

import pytest

from contextopus.core.module_storage import ModuleStorage, ModuleStorageError
from contextopus.core.module_storage import legacy
from contextopus.core.storage import StorageLayout


LEDGER_SQL = '''CREATE TABLE "_contextopus_module_migrations" (
    module TEXT NOT NULL, version INTEGER NOT NULL, name TEXT NOT NULL,
    checksum TEXT NOT NULL, PRIMARY KEY(module,version))'''
ALPHA_SQL = '''
CREATE TABLE "alpha::parents" (id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT UNIQUE);
CREATE TABLE "alpha::children" (id INTEGER PRIMARY KEY, parent INTEGER REFERENCES "alpha::parents"(id), body TEXT);
CREATE INDEX "alpha::by_parent" ON "alpha::children" (parent);
CREATE TRIGGER "alpha::upper" AFTER INSERT ON "alpha::children" BEGIN
  UPDATE "alpha::children" SET body=upper(body) WHERE id=NEW.id;
END;
CREATE VIEW "alpha::joined" AS SELECT p.body AS parent,c.body AS child
  FROM "alpha::parents" AS p JOIN "alpha::children" AS c ON p.id=c.parent;
CREATE TABLE "alpha::implicit" (body TEXT);
CREATE TABLE "alpha::generated" (base INTEGER, doubled INTEGER GENERATED ALWAYS AS (base*2) STORED);
CREATE TABLE "alpha::without_rowid" (key TEXT PRIMARY KEY, body BLOB) WITHOUT ROWID;
'''


def shared(tmp_path):
    root = tmp_path / "root"
    path = root / "core/storage/modules.sqlite3"
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(LEDGER_SQL + ";" + ALPHA_SQL)
        conn.execute('CREATE TABLE "beta::items" (id INTEGER PRIMARY KEY, body TEXT)')
        conn.executemany('INSERT INTO "_contextopus_module_migrations" VALUES (?,1,?,?)',
                         [("alpha", "001-schema.sql", hashlib.sha256(ALPHA_SQL.encode()).hexdigest()),
                          ("beta", "001-schema.sql", "beta-checksum")])
        conn.execute('INSERT INTO "alpha::parents" VALUES (80,\'deleted maximum\')')
        conn.execute('DELETE FROM "alpha::parents"')
        conn.execute('INSERT INTO "alpha::parents" VALUES (3,\'parent\')')
        conn.execute('INSERT INTO "alpha::children" VALUES (7,3,\'hello\')')
        conn.executemany('INSERT INTO "alpha::implicit" (rowid,body) VALUES (?,?)', [(4,"four"), (900,"nine hundred")])
        conn.execute('INSERT INTO "alpha::generated" (base) VALUES (12)')
        conn.execute('INSERT INTO "alpha::without_rowid" VALUES (?,?)', ("key", b"\x00\xff"))
        conn.execute('INSERT INTO "beta::items" VALUES (1,?)', ("FOREIGN_SECRET_MARKER" * 100,))
    return root, path


def target(root, module):
    return root / "core/storage/modules" / (module + ".sqlite3")


def test_read_path_inspects_without_creating_or_changing_files(tmp_path):
    root, source = shared(tmp_path)
    original = source.read_bytes()
    assert legacy.read_path(root, "alpha", target(root,"alpha")) == source
    assert legacy.legacy_pending(root)
    assert source.read_bytes() == original
    assert not target(root,"alpha").parent.exists()
    assert not (source.parent / ".backups").exists()


def test_preserves_schema_data_rowids_generated_fk_sequence_and_ledger(tmp_path):
    root, source = shared(tmp_path)
    with sqlite3.connect(source) as conn:
        original_schema = conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name LIKE 'alpha::%' ORDER BY name").fetchall()
        original_ledger = conn.execute('SELECT * FROM "_contextopus_module_migrations" WHERE module=\'alpha\'').fetchall()
    legacy.ensure_partitioned(root)
    assert not legacy.legacy_pending(root)
    assert legacy.read_path(root,"alpha",target(root,"alpha")) == target(root,"alpha")
    with sqlite3.connect(target(root,"alpha")) as conn:
        assert conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name LIKE 'alpha::%' ORDER BY name").fetchall() == original_schema
        assert conn.execute('SELECT * FROM "_contextopus_module_migrations"').fetchall() == original_ledger
        assert conn.execute('SELECT rowid,body FROM "alpha::implicit" ORDER BY rowid').fetchall() == [(4,"four"),(900,"nine hundred")]
        assert conn.execute('SELECT * FROM "alpha::generated"').fetchall() == [(12,24)]
        assert conn.execute('SELECT * FROM "alpha::without_rowid"').fetchall() == [("key",b"\x00\xff")]
        assert conn.execute('SELECT * FROM "alpha::joined"').fetchall() == [("parent","HELLO")]
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute('INSERT INTO "alpha::parents" (body) VALUES (\'after\')').lastrowid == 81
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'beta::%' OR name LIKE '_contextopus_partition_block_%'").fetchall()
        conn.execute('INSERT INTO "alpha::children" VALUES (9,3,\'new\')')
        assert conn.execute('SELECT body FROM "alpha::children" WHERE id=9').fetchone() == ("NEW",)
    assert b"FOREIGN_SECRET_MARKER" not in target(root,"alpha").read_bytes()
    with sqlite3.connect(target(root,"beta")) as conn:
        assert conn.execute('SELECT id FROM "beta::items"').fetchall() == [(1,)]
        assert not conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'alpha::%'").fetchall()
    backups = list((source.parent / ".backups").iterdir())
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as conn:
        assert conn.execute('SELECT * FROM "_contextopus_module_migrations" WHERE module=\'alpha\'').fetchall() == original_ledger
        assert conn.execute('SELECT body FROM "beta::items"').fetchone()[0].startswith("FOREIGN_SECRET")


def test_old_connection_and_old_migration_are_fenced(tmp_path):
    root, source = shared(tmp_path)
    with sqlite3.connect(source) as old:
        old.execute('SELECT * FROM "alpha::parents"').fetchall()
        legacy.ensure_partitioned(root)
        with pytest.raises(sqlite3.IntegrityError, match="partitioned"):
            old.execute('UPDATE "alpha::parents" SET body=\'divergent\'')
        old.rollback()
        assert old.execute('SELECT version FROM "_contextopus_module_migrations" WHERE module=\'alpha\' ORDER BY version').fetchall() == [(0,),(1,)]
        old.execute("BEGIN IMMEDIATE")
        old.execute('CREATE TABLE "new::items" (id INTEGER)')
        with pytest.raises(sqlite3.IntegrityError, match="partitioned"):
            old.execute('INSERT INTO "_contextopus_module_migrations" VALUES (\'new\',1,\'migration\',\'checksum\')')
        old.rollback()
        assert not old.execute("SELECT 1 FROM sqlite_master WHERE name='new::items'").fetchall()


def test_existing_active_writer_fails_promptly_and_can_still_commit(tmp_path):
    root, source = shared(tmp_path)
    with sqlite3.connect(source) as old:
        old.execute('UPDATE "alpha::parents" SET body=\'in flight\'')
        started = time.monotonic()
        with pytest.raises(ModuleStorageError, match="locked"):
            legacy.ensure_partitioned(root)
        assert time.monotonic() - started < 1
        old.commit()
    assert legacy.legacy_pending(root)
    legacy.ensure_partitioned(root)
    with sqlite3.connect(target(root,"alpha")) as conn:
        assert conn.execute('SELECT body FROM "alpha::parents"').fetchall() == [("in flight",)]


def test_partial_publish_routes_reads_to_backup_and_retries(tmp_path, monkeypatch):
    root, source = shared(tmp_path)
    real_link = legacy.os.link
    calls = 0
    def interrupted_link(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated interruption")
        return real_link(*args, **kwargs)
    monkeypatch.setattr(legacy.os, "link", interrupted_link)
    with pytest.raises(OSError, match="simulated"):
        legacy.ensure_partitioned(root)
    assert target(root,"alpha").exists() and not target(root,"beta").exists()
    assert legacy.legacy_pending(root)
    read = legacy.read_path(root,"alpha",target(root,"alpha"))
    assert read.parent.name == ".backups"
    with sqlite3.connect(source) as conn, pytest.raises(sqlite3.IntegrityError, match="partitioned"):
        conn.execute('DELETE FROM "alpha::parents"')
    monkeypatch.setattr(legacy.os, "link", real_link)
    legacy.ensure_partitioned(root)
    assert not legacy.legacy_pending(root)
    legacy.ensure_partitioned(root)
    assert not list(target(root,"alpha").parent.glob(".partition-*"))


@pytest.mark.parametrize("sql", [
    'CREATE TABLE unowned (id INTEGER)',
    'CREATE TABLE "ghost::items" (id INTEGER)',
    'CREATE VIEW "alpha::foreign" AS SELECT * FROM "beta::items"',
    'CREATE TRIGGER "alpha::foreign" AFTER INSERT ON "alpha::parents" BEGIN DELETE FROM "beta::items"; END',
    'CREATE TABLE "alpha::foreign" (id INTEGER REFERENCES "beta::items"(id))',
])
def test_ambiguous_or_crossmodule_schema_fails_without_freezing_source(tmp_path, sql):
    root, source = shared(tmp_path)
    with sqlite3.connect(source) as conn:
        conn.execute(sql)
    original = source.read_bytes()
    with pytest.raises(ModuleStorageError):
        legacy.ensure_partitioned(root)
    assert source.read_bytes() == original
    assert legacy.legacy_pending(root)
    with sqlite3.connect(source) as conn:
        conn.execute('UPDATE "alpha::parents" SET body=\'still writable\'')


def test_existing_destination_is_never_overwritten(tmp_path):
    root, source = shared(tmp_path)
    path = target(root,"alpha")
    path.parent.mkdir()
    path.write_bytes(b"existing-user-file")
    with pytest.raises(ModuleStorageError, match="Conflicting"):
        legacy.ensure_partitioned(root)
    assert path.read_bytes() == b"existing-user-file"
    with sqlite3.connect(source) as conn:
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (legacy.MARKER,)).fetchall()


def test_changed_partial_destination_refuses_recovery_without_overwrite(tmp_path, monkeypatch):
    root, _ = shared(tmp_path)
    publish = legacy._publish
    monkeypatch.setattr(legacy, "_publish", lambda *args: (_ for _ in ()).throw(OSError("interrupted")))
    with pytest.raises(OSError):
        legacy.ensure_partitioned(root)
    path = target(root,"alpha")
    path.write_bytes(b"unexpected-data")
    monkeypatch.setattr(legacy, "_publish", publish)
    with pytest.raises(ModuleStorageError, match="Conflicting"):
        legacy.ensure_partitioned(root)
    assert path.read_bytes() == b"unexpected-data"
    assert legacy.legacy_pending(root)


def test_apply_existing_current_schema_performs_layout_cutover(tmp_path):
    root, source = shared(tmp_path)
    package = tmp_path / "package"
    (package / "migrations").mkdir(parents=True)
    (package / "migrations/001-schema.sql").write_text(ALPHA_SQL)
    contract = {"engine":"sqlite", "schema_version":1, "migrations":"migrations", "compatible_versions":{"min":1,"max":1}}
    storage = ModuleStorage(StorageLayout(root)).for_module("alpha")
    inspected = storage.inspect("alpha",contract,package)
    assert inspected["current_version"] == 1 and inspected["needs_migration"]
    assert storage.prepare("alpha",contract,package)["revision"] == inspected["revision"]
    assert not target(root,"alpha").exists()
    with pytest.raises(ModuleStorageError, match="legacy|Legacy"):
        storage.execute("alpha",'UPDATE "alpha::parents" SET body=\'blocked\'')
    result = storage.apply("alpha",contract,package,inspected["revision"])
    assert result["current_version"] == 1 and not result["needs_migration"]
    assert result["applied_versions"] == []
    assert storage.query("alpha",'SELECT child FROM "alpha::joined"')["rows"] == [{"child":"HELLO"}]
    assert source.exists() and target(root,"alpha").exists() and target(root,"beta").exists()


def test_empty_legacy_catalog_cannot_be_reused_by_old_runtime(tmp_path):
    root = tmp_path / "root"
    source = root / "core/storage/modules.sqlite3"
    source.parent.mkdir(parents=True)
    sqlite3.connect(source).close()
    legacy.ensure_partitioned(root)
    assert not legacy.legacy_pending(root)
    with sqlite3.connect(source) as conn, pytest.raises(sqlite3.IntegrityError, match="partitioned"):
        conn.execute('INSERT INTO "_contextopus_module_migrations" VALUES (\'new\',1,\'step\',\'checksum\')')


def test_partitions_are_compact_and_do_not_duplicate_foreign_payload(tmp_path):
    root, source = shared(tmp_path)
    with sqlite3.connect(source) as conn:
        conn.execute('INSERT INTO "beta::items" VALUES (2,?)', (b"x" * 2_000_000,))
    legacy.ensure_partitioned(root)
    assert target(root,"alpha").stat().st_size < 100_000
    assert target(root,"beta").stat().st_size > 2_000_000
    assert len(list((source.parent / ".backups").iterdir())) == 1


def test_generated_column_shadowing_rowid_does_not_change_implicit_identity(tmp_path):
    root, source = shared(tmp_path)
    with sqlite3.connect(source) as conn:
        conn.execute('CREATE TABLE "alpha::shadow" (base INTEGER, rowid INTEGER GENERATED ALWAYS AS (base*2))')
        conn.execute('INSERT INTO "alpha::shadow" (_rowid_,base) VALUES (901,7)')
    legacy.ensure_partitioned(root)
    with sqlite3.connect(target(root,"alpha")) as conn:
        assert conn.execute('SELECT _rowid_,rowid,base FROM "alpha::shadow"').fetchall() == [(901,14,7)]


def test_all_rowid_aliases_shadowed_fail_safely_before_source_freeze(tmp_path):
    root, source = shared(tmp_path)
    with sqlite3.connect(source) as conn:
        conn.execute('CREATE TABLE "alpha::shadow" (rowid INTEGER,_rowid_ INTEGER,oid INTEGER)')
        conn.execute('INSERT INTO "alpha::shadow" VALUES (1,2,3)')
    original = source.read_bytes()
    with pytest.raises(ModuleStorageError, match="shadows every rowid"):
        legacy.ensure_partitioned(root)
    assert source.read_bytes() == original
    assert not target(root,"alpha").exists()
    with sqlite3.connect(source) as conn:
        conn.execute('UPDATE "alpha::parents" SET body=\'still writable\'')


def test_trigger_effects_are_not_repeated_when_rows_are_copied(tmp_path):
    root, source = shared(tmp_path)
    with sqlite3.connect(source) as conn:
        conn.execute('CREATE TRIGGER "alpha::append" AFTER UPDATE ON "alpha::parents" BEGIN UPDATE "alpha::parents" SET body=body||\'!\' WHERE id=NEW.id; END')
        conn.execute('UPDATE "alpha::parents" SET body=\'before\'')
        assert conn.execute('SELECT body FROM "alpha::parents"').fetchall() == [("before!",)]
    legacy.ensure_partitioned(root)
    with sqlite3.connect(target(root,"alpha")) as conn:
        assert conn.execute('SELECT body FROM "alpha::parents"').fetchall() == [("before!",)]
        conn.execute('UPDATE "alpha::parents" SET body=\'after\'')
        assert conn.execute('SELECT body FROM "alpha::parents"').fetchall() == [("after!",)]


def test_changed_backup_cannot_be_used_for_recovery(tmp_path, monkeypatch):
    root, source = shared(tmp_path)
    monkeypatch.setattr(legacy,"_publish",lambda *args: (_ for _ in ()).throw(OSError("interrupted")))
    with pytest.raises(OSError):
        legacy.ensure_partitioned(root)
    backup = next((source.parent / ".backups").iterdir())
    with sqlite3.connect(backup) as conn:
        conn.execute('UPDATE "alpha::parents" SET body=\'tampered\'')
    with pytest.raises(ModuleStorageError, match="backup changed"):
        legacy.ensure_partitioned(root)
    with pytest.raises(ModuleStorageError, match="backup changed"):
        legacy.read_path(root,"alpha",target(root,"alpha"))


def test_source_backup_is_a_consistent_wal_snapshot(tmp_path):
    root, source = shared(tmp_path)
    with closing(sqlite3.connect(source)) as keeper:
        assert keeper.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        keeper.execute('UPDATE "alpha::parents" SET body=\'from wal\'')
        keeper.commit()
        assert Path(str(source) + "-wal").exists()
        legacy.ensure_partitioned(root)
    with sqlite3.connect(target(root,"alpha")) as conn:
        assert conn.execute('SELECT body FROM "alpha::parents"').fetchall() == [("from wal",)]


def test_completed_receipt_keeps_modules_independent_of_old_database_locks(tmp_path):
    root, source = shared(tmp_path)
    legacy.ensure_partitioned(root)
    assert (source.parent / ".module-partitions.json").is_file()
    storage = ModuleStorage(StorageLayout(root))
    with sqlite3.connect(source) as old:
        old.execute("BEGIN EXCLUSIVE")
        assert not legacy.legacy_pending(root)
        assert storage.query("alpha",'SELECT body FROM "alpha::parents"')["rows"] == [{"body":"parent"}]
        assert storage.query("beta",'SELECT id FROM "beta::items"')["rows"] == [{"id":1}]
        assert storage.execute("alpha",'UPDATE "alpha::parents" SET body=\'independent\'')["rowcount"] == 1
        assert storage.execute("beta",'UPDATE "beta::items" SET body=\'independent\'')["rowcount"] == 1
        legacy.ensure_partitioned(root)


def test_missing_unrelated_partition_does_not_block_another_module(tmp_path):
    root, _ = shared(tmp_path)
    legacy.ensure_partitioned(root)
    target(root,"beta").unlink()
    storage = ModuleStorage(StorageLayout(root))
    assert storage.query("alpha",'SELECT body FROM "alpha::parents"')["rows"] == [{"body":"parent"}]
    with pytest.raises(ModuleStorageError, match="missing"):
        storage.query("beta",'SELECT * FROM "beta::items"')


def test_receipt_publication_interruption_resumes_without_rebuilding_targets(tmp_path, monkeypatch):
    root, source = shared(tmp_path)
    write = legacy._write_receipt
    monkeypatch.setattr(legacy,"_write_receipt",lambda *args: (_ for _ in ()).throw(OSError("interrupted receipt")))
    with pytest.raises(OSError, match="interrupted receipt"):
        legacy.ensure_partitioned(root)
    assert legacy.legacy_pending(root)
    original = target(root,"alpha").read_bytes()
    monkeypatch.setattr(legacy,"_write_receipt",write)
    legacy.ensure_partitioned(root)
    assert not legacy.legacy_pending(root)
    assert target(root,"alpha").read_bytes() == original
    assert (source.parent / ".module-partitions.json").exists()


def test_pending_partial_publication_can_relocate_and_resume(tmp_path, monkeypatch):
    from contextopus.core import relocation
    root, source = shared(tmp_path)
    real_link = legacy.os.link
    calls = 0
    def interrupted_link(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated interruption")
        return real_link(*args, **kwargs)
    monkeypatch.setattr(legacy.os,"link",interrupted_link)
    with pytest.raises(OSError, match="simulated"):
        legacy.ensure_partitioned(root)
    monkeypatch.setattr(legacy.os,"link",real_link)
    assert legacy.legacy_pending(root)
    destination = tmp_path / "relocated"
    proposal = relocation.plan(root,destination)
    assert relocation.apply(proposal)["status"] == "complete"
    assert legacy.legacy_pending(destination)
    read = legacy.read_path(destination,"alpha",target(destination,"alpha"))
    assert read.parent.name == ".backups"
    with sqlite3.connect(read) as conn:
        assert conn.execute('SELECT body FROM "alpha::parents"').fetchall() == [("parent",)]
    legacy.ensure_partitioned(destination)
    assert not legacy.legacy_pending(destination)
    storage = ModuleStorage(StorageLayout(destination))
    assert storage.query("alpha",'SELECT child FROM "alpha::joined"')["rows"] == [{"child":"HELLO"}]
    assert storage.query("beta",'SELECT id FROM "beta::items"')["rows"] == [{"id":1}]

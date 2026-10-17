"""Real SQLite module-domain storage; no model, live root or installation."""

import sqlite3
import threading
import time

import pytest

from contextopus.core.module_storage import ModuleStorage, ModuleStorageError, validate_contract
from contextopus.core.storage import StorageLayout


def package(tmp_path, name="alpha", migrations=None):
    root = tmp_path / "packages" / name
    directory = root / "migrations"
    directory.mkdir(parents=True)
    for number, sql in (migrations or {1: 'CREATE TABLE "{{module}}::sessions" (id INTEGER PRIMARY KEY, body TEXT NOT NULL);'}).items():
        (directory / f"{number:03d}-schema.sql").write_text(sql)
    return root


def contract(version=1, minimum=1, maximum=None):
    return {"engine": "sqlite", "schema_version": version, "migrations": "migrations",
            "compatible_versions": {"min": minimum, "max": maximum or version}}


def install(storage, module, rules, path):
    plan = storage.prepare(module, rules, path)
    return storage.apply(module, rules, path, plan["revision"])


def service(tmp_path):
    return ModuleStorage(StorageLayout(tmp_path / "memory"))


def test_discovery_and_queries_never_create_database(tmp_path):
    storage = service(tmp_path)
    path = package(tmp_path)
    result = storage.inspect("alpha", contract(), path)
    assert result["status"] == "pending" and result["current_version"] == 0
    assert storage.prepare("alpha", contract(), path)["revision"] == result["revision"]
    with pytest.raises(ModuleStorageError, match="absent"):
        storage.query("alpha", 'SELECT * FROM "{{module}}::sessions"')
    with pytest.raises(ModuleStorageError, match="absent"):
        storage.execute("alpha", 'INSERT INTO "{{module}}::sessions" VALUES (1,?)', ("one",))
    assert not storage.path.parent.exists()


def test_two_modules_share_catalog_without_table_or_data_collisions(tmp_path):
    storage = service(tmp_path)
    path = package(tmp_path)
    for module in ("alpha", "beta"):
        assert install(storage, module, contract(), path)["applied_versions"] == [1]
        storage.execute(module, 'INSERT INTO "{{module}}::sessions" VALUES (?,?)', (1, module))
    for module in ("alpha", "beta"):
        assert storage.query(module, 'SELECT body FROM "{{module}}::sessions" WHERE id=?', (1,)) == {
            "columns": ["body"], "rows": [{"body": module}]}
    assert storage.path == tmp_path / "memory/core/storage/modules.sqlite3"
    with sqlite3.connect(storage.path) as conn:
        assert conn.execute('SELECT count(*) FROM "_contextopus_module_migrations"').fetchone()[0] == 2


@pytest.mark.parametrize("extension_api_present", [False, True])
def test_optional_extension_api_keeps_storage_usable_and_loading_denied(tmp_path, monkeypatch, extension_api_present):
    original_connect = sqlite3.connect
    native_enable = getattr(sqlite3.Connection, "enable_load_extension", None)
    connections, disable_calls = [], []

    class Connection(sqlite3.Connection):
        @property
        def enable_load_extension(self):
            if not extension_api_present:
                raise AttributeError("SQLite build has no extension-loading API")

            def enable(value):
                disable_calls.append((self, value))
                if native_enable is not None:
                    native_enable(self, value)

            return enable

    def connect(*args, **kwargs):
        connection = original_connect(*args, factory=Connection, **kwargs)
        connections.append(connection)
        assert hasattr(connection, "enable_load_extension") == extension_api_present
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    storage, path = service(tmp_path), package(tmp_path)
    assert install(storage, "alpha", contract(), path)["applied_versions"] == [1]
    assert storage.inspect("alpha", contract(), path)["status"] == "current"
    storage.execute("alpha", 'INSERT INTO "{{module}}::sessions" VALUES (1,?)', ("retained",))
    # Without an authorizer, the connection itself must still prohibit loading
    # (or the function is absent in SQLite builds without that capability).
    with storage._connection() as connection:
        with pytest.raises(sqlite3.OperationalError, match="not authorized|no such function"):
            connection.execute("SELECT load_extension('anything')")
    with pytest.raises(ModuleStorageError, match="not authorized|no such function"):
        storage.query("alpha", "SELECT load_extension('anything')")
    with pytest.raises(ModuleStorageError, match="not authorized|no such function"):
        storage.execute("alpha", 'INSERT INTO "{{module}}::sessions" VALUES (2,load_extension(\'anything\'))')
    (path / "migrations/002-extension.sql").write_text("SELECT load_extension('anything');")
    with pytest.raises(ModuleStorageError, match="not authorized|no such function"):
        install(storage, "alpha", contract(2), path)
    assert storage.inspect("alpha", contract(2), path)["current_version"] == 1
    assert storage.query("alpha", 'SELECT body FROM "{{module}}::sessions"')["rows"] == [{"body": "retained"}]
    assert disable_calls == ([(connection, False) for connection in connections] if extension_api_present else [])


def test_second_migration_preserves_data_and_stricter_new_code_can_upgrade(tmp_path):
    storage, path = service(tmp_path), package(tmp_path)
    install(storage, "alpha", contract(), path)
    storage.execute("alpha", 'INSERT INTO "{{module}}::sessions" VALUES (1,?)', ("retained",))
    (path / "migrations/002-expand.sql").write_text('ALTER TABLE "{{module}}::sessions" ADD COLUMN status TEXT DEFAULT \'open\';')
    rules = contract(2, minimum=2)
    inspection = storage.inspect("alpha", rules, path)
    assert inspection["status"] == "pending" and not inspection["compatible"]
    assert install(storage, "alpha", rules, path)["applied_versions"] == [2]
    assert storage.query("alpha", 'SELECT body,status FROM "{{module}}::sessions"')["rows"] == [{"body": "retained", "status": "open"}]
    assert install(storage, "alpha", rules, path)["applied_versions"] == []


def test_failed_migrations_roll_back_all_steps_and_can_retry(tmp_path):
    storage = service(tmp_path)
    path = package(tmp_path, migrations={1: 'CREATE TABLE "{{module}}::sessions" (id INTEGER);',
        2: 'INSERT INTO "{{module}}::sessions" VALUES (7); INSERT INTO absent VALUES (1);'})
    rules = contract(2)
    with pytest.raises(ModuleStorageError):
        install(storage, "alpha", rules, path)
    assert storage.inspect("alpha", rules, path)["current_version"] == 0
    with sqlite3.connect(storage.path) as conn:
        assert conn.execute("SELECT name FROM sqlite_master").fetchall() == []
    (path / "migrations/002-schema.sql").write_text('INSERT INTO "{{module}}::sessions" VALUES (7);')
    assert install(storage, "alpha", rules, path)["applied_versions"] == [1, 2]
    assert storage.query("alpha", 'SELECT id FROM "{{module}}::sessions"')["rows"] == [{"id": 7}]


def test_interruption_rolls_back_ddl_and_ledger_before_retry(tmp_path, monkeypatch):
    import contextopus.core.module_storage.service as implementation
    storage, path = service(tmp_path), package(tmp_path)
    install(storage, "alpha", contract(), path)
    storage.execute("alpha", 'INSERT INTO "{{module}}::sessions" VALUES (1,?)', ("retained",))
    (path / "migrations/002-expand.sql").write_text('ALTER TABLE "{{module}}::sessions" ADD COLUMN status TEXT;')
    original = implementation.statements
    def interrupted(sql):
        yield from original(sql)
        raise KeyboardInterrupt("simulated interrupted migration")
    with monkeypatch.context() as patch:
        patch.setattr(implementation, "statements", interrupted)
        with pytest.raises(KeyboardInterrupt):
            install(storage, "alpha", contract(2), path)
    assert storage.inspect("alpha", contract(2), path)["current_version"] == 1
    assert storage.query("alpha", 'SELECT * FROM "{{module}}::sessions"')["columns"] == ["id", "body"]
    assert install(storage, "alpha", contract(2), path)["applied_versions"] == [2]


def test_applied_checksums_missing_steps_and_stale_preparation_block(tmp_path):
    storage, path = service(tmp_path), package(tmp_path)
    plan = storage.prepare("alpha", contract(), path)
    first = path / "migrations/001-schema.sql"
    original = first.read_text()
    first.write_text(original + "\n-- changed before apply\n")
    with pytest.raises(ModuleStorageError, match="changed"):
        storage.apply("alpha", contract(), path, plan["revision"])
    install(storage, "alpha", contract(), path)
    first.write_text(original)
    assert storage.inspect("alpha", contract(), path)["status"] == "error"
    with pytest.raises(ModuleStorageError, match="Applied migration changed"):
        storage.prepare("alpha", contract(), path)
    first.unlink()
    assert "continuous steps" in storage.inspect("alpha", contract(), path)["errors"][0]


def test_code_rollback_uses_explicit_compatibility_without_downgrading(tmp_path):
    storage, path = service(tmp_path), package(tmp_path)
    first = (path / "migrations/001-schema.sql").read_text()
    (path / "migrations/002-expand.sql").write_text('ALTER TABLE "{{module}}::sessions" ADD COLUMN status TEXT;')
    install(storage, "alpha", contract(2), path)
    older = package(tmp_path, "older", {1: first})
    result = storage.inspect("alpha", contract(), older)
    assert result["status"] == "incompatible" and result["current_version"] == 2
    with pytest.raises(ModuleStorageError, match="no automatic downgrade"):
        storage.prepare("alpha", contract(), older)
    supported = contract(maximum=2)
    assert storage.inspect("alpha", supported, older)["compatible"]
    assert install(storage, "alpha", supported, older)["applied_versions"] == []
    assert storage.query("alpha", 'SELECT * FROM "{{module}}::sessions"')["columns"] == ["id", "body", "status"]


@pytest.mark.parametrize("sql", [
    'INSERT INTO "{{module}}::sessions" VALUES (1,\'bad\')',
    'UPDATE "{{module}}::sessions" SET body=\'bad\'',
    'DELETE FROM "{{module}}::sessions"',
    'CREATE TABLE "{{module}}::extra" (id INTEGER)',
    'PRAGMA writable_schema=ON', 'ATTACH DATABASE \'other.sqlite\' AS other',
    'BEGIN', 'COMMIT', 'SAVEPOINT x', "SELECT load_extension('anything')",
])
def test_query_cannot_write_or_control_connection(tmp_path, sql):
    storage, path = service(tmp_path), package(tmp_path)
    install(storage, "alpha", contract(), path)
    with pytest.raises(ModuleStorageError):
        storage.query("alpha", sql)
    assert storage.query("alpha", 'SELECT count(*) AS n FROM "{{module}}::sessions"')["rows"] == [{"n": 0}]


@pytest.mark.parametrize("sql", [
    'SELECT * FROM "beta::sessions"', 'UPDATE "beta::sessions" SET body=\'bad\'',
    'DELETE FROM "beta::sessions"', 'INSERT INTO "beta::sessions" VALUES (2,\'bad\')',
    'SELECT * FROM "_contextopus_module_migrations"', 'SELECT * FROM sqlite_master',
    'CREATE TABLE "alpha::extra" (id INTEGER)', 'DROP TABLE "alpha::sessions"',
    'PRAGMA foreign_keys=OFF', "ATTACH DATABASE ':memory:' AS other", 'BEGIN',
    'SELECT 1',
])
def test_execute_is_own_module_dml_only(tmp_path, sql):
    storage, path = service(tmp_path), package(tmp_path)
    for module in ("alpha", "beta"):
        install(storage, module, contract(), path)
        storage.execute(module, 'INSERT INTO "{{module}}::sessions" VALUES (1,?)', (module,))
    with pytest.raises(ModuleStorageError):
        storage.execute("alpha", sql)
    assert storage.query("beta", 'SELECT body FROM "{{module}}::sessions"')["rows"] == [{"body": "beta"}]


@pytest.mark.parametrize("sql", [
    'UPDATE "beta::sessions" SET body=\'bad\';',
    'DROP TABLE "beta::sessions";',
    'CREATE TABLE unscoped (id INTEGER);',
    'ALTER TABLE "{{module}}::sessions" RENAME TO "beta::renamed";',
    'CREATE TABLE "{{module}}::bad_fk" (id INTEGER REFERENCES "beta::sessions"(id));',
    'PRAGMA user_version=8;', 'BEGIN;', "ATTACH DATABASE ':memory:' AS other;",
])
def test_migrations_cannot_change_other_modules_or_core_ledger(tmp_path, sql):
    storage, path = service(tmp_path), package(tmp_path)
    for module in ("alpha", "beta"):
        install(storage, module, contract(), path)
        storage.execute(module, 'INSERT INTO "{{module}}::sessions" VALUES (1,?)', (module,))
    (path / "migrations/002-bad.sql").write_text(sql)
    with pytest.raises(ModuleStorageError):
        install(storage, "alpha", contract(2), path)
    assert storage.query("beta", 'SELECT body FROM "{{module}}::sessions"')["rows"] == [{"body": "beta"}]
    assert storage.inspect("alpha", contract(2), path)["current_version"] == 1


def test_ledger_is_not_mutable_from_module_migration(tmp_path):
    storage, path = service(tmp_path), package(tmp_path)
    install(storage, "alpha", contract(), path)
    (path / "migrations/002-ledger.sql").write_text('UPDATE "_contextopus_module_migrations" SET checksum=\'bad\';')
    with pytest.raises(ModuleStorageError):
        install(storage, "alpha", contract(2), path)
    assert storage.inspect("alpha", contract(2), path)["current_version"] == 1


def test_ordinary_foreign_keys_indexes_and_trigger_migrations(tmp_path):
    storage = service(tmp_path)
    path = package(tmp_path, migrations={1: '''
CREATE TABLE "{{module}}::sessions" (id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT UNIQUE);
CREATE TABLE "{{module}}::messages" (id INTEGER PRIMARY KEY, session_id INTEGER REFERENCES "{{module}}::sessions"(id), body TEXT);
CREATE INDEX "{{module}}::messages_session" ON "{{module}}::messages" (session_id);
CREATE TRIGGER "{{module}}::normalize" AFTER INSERT ON "{{module}}::messages" BEGIN
  UPDATE "{{module}}::messages" SET body=upper(body) WHERE id=NEW.id;
END;
'''})
    install(storage, "alpha", contract(), path)
    storage.execute("alpha", 'INSERT INTO "{{module}}::sessions" (body) VALUES (?)', ("session",))
    storage.execute("alpha", 'INSERT INTO "{{module}}::messages" VALUES (1,1,?)', ("hello",))
    assert storage.query("alpha", 'SELECT body FROM "{{module}}::messages"')["rows"] == [{"body": "HELLO"}]


def test_sql_splitting_preserves_quoted_semicolons_and_trailing_comments(tmp_path):
    storage = service(tmp_path)
    path = package(tmp_path, migrations={1: '''-- first comment ; not a statement
CREATE TABLE "{{module}}::sessions" (id INTEGER PRIMARY KEY, body TEXT DEFAULT 'a;b');
/* middle comment ; */ INSERT INTO "{{module}}::sessions" VALUES (1,'quoted;value');
INSERT INTO "{{module}}::sessions" VALUES (2,'-- not a comment;'); -- trailing comment ;'''})
    install(storage, "alpha", contract(), path)
    assert storage.query("alpha", 'SELECT body FROM "{{module}}::sessions" ORDER BY id')["rows"] == [{"body": "quoted;value"}, {"body": "-- not a comment;"}]


def test_deadline_interrupts_long_queries_without_writes(tmp_path):
    storage, path = service(tmp_path), package(tmp_path)
    install(storage, "alpha", contract(), path)
    with pytest.raises(ModuleStorageError, match="deadline"):
        storage.execute("alpha", 'INSERT INTO "{{module}}::sessions" VALUES (1,?)', ("late",), deadline=time.monotonic() - 1)
    with pytest.raises(ModuleStorageError, match="interrupted|deadline"):
        storage.query("alpha", 'WITH RECURSIVE x(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM x WHERE n<100000000) SELECT sum(n) FROM x', deadline=time.monotonic() + .005)
    assert storage.query("alpha", 'SELECT count(*) AS n FROM "{{module}}::sessions"')["rows"] == [{"n": 0}]


def test_deadline_before_commit_rolls_back_and_success_is_not_relabelled(tmp_path, monkeypatch):
    import contextopus.core.module_storage.service as implementation
    storage, path = service(tmp_path), package(tmp_path)
    install(storage, "alpha", contract(), path)
    original = implementation.check_deadline
    calls = []
    def expire_before_commit(deadline):
        calls.append(deadline)
        if len(calls) == 2:
            raise ModuleStorageError("Module storage deadline exceeded")
        original(deadline)
    with monkeypatch.context() as patch:
        patch.setattr(implementation, "check_deadline", expire_before_commit)
        with pytest.raises(ModuleStorageError, match="deadline"):
            storage.execute("alpha", 'INSERT INTO "{{module}}::sessions" VALUES (1,?)', ("expired",), deadline=time.monotonic() + 10)
    assert storage.query("alpha", 'SELECT * FROM "{{module}}::sessions"')["rows"] == []
    calls.clear()
    def forbid_postcommit_check(deadline):
        calls.append(deadline)
        assert len(calls) <= 2, "A successful commit must not be reported as a timeout"
        original(deadline)
    with monkeypatch.context() as patch:
        patch.setattr(implementation, "check_deadline", forbid_postcommit_check)
        assert storage.execute("alpha", 'INSERT INTO "{{module}}::sessions" VALUES (1,?)', ("saved",), deadline=time.monotonic() + 10)["rowcount"] == 1
    assert storage.query("alpha", 'SELECT body FROM "{{module}}::sessions"')["rows"] == [{"body": "saved"}]


@pytest.mark.parametrize("change", [
    {"engine": "postgres"}, {"schema_version": True}, {"schema_version": 0},
    {"migrations": "../escape"}, {"migrations": "/absolute"},
    {"compatible_versions": {"min": 2, "max": 1}}, {"unexpected": True},
])
def test_contracts_reject_unsupported_or_ambiguous_shapes(change):
    rules = contract()
    rules.update(change)
    with pytest.raises(ModuleStorageError):
        validate_contract(rules)


def test_invalid_module_and_symlinked_migrations_are_rejected(tmp_path):
    storage, path = service(tmp_path), package(tmp_path)
    with pytest.raises(ModuleStorageError, match="Invalid module ID"):
        storage.prepare("alpha::beta", contract(), path)
    original = path / "migrations/001-schema.sql"
    external = tmp_path / "external.sql"
    original.rename(external)
    original.symlink_to(external)
    assert storage.inspect("alpha", contract(), path)["status"] == "error"


def test_views_and_triggers_cannot_launder_other_module_access(tmp_path):
    storage, path = service(tmp_path), package(tmp_path)
    for module in ("alpha", "beta"):
        install(storage, module, contract(), path)
        storage.execute(module, 'INSERT INTO "{{module}}::sessions" VALUES (1,?)', (module,))
    (path / "migrations/002-views.sql").write_text('''
CREATE VIEW "{{module}}::other" AS SELECT * FROM "beta::sessions";
CREATE TRIGGER "{{module}}::bad_trigger" AFTER UPDATE ON "{{module}}::sessions" BEGIN
  UPDATE "beta::sessions" SET body=NEW.body WHERE id=NEW.id;
END;
''')
    install(storage, "alpha", contract(2), path)
    with pytest.raises(ModuleStorageError):
        storage.query("alpha", 'SELECT * FROM "{{module}}::other"')
    with pytest.raises(ModuleStorageError):
        storage.execute("alpha", 'UPDATE "{{module}}::sessions" SET body=\'bad\'')
    for module in ("alpha", "beta"):
        assert storage.query(module, 'SELECT body FROM "{{module}}::sessions"')["rows"] == [{"body": module}]


def test_root_freeze_blocks_domain_writes_but_retains_reads(tmp_path):
    storage, path = service(tmp_path), package(tmp_path)
    install(storage, "alpha", contract(), path)
    (storage.layout.root / ".contextopus-freeze.json").write_text('{}')
    with pytest.raises((ModuleStorageError, RuntimeError), match="frozen"):
        storage.execute("alpha", 'INSERT INTO "{{module}}::sessions" VALUES (1,?)', ("blocked",))
    assert storage.query("alpha", 'SELECT count(*) AS n FROM "{{module}}::sessions"')["rows"] == [{"n": 0}]


def test_native_execute_obeys_root_lock_and_same_thread_reentrancy(tmp_path):
    storage, path = service(tmp_path), package(tmp_path)
    install(storage, "alpha", contract(), path)
    started, done, failures = threading.Event(), threading.Event(), []
    def write():
        started.set()
        try:
            storage.execute("alpha", 'INSERT INTO "{{module}}::sessions" VALUES (2,?)', ("worker",))
        except BaseException as exc:
            failures.append(exc)
        finally:
            done.set()
    with storage.layout.guard():
        storage.execute("alpha", 'INSERT INTO "{{module}}::sessions" VALUES (1,?)', ("reentrant",))
        worker = threading.Thread(target=write)
        worker.start()
        assert started.wait(1)
        assert not done.wait(.05)
    assert done.wait(3)
    worker.join(timeout=1)
    assert failures == []
    assert storage.query("alpha", 'SELECT body FROM "{{module}}::sessions" ORDER BY id')["rows"] == [{"body": "reentrant"}, {"body": "worker"}]


def test_relocation_uses_consistent_sqlite_backup_for_shared_wal_catalog(tmp_path, monkeypatch):
    from contextopus.core import relocation
    storage, path = service(tmp_path), package(tmp_path)
    for module in ("alpha", "beta"):
        install(storage, module, contract(), path)
    # Keep WAL open: committed data must be obtained through SQLite backup,
    # rather than copying only the main database file.
    keeper = sqlite3.connect(storage.path)
    try:
        keeper.execute("PRAGMA journal_mode=WAL")
        keeper.execute("BEGIN")
        keeper.execute('SELECT * FROM "alpha::sessions"').fetchall()
        for module in ("alpha", "beta"):
            storage.execute(module, 'INSERT INTO "{{module}}::sessions" VALUES (1,?)', (module,))
        backups = []
        original = relocation._sqlite_backup
        def capture(source, target):
            backups.append((source, target))
            return original(source, target)
        monkeypatch.setattr(relocation, "_sqlite_backup", capture)
        destination = tmp_path / "relocated"
        plan = relocation.plan(storage.layout.root, destination)
        entry = next(item for item in plan["files"] if item["path"] == "core/storage/modules.sqlite3")
        assert entry["kind"] == "sqlite" and "snapshot" not in entry
        assert relocation.apply(plan)["status"] == "complete"
        moved = ModuleStorage(StorageLayout(destination))
        for module in ("alpha", "beta"):
            assert moved.query(module, 'SELECT body FROM "{{module}}::sessions"')["rows"] == [{"body": module}]
            assert moved.inspect(module, contract(), path)["status"] == "current"
        assert any(source == storage.path and str(target).endswith("modules.sqlite3.relocating") for source, target in backups)
        with sqlite3.connect(moved.path) as conn:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert storage.path.is_file()  # source is retained by relocation
    finally:
        keeper.close()

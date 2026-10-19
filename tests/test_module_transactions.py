"""Actual same-connection SQL, namespace enforcement and disconnect rollback."""

import threading
import time
from types import SimpleNamespace

import pytest

from contextopus.core.module_management.core_access import ModuleCoreAccess
from contextopus.core.module_storage import ModuleStorage, ModuleStorageError
from contextopus.core.storage import StorageLayout


@pytest.fixture
def app(tmp_path):
    storage = ModuleStorage(StorageLayout(tmp_path / "root"))
    package = tmp_path / "package"
    (package / "migrations").mkdir(parents=True)
    (package / "migrations/001-schema.sql").write_text('''
        CREATE TABLE "{{module}}::parents" (id INTEGER PRIMARY KEY, body TEXT NOT NULL);
        CREATE TABLE "{{module}}::children" (id INTEGER PRIMARY KEY, parent INTEGER REFERENCES "{{module}}::parents"(id));
    ''')
    contract = dict(engine="sqlite", schema_version=1, migrations="migrations",
                    compatible_versions=dict(min=1, max=1))
    for module in ("alpha", "beta"):
        plan = storage.prepare(module, contract, package)
        storage.apply(module, contract, package, plan["revision"])
    return SimpleNamespace(module_storage=storage, layout=storage.layout,
                           package=package, contract=contract)


def access(app, module="alpha", **kwargs):
    return ModuleCoreAccess(app, module, storage_declared=True, **kwargs)


def write(core, body="one", **kwargs):
    return core.call("storage.execute", dict(sql='INSERT INTO "{{module}}::parents" (body) VALUES (?)',
                                            parameters=[body], **kwargs))


def rows(core, **kwargs):
    return core.call("storage.query", dict(sql='SELECT * FROM "{{module}}::parents" ORDER BY id', **kwargs))["rows"]


def test_reads_and_conditional_writes_share_connection_with_fk_and_rowid(app):
    core = access(app)
    token = core.call("storage.begin", {})
    pk = write(core, **token)["lastrowid"]
    assert rows(core, **token) == [dict(id=pk, body="one")]
    assert rows(core) == []  # Explicitly independent read sees committed data.
    core.call("storage.execute", dict(sql='INSERT INTO "{{module}}::children" (parent) SELECT id FROM "{{module}}::parents" WHERE body=?', parameters=["one"], **token))
    core.call("storage.commit", token)
    assert rows(core) == [dict(id=pk, body="one")]
    assert core.call("storage.query", dict(sql='SELECT parent FROM "{{module}}::children"'))["rows"] == [dict(parent=pk)]
    core.close()


@pytest.mark.parametrize("sql", ['INSERT INTO "{{module}}::children" VALUES (1,999)',
    'INSERT INTO "{{module}}::parents" VALUES (1,NULL)',
    'SELECT * FROM "beta::parents"', 'CREATE TABLE "alpha::evil" (id)',
    'COMMIT', 'SAVEPOINT x', 'PRAGMA foreign_keys=OFF', 'SELECT * FROM sqlite_master'])
def test_every_sql_failure_aborts_whole_owned_transaction_even_if_caught(app, sql):
    core = access(app)
    token = core.call("storage.begin", {})
    write(core, **token)
    method = "storage.query" if sql.startswith("SELECT") else "storage.execute"
    with pytest.raises(ModuleStorageError):
        core.call(method, dict(sql=sql, **token))
    with pytest.raises(ModuleStorageError, match="inactive"):
        core.call("storage.commit", token)
    assert rows(core) == []
    assert write(core)["rowcount"] == 1
    core.close()


def test_timeout_rolls_back_when_idle_and_next_calls_cannot_commit(app):
    core = access(app)
    token = core.call("storage.begin", dict(timeout_seconds=.04))
    write(core, **token)
    time.sleep(.06)
    assert core.expire() is True
    assert core.expire() is False
    with pytest.raises(ModuleStorageError, match="inactive"):
        core.call("storage.commit", token)
    assert rows(core) == []
    core.close()


def test_per_call_sql_deadline_aborts_the_entire_transaction(app):
    core = access(app)
    token = core.call("storage.begin", {})
    write(core, **token)
    with pytest.raises(ModuleStorageError, match="interrupted|deadline"):
        core.call("storage.query", dict(sql='WITH RECURSIVE x(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM x WHERE n<100000000) SELECT sum(n) FROM x', **token),
                  deadline=time.monotonic() + .01)
    assert rows(core) == []
    assert write(core)["rowcount"] == 1
    core.close()


def test_cross_thread_disconnect_rolls_back_and_releases_catalog_writer(app):
    core = access(app)
    token = core.call("storage.begin", {})
    write(core, **token)
    thread = threading.Thread(target=core.close)
    thread.start()
    thread.join(1)
    assert not thread.is_alive()
    other = access(app)
    assert rows(other) == []
    assert write(other)["rowcount"] == 1
    with pytest.raises(RuntimeError, match="closed"):
        rows(core)
    other.close()


def test_wrong_token_and_untagged_write_never_join_active_transaction(app):
    core = access(app)
    token = core.call("storage.begin", {})
    write(core, **token)
    with pytest.raises(ModuleStorageError, match="inactive"):
        write(core, transaction_id="other-session")
    with pytest.raises(ModuleStorageError, match="Explicit"):
        write(core)
    assert len(rows(core, **token)) == 1
    assert rows(core) == []
    core.call("storage.rollback", token)
    assert rows(core) == []
    core.close()


def test_query_kind_and_invalid_limits_and_bad_parameters(app):
    core = access(app, kind="query")
    for method in ("begin", "execute", "commit", "rollback"):
        with pytest.raises(PermissionError):
            core.call("storage." + method, {})
    core.close()
    core = access(app)
    for seconds in (0, -1, 6, True, float("inf"), float("nan")):
        with pytest.raises(ModuleStorageError):
            core.call("storage.begin", dict(timeout_seconds=seconds))
    token = core.call("storage.begin", {})
    write(core, **token)
    with pytest.raises(ValueError):
        core.call("storage.query", dict(sql="SELECT 1", parameters="invalid", **token))
    assert rows(core) == []
    core.close()


def test_other_module_write_finishes_while_transaction_remains_open(app):
    owner, other = access(app), access(app, "beta")
    token = owner.call("storage.begin", {})
    write(owner, **token)
    started, done, failures = threading.Event(), threading.Event(), []

    def second_write():
        started.set()
        try:
            write(other, "beta")
        except BaseException as exc:
            failures.append(exc)
        finally:
            done.set()

    thread = threading.Thread(target=second_write)
    thread.start()
    assert started.wait(1) and done.wait(1)
    assert owner._transactions.active
    with app.layout.guard():
        assert rows(other) == [dict(id=1, body="beta")]
    owner.call("storage.commit", token)
    thread.join(1)
    assert failures == []
    assert rows(other) == [dict(id=1, body="beta")]
    owner.close()
    other.close()


def test_same_module_writer_deadline_bounded_and_guarded_native_writer_fails_fast(app):
    owner, other = access(app), access(app)
    token = owner.call("storage.begin", {})
    started = time.monotonic()
    with pytest.raises(ModuleStorageError, match="deadline|busy"):
        other.call("storage.execute", dict(sql='INSERT INTO "{{module}}::parents" (body) VALUES (?)',
                   parameters=["late"]), deadline=time.monotonic() + .03)
    assert time.monotonic() - started < .5
    with app.layout.guard():
        with pytest.raises(ModuleStorageError, match="busy"):
            write(other)
        plan = app.module_storage.prepare("alpha", app.contract, app.package)
        with pytest.raises(ModuleStorageError, match="busy"):
            app.module_storage.apply("alpha", app.contract, app.package, plan["revision"])
    owner.call("storage.commit", token)
    assert write(other)["rowcount"] == 1
    owner.close()
    other.close()


def test_freeze_before_commit_rolls_back_transaction(app):
    core = access(app)
    token = core.call("storage.begin", {})
    write(core, **token)
    (app.layout.root / ".contextopus-freeze.json").write_text("{}")
    with pytest.raises((RuntimeError, ModuleStorageError), match="frozen"):
        core.call("storage.commit", token)
    assert rows(core) == []
    core.close()


def _process_transaction_owner(root, ready, release, failures):
    """Spawn-compatible process owning an uncommitted alpha database write."""
    from contextopus.core.module_storage.transactions import StorageTransactions
    transaction = StorageTransactions(ModuleStorage(StorageLayout(root)), "alpha")
    try:
        token = transaction.begin()
        transaction.statement(token["transaction_id"], 'INSERT INTO "{{module}}::parents" (body) VALUES (?)', ["process"], write=True)
        ready.set()
        if not release.wait(4):
            raise RuntimeError("Parent did not release process transaction")
        transaction.rollback(token["transaction_id"])
    except BaseException as exc:
        failures.put(repr(exc))
        ready.set()
    finally:
        transaction.close()


def test_process_transaction_serializes_own_module_and_allows_beta_and_root(app):
    import multiprocessing
    context = multiprocessing.get_context("spawn")
    ready, release, failures = context.Event(), context.Event(), context.Queue()
    process = context.Process(target=_process_transaction_owner,
                              args=(str(app.layout.root), ready, release, failures))
    process.start()
    owner, other = access(app), access(app, "beta")
    try:
        assert ready.wait(3)
        assert process.is_alive()
        assert write(other, "beta")["rowcount"] == 1
        with app.layout.guard(deadline=time.monotonic() + .2):
            assert rows(other) == [dict(id=1, body="beta")]
        with pytest.raises(ModuleStorageError, match="deadline|busy"):
            owner.call("storage.execute", dict(sql='INSERT INTO "{{module}}::parents" (body) VALUES (?)', parameters=["blocked"]), deadline=time.monotonic() + .05)
        assert rows(owner) == []
    finally:
        release.set()
        process.join(3)
        if process.is_alive():
            process.terminate()
            process.join(1)
        owner.close()
        other.close()
    assert process.exitcode == 0
    assert failures.empty()
    final = access(app)
    try:
        assert rows(final) == []
    finally:
        final.close()

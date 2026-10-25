from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
import pytest
from contextopus.core.analytics import OperationJournal, sanitize
from contextopus.core.storage import StorageLayout


def test_read_absent_journal_does_not_create_storage(tmp_path):
    root = tmp_path / "absent"
    assert OperationJournal(StorageLayout(root)).summary()["requests"] is None
    assert not root.exists()


def test_success_failure_started_and_24h_window(tmp_path):
    journal = OperationJournal(StorageLayout(tmp_path))
    ctx = SimpleNamespace(workspace="chosen")
    old = journal.begin(ctx, "third.observe", {})
    success = journal.begin(ctx, "third.read", {"scope": "chosen"})
    failure = journal.begin(ctx, "other.change", {})
    unfinished = journal.begin(ctx, "other.pending", {})
    journal.finish(old, duration=100)
    journal.finish(success, result={"count": 3}, duration=2)
    journal.finish(failure, error=RuntimeError("private-password"), duration=4)
    with journal.connect() as db:
        db.execute(
            "UPDATE operations SET started=? WHERE id=?",
            ((datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(), old),
        )
        rows = db.execute(
            "SELECT operation,module,context,outcome,error FROM operations WHERE id IN (?,?)",
            (failure, unfinished),
        ).fetchall()
    assert journal.summary() == {
        "requests": 3,
        "errors": 1,
        "average_seconds": 3.0,
        "period": "24h",
    }
    assert ("other.change", "other", "chosen", "error", "RuntimeError") in rows
    assert ("other.pending", "other", "chosen", "started", None) in rows
    assert b"private-password" not in journal.path.read_bytes()


def test_nested_secrets_and_source_text_never_retained(tmp_path):
    journal = OperationJournal(StorageLayout(tmp_path))
    identifier = journal.begin(
        None,
        "module.op",
        {
            "nested": {"apiKey": "top-secret", "access_token": "token-value"},
            "content": "private-source",
            "url": "https://user:pass@example.org/path",
            "header": "Bearer credential-value",
        },
    )
    journal.finish(
        identifier,
        result={"password": "result-secret", "text": "private-result"},
        duration=float("nan"),
    )
    with journal.connect() as db:
        parameters, result, duration = db.execute(
            "SELECT parameters,result,duration FROM operations"
        ).fetchone()
    assert "REDACTED_SECRET" in parameters
    assert json.loads(parameters)["content"] == {"retained": False, "characters": 14}
    assert json.loads(result)["text"]["retained"] is False
    assert duration is None
    for secret in (
        "top-secret",
        "token-value",
        "private-source",
        "user:pass",
        "credential-value",
        "result-secret",
        "private-result",
    ):
        assert secret.encode() not in journal.path.read_bytes()


def test_connections_close_and_rollback(tmp_path):
    journal = OperationJournal(StorageLayout(tmp_path))
    with journal.connect() as connection:
        connection.execute("INSERT INTO operations (id) VALUES ('committed')")
    import sqlite3

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    with pytest.raises(RuntimeError):
        with journal.connect() as rolled_back:
            rolled_back.execute("INSERT INTO operations (id) VALUES ('rolled-back')")
            raise RuntimeError("stop")
    with pytest.raises(sqlite3.ProgrammingError):
        rolled_back.execute("SELECT 1")
    with journal.connect() as db:
        assert db.execute("SELECT id FROM operations").fetchall() == [("committed",)]


def test_sanitize_bounds_recursive_and_large_values():
    recursive = {}
    recursive["self"] = recursive
    assert len(json.dumps(sanitize(recursive))) < 2000
    assert sanitize("x" * 5000)["characters"] == 5000
    assert len(sanitize(list(range(1000)))) == 101


def test_registry_journals_external_module_without_workspace_cycle(tmp_path):
    from contextopus.core.operations import OperationRegistry, OperationSpec
    from contextopus.core.operations import OperationInputError

    journal = OperationJournal(StorageLayout(tmp_path))
    registry = OperationRegistry(journal)
    schema = {
        "type": "object",
        "properties": {"value": {"type": "integer"}},
        "required": ["value"],
        "additionalProperties": False,
    }
    registry.register(
        OperationSpec(
            "third.double", "query", schema, lambda context, value: {"value": value * 2}
        )
    )
    assert registry.dispatch(
        "query", "third.double", {"value": 3}, SimpleNamespace(workspace=None)
    ) == {"value": 6}
    assert journal.summary()["requests"] == 1
    with pytest.raises(OperationInputError):
        registry.dispatch("query", "third.double", {"value": "invalid"})
    assert journal.summary()["requests"] == 1
    assert not (tmp_path / "modules/workspace").exists()
    with journal.connect() as db:
        module, context, outcome = db.execute(
            "SELECT module,context,outcome FROM operations"
        ).fetchone()
    assert (module, context, outcome) == ("third", None, "ok")


def test_rebind_forwards_inflight_finish_and_other_journals(tmp_path):
    import shutil

    source = StorageLayout(tmp_path / "source")
    destination = StorageLayout(tmp_path / "destination")
    first, other = OperationJournal(source), OperationJournal(source)
    ident = first.begin(None, "core.relocation_apply", {})
    source_before = first.path.read_bytes()
    shutil.copytree(source.root, destination.root)
    first.rebind(destination)
    other.finish(ident, result={"status": "complete"}, duration=1)
    later = first.begin(None, "core.status", {})
    first.finish(later, result={}, duration=2)
    assert first.path == other.path == destination.analytics / "operations.sqlite3"
    assert (source.analytics / "operations.sqlite3").read_bytes() == source_before
    assert first.summary()["requests"] == 2
    with first.connect() as db:
        assert {row[0] for row in db.execute("SELECT outcome FROM operations")} == {
            "ok"
        }

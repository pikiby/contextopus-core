"""Reviewed, recoverable import of an existing trusted module database.

A pristine backup and durable pending receipt precede the legacy write barrier.
The target contains the same receipt before atomic publication, so a crash at
either side of publication can be retried without replacing target data.
"""

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid

from .contract import ModuleStorageError
from .legacy import _connect, _copy_columns, _digest, _new_file, _quote, _regular, _sync

MARKER = "_contextopus_native_import"
PREFIX = "_contextopus_native_import_block_"


def _encode(value):
    return {"bytes": value.hex()} if isinstance(value, bytes) else value


def inventory(connection):
    """Hash all schema and rows, including implicit rowids and SQLite sequences."""
    schema = [tuple(row) for row in connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")
        if row["name"] != MARKER and not row["name"].startswith(PREFIX)]
    result = {"schema": hashlib.sha256(json.dumps(schema, ensure_ascii=False).encode()).hexdigest(), "tables": {}}
    for kind, name, _, _ in schema:
        if kind != "table":
            continue
        columns = _copy_columns(connection, name)
        hashes = []
        for row in connection.execute("SELECT " + ",".join(map(_quote, columns)) + " FROM " + _quote(name)):
            hashes.append(hashlib.sha256(json.dumps([_encode(value) for value in row],
                ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()).digest())
        result["tables"][name] = {"rows": len(hashes), "sha256": hashlib.sha256(b"".join(sorted(hashes))).hexdigest()}
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ModuleStorageError("Import source failed SQLite integrity check")
    if connection.execute("PRAGMA foreign_key_check").fetchone():
        raise ModuleStorageError("Import source contains broken foreign keys")
    return result


def _paths(storage, source):
    source = Path(source)
    storage._safe_path(source)
    storage._safe_path()
    if source == storage.path:
        raise ModuleStorageError("Import source and target must differ")
    directory = Path(storage.layout.root) / "modules" / storage.module / ".storage-migrations"
    storage._safe_path(directory)
    return source, directory


def _revision(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _read_marker(connection):
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE name=?", (MARKER,)).fetchone():
        return None
    rows = connection.execute("SELECT payload FROM " + _quote(MARKER)).fetchall()
    if len(rows) != 1:
        raise ModuleStorageError("Invalid module import marker")
    payload = json.loads(rows[0][0])
    if payload.get("format") != 1 or payload.get("revision") != _revision(payload["plan"]):
        raise ModuleStorageError("Invalid module import marker")
    return payload


def prepare(storage, source):
    source, _ = _paths(storage, source)
    relative_source = source.relative_to(storage.layout.root).as_posix()
    relative_target = storage.path.relative_to(storage.layout.root).as_posix()
    _regular(source)
    with closing(_connect(source)) as reader:
        reader.execute("BEGIN")
        marker = _read_marker(reader)
        state = inventory(reader)
    if marker is not None:
        plan = marker["plan"]
        if state != plan["inventory"] or plan["module"] != storage.module or plan["source"] != relative_source or plan["target"] != relative_target:
            raise ModuleStorageError("Legacy import source changed after cutover")
    else:
        plan = {"format": 1, "module": storage.module, "source": relative_source,
                "target": relative_target, "inventory": state}
    revision = _revision(plan)
    status = "pending"
    if storage.path.exists():
        with storage._connection() as target:
            receipt = _read_marker(target)
        if receipt is None or receipt["revision"] != revision:
            raise ModuleStorageError("Import target already exists without matching provenance; refusing overwrite")
        status = "complete"
    return {**plan, "revision": revision, "status": status}


def _write_json(path, payload):
    if path.is_symlink():
        raise ModuleStorageError("Import receipt cannot be a symlink")
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex)
    _new_file(temporary)
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        _sync(temporary)
        os.replace(temporary, path)
        _sync(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _barrier(source, payload):
    with closing(_connect(source, write=True)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            if inventory(connection) != payload["plan"]["inventory"]:
                raise ModuleStorageError("Import source changed; prepare and review again")
            existing = _read_marker(connection)
            if existing is not None and existing != payload:
                raise ModuleStorageError("Conflicting legacy module import marker")
            if existing is None:
                tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                connection.execute("CREATE TABLE " + _quote(MARKER) + " (payload TEXT NOT NULL)")
                connection.execute("INSERT INTO " + _quote(MARKER) + " VALUES (?)", (json.dumps(payload, sort_keys=True),))
                for name in tables:
                    for action in ("INSERT", "UPDATE", "DELETE"):
                        trigger = PREFIX + hashlib.sha256((name + action).encode()).hexdigest()
                        connection.execute("CREATE TRIGGER " + _quote(trigger) + " BEFORE " + action + " ON " + _quote(name)
                            + " BEGIN SELECT RAISE(ABORT,'Module storage was migrated; use current module runtime'); END")
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def _publish(stage, target):
    # Same-directory hard link publishes atomically and refuses to replace a file.
    os.link(stage, target)
    _sync(target.parent)


def apply(storage, source, expected_revision):
    source, directory = _paths(storage, source)
    # Older native modules serialize legacy writers on the root guard. This
    # explicit one-time cutover holds it until their durable barrier is active.
    with storage.layout.guard(), storage._write_guard():
        plan = prepare(storage, source)
        if plan["revision"] != expected_revision:
            raise ModuleStorageError("Import source changed; prepare and review again")
        core_plan = {key: plan[key] for key in ("format", "module", "source", "target", "inventory")}
        directory.mkdir(parents=True, exist_ok=True)
        backup = directory / (expected_revision + ".sqlite3")
        receipt_path = directory / (expected_revision + ".json")
        storage._safe_path(backup)
        storage._safe_path(receipt_path)
        if receipt_path.exists():
            state = json.loads(receipt_path.read_text(encoding="utf-8"))
            if state["plan"] != core_plan or state["revision"] != expected_revision:
                raise ModuleStorageError("Conflicting module import receipt")
            _regular(backup)
            if _digest(backup) != state["backup_sha256"]:
                raise ModuleStorageError("Module import backup changed; recovery requires review")
        else:
            if backup.exists():
                # A process may have died after backup fsync, before receipt.
                _regular(backup)
                with closing(_connect(backup)) as reader:
                    if inventory(reader) != core_plan["inventory"]:
                        raise ModuleStorageError("Conflicting module import backup")
            else:
                _new_file(backup)
                try:
                    with closing(_connect(source)) as reader, closing(sqlite3.connect(backup)) as writer:
                        reader.backup(writer)
                    _sync(backup)
                    with closing(_connect(backup)) as reader:
                        if inventory(reader) != core_plan["inventory"]:
                            raise ModuleStorageError("Import source changed while creating backup")
                except BaseException:
                    backup.unlink()
                    raise
            state = {"format": 1, "revision": expected_revision, "plan": core_plan,
                     "backup": backup.relative_to(storage.layout.root).as_posix(), "backup_sha256": _digest(backup)}
            _write_json(receipt_path, {**state, "status": "pending"})
        marker = {key: state[key] for key in ("format", "revision", "plan", "backup", "backup_sha256")}
        _barrier(source, marker)
        if plan["status"] != "complete":
            stage = storage.path.with_name("." + storage.path.name + ".import-" + uuid.uuid4().hex)
            _new_file(stage)
            try:
                with closing(_connect(backup)) as reader, closing(sqlite3.connect(stage)) as writer:
                    reader.backup(writer)
                    writer.execute("CREATE TABLE " + _quote(MARKER) + " (payload TEXT NOT NULL)")
                    writer.execute("INSERT INTO " + _quote(MARKER) + " VALUES (?)", (json.dumps(marker, sort_keys=True),))
                    writer.commit()
                with closing(_connect(stage)) as reader:
                    if inventory(reader) != core_plan["inventory"]:
                        raise ModuleStorageError("Imported database differs from source backup")
                _sync(stage)
                _publish(stage, storage.path)
            finally:
                stage.unlink(missing_ok=True)
        _write_json(receipt_path, {**marker, "status": "complete"})
        return {**plan, "status": "complete", "backup": str(backup), "receipt": str(receipt_path)}

"""Explicit, recoverable cutover from the old shared module SQLite catalog.

The shared file remains in place to reject writes from older Core processes.
A pristine SQLite backup is retained in the hidden backup directory. Routing changes only after every
partition has been durably published; an interrupted cutover is safe to retry.
"""

from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid

from .contract import ModuleStorageError, module_id
from ..storage import sync_directory

LEDGER = "_contextopus_module_migrations"
MARKER = "_contextopus_module_partitioning"
BLOCK_PREFIX = "_contextopus_partition_block_"


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def _paths(root):
    root = Path(root).resolve()
    source = root / "core/storage/modules.sqlite3"
    for path in (root / "core", source.parent, source, source.parent / "modules", source.parent / ".backups"):
        if path.is_symlink():
            raise ModuleStorageError("Module storage paths cannot contain symlinks")
    return source, source.parent / "modules"


def _connect(path, *, write=False):
    conn = sqlite3.connect(path.resolve().as_uri() + ("?mode=rw" if write else "?mode=ro"),
                           uri=True, isolation_level=None, timeout=0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA trusted_schema=OFF")
    if not write:
        conn.execute("PRAGMA query_only=ON")
    return conn


def _checksum(value):
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _validate_state(state):
    if (not isinstance(state, dict) or set(state) != {"format", "state", "backup", "backup_sha256", "targets"}
            or state["format"] != 1 or state["state"] not in {"pending", "complete"}
            or not isinstance(state["backup"], str)
            or not state["backup"].startswith("modules.sqlite3.pre-partition-")
            or Path(state["backup"]).name != state["backup"]
            or not isinstance(state["targets"], dict)
            or not _checksum(state["backup_sha256"])):
        raise ValueError("invalid partition marker")
    for module, digest in state["targets"].items():
        module_id(module)
        if not _checksum(digest):
            raise ValueError("invalid partition checksum")
    return state


def _marker(conn):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (MARKER,)).fetchone():
        return None
    try:
        rows = conn.execute(f'SELECT payload FROM "{MARKER}"').fetchall()
        return _validate_state(json.loads(rows[0][0]) if len(rows) == 1 else None)
    except (sqlite3.Error, ValueError, TypeError, KeyError, IndexError) as exc:
        raise ModuleStorageError("Invalid legacy module partition marker; recovery requires review") from exc


def _receipt(source):
    path = source.parent / ".module-partitions.json"
    if not path.exists() and not path.is_symlink():
        return None
    _regular(path)
    try:
        state = _validate_state(json.loads(path.read_text(encoding="utf-8")))
        if state["state"] != "complete":
            raise ValueError("incomplete receipt")
        return state
    except (ValueError, TypeError, KeyError) as exc:
        raise ModuleStorageError("Invalid module partition completion receipt") from exc


def _write_receipt(source, state):
    existing = _receipt(source)
    if existing is not None:
        if existing != state:
            raise ModuleStorageError("Conflicting module partition completion receipt")
        return
    path = source.parent / ".module-partitions.json"
    temporary = source.parent / (".module-partitions-" + uuid.uuid4().hex + ".tmp")
    _new_file(temporary)
    try:
        temporary.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
        _sync(temporary)
        try:
            os.link(temporary, path)
        except FileExistsError:
            if _receipt(source) != state:
                raise ModuleStorageError("Conflicting module partition completion receipt")
        _sync(source.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _digest(path):
    # Relocation uses SQLite backup, which can change page/header bytes without
    # changing the database. Bind recovery to SQL objects and typed cell values,
    # including implicit rowids, rather than to incidental file serialization.
    digest = hashlib.sha256()
    with closing(_connect(path)) as conn:
        for setting in ("page_size", "encoding", "application_id", "user_version"):
            digest.update(repr((setting, conn.execute("PRAGMA " + setting).fetchone()[0])).encode("utf-8"))
        schema = list(conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY name"))
        tables = {row["name"]: row for row in conn.execute("PRAGMA table_list") if row["schema"] == "main"}
        for row in schema:
            digest.update(repr(tuple(row)).encode("utf-8"))
            if row["type"] != "table":
                continue
            name = row["name"]
            if tables[name]["wr"]:
                selection = "*"
                keys = sorted((item for item in conn.execute("PRAGMA table_xinfo(" + _quote(name) + ")") if item["pk"]), key=lambda item: item["pk"])
                ordering = ",".join(_quote(item["name"]) for item in keys)
            else:
                columns = _copy_columns(conn, name)
                selection = _quote(columns[0]) + ",*"
                ordering = _quote(columns[0])
            for item in conn.execute("SELECT " + selection + " FROM " + _quote(name) + " ORDER BY " + ordering):
                digest.update(repr(tuple(item)).encode("utf-8"))
    return digest.hexdigest()


def _regular(path):
    if path.is_symlink() or not path.is_file():
        raise ModuleStorageError("Module partition file is missing or is not a regular file: " + str(path))


def _backup_path(source, state):
    path = source.parent / ".backups" / state["backup"]
    _regular(path)
    if _digest(path) != state["backup_sha256"]:
        raise ModuleStorageError("Legacy module backup changed; recovery requires review")
    return path


def read_path(root, module, target):
    """Choose a read source without creating or migrating anything."""
    module_id(module)
    source, directory = _paths(root)
    target = Path(target)
    receipt = _receipt(source)
    if receipt is not None:
        if module in receipt["targets"]:
            _regular(target)
        return target
    if source.is_file():
        try:
            with closing(_connect(source)) as conn:
                state = _marker(conn)
            if state is None:
                return source
            if state["state"] == "pending":
                return _backup_path(source, state)
            if module in state["targets"]:
                _regular(target)
        except sqlite3.Error as exc:
            raise ModuleStorageError("Cannot inspect legacy module storage: " + str(exc)) from exc
    return target


def legacy_pending(root):
    source, _ = _paths(root)
    if _receipt(source) is not None:
        return False
    if not source.is_file():
        return False
    try:
        with closing(_connect(source)) as conn:
            _marker(conn)
            # The durable receipt is the final routing switch. A crash after
            # source completion but before receipt publication still needs apply.
            return True
    except sqlite3.Error as exc:
        raise ModuleStorageError("Cannot inspect legacy module storage: " + str(exc)) from exc


def _owner(name):
    if not isinstance(name, str) or "::" not in name:
        raise ModuleStorageError("Ambiguous object in legacy module storage: " + str(name))
    owner, suffix = name.split("::", 1)
    module_id(owner)
    if not suffix:
        raise ModuleStorageError("Empty legacy module object name")
    return owner


def _validate(conn):
    """Reject unsupported ownership or hidden dependencies before touching source."""
    schema = [dict(row) for row in conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master")]
    ledger = next((row for row in schema if row["name"] == LEDGER and row["type"] == "table"), None)
    if ledger is None:
        if schema:
            raise ModuleStorageError("Legacy module storage has no Core migration ledger")
        return [], schema
    columns = [row["name"] for row in conn.execute(f'PRAGMA table_info("{LEDGER}")')]
    if columns != ["module", "version", "name", "checksum"]:
        raise ModuleStorageError("Unsupported legacy Core migration ledger schema")
    modules = {}
    for row in conn.execute(f'SELECT * FROM "{LEDGER}" ORDER BY module,version'):
        owner = module_id(row["module"])
        versions = modules.setdefault(owner, [])
        if (type(row["version"]) is not int or row["version"] != len(versions) + 1
                or not isinstance(row["name"], str) or not isinstance(row["checksum"], str)):
            raise ModuleStorageError("Legacy migration ledger has missing or invalid steps")
        versions.append(row["version"])
    for row in schema:
        name, table = row["name"], row["tbl_name"]
        if name == LEDGER or (table == LEDGER and row["sql"] is None) or name == "sqlite_sequence":
            continue
        owner = _owner(table)
        if owner not in modules:
            raise ModuleStorageError("Legacy schema has an owner without migration history: " + owner)
        if row["sql"] is None:
            if row["type"] != "index" or not name.startswith("sqlite_autoindex_" + table + "_"):
                raise ModuleStorageError("Unsupported implicit legacy schema object: " + name)
        elif _owner(name) != owner or "CREATE VIRTUAL TABLE" in row["sql"].upper():
            raise ModuleStorageError("Unsupported or cross-module legacy schema object: " + name)
        if row["type"] == "table":
            for key in conn.execute("PRAGMA foreign_key_list(" + _quote(table) + ")"):
                if _owner(key["table"]) != owner:
                    raise ModuleStorageError("Cross-module foreign key in legacy storage")
    if any(row["name"] == "sqlite_sequence" for row in schema):
        tables = {row["name"] for row in schema if row["type"] == "table"}
        seen = set()
        for row in conn.execute("SELECT name,seq FROM sqlite_sequence"):
            if row["name"] not in tables or row["name"] in seen or type(row["seq"]) is not int:
                raise ModuleStorageError("Unsupported legacy autoincrement sequence state")
            seen.add(row["name"])
    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ModuleStorageError("Legacy module storage failed its integrity check")
    if conn.execute("PRAGMA foreign_key_check").fetchone():
        raise ModuleStorageError("Legacy module storage contains broken foreign keys")

    # SQLite resolves trigger bodies and views lazily. Compile reads and all DML
    # variants so copying a seemingly owned object cannot hide another owner.
    for row in schema:
        if row["name"] == LEDGER or row["name"].startswith("sqlite_") or row["type"] not in {"table", "view"}:
            continue
        owner, table = _owner(row["name"]), _quote(row["name"])
        def authorize(action, first, second, database, trigger):
            if action in {sqlite3.SQLITE_READ, sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE}:
                if not str(first).startswith(owner + "::"):
                    return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_FUNCTION and str(second).lower() in {"load_extension", "writefile", "readfile", "eval"}:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        columns = [item["name"] for item in conn.execute("PRAGMA table_xinfo(" + table + ")") if item["hidden"] == 0]
        conn.set_authorizer(authorize)
        try:
            conn.execute("EXPLAIN SELECT * FROM " + table).fetchall()
            if row["type"] == "table" or any(item["type"] == "trigger" and item["tbl_name"] == row["name"] for item in schema):
                if columns:
                    names = ",".join(_quote(name) for name in columns)
                    conn.execute("EXPLAIN INSERT INTO " + table + " (" + names + ") VALUES (" + ",".join("NULL" for _ in columns) + ")").fetchall()
                    conn.execute("EXPLAIN UPDATE " + table + " SET " + ",".join(_quote(name) + "=" + _quote(name) for name in columns)).fetchall()
                conn.execute("EXPLAIN DELETE FROM " + table).fetchall()
        except sqlite3.Error as exc:
            raise ModuleStorageError("Unsupported or cross-module legacy dependency: " + row["name"] + ": " + str(exc)) from exc
        finally:
            conn.set_authorizer(None)
    return sorted(modules), schema


def _new_file(path):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)


def _sync(path):
    if path.is_dir():
        sync_directory(path)
        return
    # Windows _commit (used by fsync) rejects a read-only file descriptor.
    # Keep POSIX's read-only access for existing read-only backup files.
    descriptor = os.open(path, os.O_RDWR if os.name == 'nt' else os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _copy_columns(conn, table):
    table_columns = list(conn.execute("PRAGMA table_xinfo(" + _quote(table) + ")"))
    columns = [item["name"] for item in table_columns if item["hidden"] == 0]
    info = next(row for row in conn.execute("PRAGMA table_list") if row["schema"] == "main" and row["name"] == table)
    if not info["wr"]:
        # Preserve implicit rowids, including gaps, without assuming an INTEGER
        # PRIMARY KEY exists. All three shadowed aliases are ambiguous; fail
        # before freezing rather than silently assigning new identities.
        names = {item["name"].casefold() for item in table_columns}
        alias = next((name for name in ("rowid", "_rowid_", "oid") if name not in names), None)
        if alias is None:
            raise ModuleStorageError("Unsupported legacy table shadows every rowid alias: " + table)
        columns.insert(0, alias)
    return columns


def _partition(backup, target, module, schema):
    _new_file(target)
    with closing(_connect(backup)) as reader, closing(sqlite3.connect(target, isolation_level=None)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("PRAGMA trusted_schema=OFF")
        for setting in ("page_size", "application_id", "user_version"):
            value = int(reader.execute("PRAGMA " + setting).fetchone()[0])
            conn.execute("PRAGMA " + setting + "=" + str(value))
        encoding = reader.execute("PRAGMA encoding").fetchone()[0]
        conn.execute("PRAGMA encoding='" + encoding + "'")
        conn.execute("BEGIN IMMEDIATE")
        owned = [row for row in schema if row["name"] == LEDGER or
                 (not row["name"].startswith("sqlite_") and _owner(row["tbl_name"]) == module)]
        for row in owned:
            if row["type"] == "table":
                conn.execute(row["sql"])
        for row in owned:
            if row["type"] != "table":
                continue
            table = row["name"]
            columns = ["module", "version", "name", "checksum"] if table == LEDGER else _copy_columns(reader, table)
            fields = ",".join(_quote(name) for name in columns)
            selected = reader.execute("SELECT " + fields + " FROM " + _quote(table)
                                      + (" WHERE module=? ORDER BY version" if table == LEDGER else ""),
                                      (module,) if table == LEDGER else ())
            conn.executemany("INSERT INTO " + _quote(table) + " (" + fields + ") VALUES ("
                             + ",".join("?" for _ in columns) + ")", selected)
        if any(row["name"] == "sqlite_sequence" for row in schema):
            # INSERT may advance sqlite_sequence, but a deleted maximum must
            # retain its original high-water mark as well.
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'").fetchone():
                conn.execute("DELETE FROM sqlite_sequence")
                conn.executemany("INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)",
                                 [tuple(row) for row in reader.execute("SELECT name,seq FROM sqlite_sequence")
                                  if _owner(row["name"]) == module])
        # Install triggers only after copying rows: their effects already exist
        # in the source snapshot and must not be executed a second time.
        for row in owned:
            if row["type"] != "table" and row["sql"] is not None:
                conn.execute(row["sql"])
        conn.execute("COMMIT")
        conn.execute("PRAGMA foreign_keys=ON")
        _validate(conn)
    _sync(target)
    return _digest(target)


def _publish(source, directory, state, stages):
    for module, digest in state["targets"].items():
        target = directory / (module + ".sqlite3")
        if target.exists() or target.is_symlink():
            _regular(target)
            try:
                matches = _digest(target) == digest
            except sqlite3.Error:
                matches = False
            if not matches:
                raise ModuleStorageError("Conflicting existing module partition; refusing to overwrite: " + str(target))
        else:
            try:
                os.link(stages[module], target)
            except FileExistsError as exc:
                raise ModuleStorageError("Module partition appeared during migration; retry after review") from exc
    _sync(directory)
    state = {**state, "state": "complete"}
    with closing(_connect(source, write=True)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(f'UPDATE "{MARKER}" SET payload=?', (json.dumps(state, sort_keys=True),))
        conn.execute("COMMIT")
    _write_receipt(source, state)
    for path in stages.values():
        path.unlink(missing_ok=True)
    _sync(directory)


def ensure_partitioned(root):
    """Run only from explicit apply/install while holding Core's root guard."""
    source, directory = _paths(root)
    if _receipt(source) is not None or not source.is_file():
        return
    stages = {}
    try:
        with closing(_connect(source, write=True)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                state = _marker(conn)
                if state is not None and state["state"] == "complete":
                    for module in state["targets"]:
                        _regular(directory / (module + ".sqlite3"))
                    conn.execute("ROLLBACK")
                    _write_receipt(source, state)
                    return
                directory.mkdir(parents=True, exist_ok=True)
                token = uuid.uuid4().hex
                if state is None:
                    modules, schema = _validate(conn)
                    for module in modules:
                        target = directory / (module + ".sqlite3")
                        if target.exists() or target.is_symlink():
                            raise ModuleStorageError("Conflicting existing module partition; refusing to overwrite: " + str(target))
                    backups = source.parent / ".backups"
                    backups.mkdir(exist_ok=True)
                    backup = backups / (source.name + ".pre-partition-" + token)
                    _new_file(backup)
                    # A separate reader avoids SQLite backup's same-connection
                    # write-transaction deadlock; BEGIN IMMEDIATE excludes writers.
                    with closing(_connect(source)) as reader, closing(sqlite3.connect(backup)) as writer:
                        reader.backup(writer)
                        writer.execute("PRAGMA journal_mode=DELETE")
                    _sync(backup)
                    _sync(backups)
                    state = {"format": 1, "state": "pending", "backup": backup.name,
                             "backup_sha256": _digest(backup), "targets": {}}
                else:
                    backup = _backup_path(source, state)
                    with closing(_connect(backup)) as reader:
                        modules, schema = _validate(reader)
                for module in modules:
                    stage = directory / (".partition-" + token + "-" + module + ".sqlite3")
                    stages[module] = stage
                    digest = _partition(backup, stage, module, schema)
                    if module in state["targets"] and state["targets"][module] != digest:
                        raise ModuleStorageError("Rebuilt module partition differs from its recovery checksum")
                    state["targets"][module] = digest
                if _marker(conn) is None:
                    if not schema:
                        conn.execute(f'CREATE TABLE "{LEDGER}" (module TEXT NOT NULL, version INTEGER NOT NULL, name TEXT NOT NULL, checksum TEXT NOT NULL, PRIMARY KEY(module,version))')
                        schema = [dict(row) for row in conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master")]
                    conn.execute(f'CREATE TABLE "{MARKER}" (payload TEXT NOT NULL)')
                    conn.execute(f'INSERT INTO "{MARKER}" VALUES (?)', (json.dumps(state, sort_keys=True),))
                    tables = [row["name"] for row in schema if row["type"] == "table" and row["name"] != "sqlite_sequence"]
                    for index, table in enumerate(tables):
                        for operation in ("INSERT", "UPDATE", "DELETE"):
                            name = BLOCK_PREFIX + str(index) + "_" + operation.lower()
                            conn.execute("CREATE TRIGGER " + _quote(name) + " BEFORE " + operation + " ON " + _quote(table)
                                         + " BEGIN SELECT RAISE(ABORT,'Legacy module storage was partitioned; restart with current Core'); END")
                    # Old migration APIs inspect their ledger before DDL. An
                    # impossible version blocks old apply even if schema-current;
                    # the pristine backup retains the actual migration history.
                    # Temporarily remove only the ledger insert blocker to add it.
                    if modules:
                        ledger_index = tables.index(LEDGER)
                        blocker = BLOCK_PREFIX + str(ledger_index) + "_insert"
                        conn.execute("DROP TRIGGER " + _quote(blocker))
                        conn.executemany(f'INSERT INTO "{LEDGER}" VALUES (?,0,?,?)',
                                         [(module, "partitioned-restart-required", "partitioned") for module in modules])
                        conn.execute("CREATE TRIGGER " + _quote(blocker) + " BEFORE INSERT ON " + _quote(LEDGER)
                                     + " BEGIN SELECT RAISE(ABORT,'Legacy module storage was partitioned; restart with current Core'); END")
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        _sync(source.parent)
        _publish(source, directory, state, stages)
    except sqlite3.Error as exc:
        raise ModuleStorageError("Legacy module storage migration failed: " + str(exc)) from exc
    finally:
        for path in stages.values():
            path.unlink(missing_ok=True)

"""SQLite authorization is an API boundary, not an OS sandbox for trusted code."""

import sqlite3
import time

from .contract import ModuleStorageError, module_id


def render(module, sql):
    module_id(module)
    if not isinstance(sql, str) or not sql.strip() or "\x00" in sql:
        raise ModuleStorageError("SQL must be a nonempty string without NUL")
    return sql.replace("{{module}}", module)


def statements(sql):
    """Preserve ordinary SQL, including semicolons inside trigger bodies."""
    pending = ""
    for char in sql:
        pending += char
        if char == ";" and sqlite3.complete_statement(pending):
            yield pending
            pending = ""
    if pending.strip():
        # sqlite3.execute accepts a final statement without ';', and a trailing
        # comment is valid even when complete_statement reports it incomplete.
        yield pending


def check_deadline(deadline):
    if deadline is not None and time.monotonic() >= deadline:
        raise ModuleStorageError("Module storage deadline exceeded")


def authorize(module, *, write=False, migration=False):
    prefix = module_id(module) + "::"
    own = lambda name: isinstance(name, str) and name.startswith(prefix) and len(name) > len(prefix)
    ddl_single = {sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_CREATE_VIEW,
                  sqlite3.SQLITE_DROP_TABLE, sqlite3.SQLITE_DROP_VIEW}
    ddl_pair = {sqlite3.SQLITE_CREATE_INDEX, sqlite3.SQLITE_CREATE_TRIGGER,
                sqlite3.SQLITE_DROP_INDEX, sqlite3.SQLITE_DROP_TRIGGER}

    def callback(action, first, second, database, source):
        if database not in (None, "main"):
            return sqlite3.SQLITE_DENY
        if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE}:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION:
            return (sqlite3.SQLITE_DENY if str(second).lower() in
                    {"load_extension", "writefile", "readfile", "eval", "fts3_tokenizer"}
                    else sqlite3.SQLITE_OK)
        if action == sqlite3.SQLITE_READ:
            return sqlite3.SQLITE_OK if own(first) or (migration and first == "sqlite_master") else sqlite3.SQLITE_DENY
        if action in {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE}:
            allowed = write and own(first)
            if allowed:
                callback.wrote = True
            # SQLite itself edits its schema catalog during authorized DDL.
            allowed = allowed or (migration and first == "sqlite_master")
            return sqlite3.SQLITE_OK if allowed else sqlite3.SQLITE_DENY
        if action in ddl_single:
            sequence = action == sqlite3.SQLITE_CREATE_TABLE and first == "sqlite_sequence"
            return sqlite3.SQLITE_OK if migration and (own(first) or sequence) else sqlite3.SQLITE_DENY
        if action in ddl_pair:
            autoindex = (action == sqlite3.SQLITE_CREATE_INDEX and own(second)
                         and str(first).startswith("sqlite_autoindex_" + prefix))
            return sqlite3.SQLITE_OK if migration and own(second) and (own(first) or autoindex) else sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_ALTER_TABLE:
            return sqlite3.SQLITE_OK if migration and first == "main" and own(second) else sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_REINDEX:
            return sqlite3.SQLITE_OK if migration and own(first) else sqlite3.SQLITE_DENY
        # No ATTACH/DETACH, PRAGMA, transaction control, temp/virtual objects,
        # extension loading, ANALYZE or access to another module's catalog.
        return sqlite3.SQLITE_DENY

    callback.wrote = False
    return callback

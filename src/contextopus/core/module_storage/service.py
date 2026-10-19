"""Separate SQLite databases with module-owned migrations and Core ledgers."""

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from .contract import ModuleStorageError, migration_files, module_id, validate_contract
from .coordination import acquire_database_write, database_write
from .legacy import ensure_partitioned, legacy_pending, read_path
from .sql import authorize, check_deadline, render, statements


LEDGER = "_contextopus_module_migrations"


class ModuleStorage:
    def __init__(self, layout, module=None):
        self.layout = layout
        self.module = module_id(module) if module is not None else None
        self.directory = Path(layout.root) / "core/storage/modules"
        self.legacy_path = Path(layout.root) / "core/storage/modules.sqlite3"
        self.path = self.directory / (self.module + ".sqlite3") if self.module else self.directory

    def for_module(self, module):
        """Bind internal connections and writer ownership to one module file."""
        module_id(module)
        if self.module is not None:
            if module != self.module:
                raise ModuleStorageError("Storage is bound to another module")
            return self
        return type(self)(self.layout, module)

    def native(self):
        """Trusted in-process module API; never exposed by the child SQL bridge."""
        from .trusted import NativeModuleStorage
        return NativeModuleStorage(self)

    def _acquire_write_gate(self, deadline=None):
        if self.module is None:
            raise ModuleStorageError("A module-bound storage connection is required")
        self._safe_path()
        self._writable_root()
        if not self.path.is_file():
            raise ModuleStorageError("Module storage is absent; explicitly prepare/apply its schema first")
        return acquire_database_write(self.layout, self.path, deadline, module=self.module)

    @contextmanager
    def _write_guard(self, deadline=None):
        if self.module is None:
            raise ModuleStorageError("A module-bound storage connection is required")
        self._safe_path()
        self._writable_root()
        with database_write(self.layout, self.path, deadline, module=self.module):
            yield

    def _safe_path(self, selected=None):
        selected = self.path if selected is None else selected
        root = Path(self.layout.root).resolve()
        if not selected.resolve().is_relative_to(root):
            raise ModuleStorageError("Module storage escapes the common root")
        for path in (selected, *selected.parents):
            if path == root:
                break
            if path.is_symlink():
                raise ModuleStorageError("Module storage paths cannot contain symlinks")

    def _writable_root(self):
        if (Path(self.layout.root) / ".contextopus-freeze.json").exists():
            raise ModuleStorageError("Root is frozen for relocation")
        if legacy_pending(self.layout.root):
            raise ModuleStorageError("Legacy shared module storage requires explicit storage apply/install before writes")

    @contextmanager
    def _connection(self, *, write=False, create=False, deadline=None, cross_thread=False):
        if self.module is None:
            raise ModuleStorageError("A module-bound storage connection is required")
        selected = self.path if write else read_path(self.layout.root, self.module, self.path)
        self._safe_path(selected)
        if write:
            self._writable_root()
        check_deadline(deadline)
        if not selected.is_file() and not create:
            raise ModuleStorageError("Module storage is absent; explicitly prepare/apply its schema first")
        timeout = 5.0 if deadline is None else max(0.001, min(5.0, deadline - time.monotonic()))
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        mode = "rwc" if create else "rw" if write else "ro"
        conn = sqlite3.connect(selected.resolve().as_uri() + "?mode=" + mode,
                               uri=True, isolation_level=None, timeout=timeout,
                               check_same_thread=not cross_thread)
        try:
            conn.row_factory = sqlite3.Row
            # Some SQLite builds omit extension-loading support and its Python
            # API entirely. Disable it explicitly whenever the API is present;
            # module SQL also remains restricted by the authorizer below.
            disable_extensions = getattr(conn, "enable_load_extension", None)
            if disable_extensions is not None:
                disable_extensions(False)
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA trusted_schema=OFF")
            if not write:
                conn.execute("PRAGMA query_only=ON")
            if deadline is not None:
                conn.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
            yield conn
            # Once COMMIT succeeded, a late timeout must not claim the write
            # failed. Mutations check the deadline before their commit instead.
            if not write:
                check_deadline(deadline)
        except sqlite3.Error as exc:
            raise ModuleStorageError("Module storage SQL rejected or failed: " + str(exc)) from exc
        finally:
            conn.close()

    @staticmethod
    def _ledger(conn, module):
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (LEDGER,)).fetchone()
        if not exists:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchone():
                raise ModuleStorageError("Module storage contains tables without its Core migration ledger")
            return []
        return [dict(row) for row in conn.execute(
            f'SELECT version,name,checksum FROM "{LEDGER}" WHERE module=? ORDER BY version', (module,))]

    def _inspect(self, module, contract, package, conn=None):
        bound = self.for_module(module)
        if bound is not self:
            return bound._inspect(module, contract, package, conn)
        contract = validate_contract(contract)
        files = migration_files(contract, package)
        if conn is not None:
            applied = self._ledger(conn, module)
        elif read_path(self.layout.root, module, self.path).exists():
            with self._connection() as reader:
                applied = self._ledger(reader, module)
        else:
            self._safe_path()
            applied = []
        versions = [item["version"] for item in applied]
        if versions != list(range(1, len(versions) + 1)):
            raise ModuleStorageError("Core migration ledger has missing or invalid steps")
        current, target = len(versions), contract["schema_version"]
        for item in files:
            if item["version"] <= current:
                old = applied[item["version"] - 1]
                if (old["checksum"], old["name"]) != (item["checksum"], item["name"]):
                    raise ModuleStorageError("Applied migration changed: " + item["name"])
        bounds = contract["compatible_versions"]
        compatible = current == 0 or bounds["min"] <= current <= bounds["max"]
        layout_pending = legacy_pending(self.layout.root)
        schema_pending = current < target
        pending = schema_pending or layout_pending
        status = "pending" if pending else "current" if compatible else "incompatible"
        revision = hashlib.sha256(json.dumps({"module": module, "contract": contract,
            "files": [{k: item[k] for k in ("version", "name", "checksum")} for item in files],
            "applied": applied}, sort_keys=True).encode()).hexdigest()
        result = {"status": status, "current_version": current, "target_version": target,
                  "compatible": compatible, "needs_migration": pending, "needs_layout_migration": layout_pending, "errors": [],
                  "migrations": [{**{k: item[k] for k in ("version", "name", "checksum")},
                                  "applied": item["version"] <= current} for item in files],
                  "revision": revision}
        if not compatible and not schema_pending:
            result["errors"] = [f"Schema version {current} is unsupported by this module ({bounds['min']}..{bounds['max']}); no automatic downgrade"]
        return result, files

    def inspect(self, module, contract, package):
        """Inspect code/schema compatibility without creating directories or a DB."""
        try:
            return self._inspect(module, contract, package)[0]
        except (ModuleStorageError, OSError) as exc:
            return {"status": "error", "current_version": None, "target_version": None,
                    "compatible": False, "needs_migration": False, "errors": [str(exc)],
                    "migrations": [], "revision": None}

    def prepare(self, module, contract, package):
        result, _ = self._inspect(module, contract, package)
        if result["errors"]:
            raise ModuleStorageError("; ".join(result["errors"]))
        return result

    @staticmethod
    def _foreign_keys(conn, module):
        prefix = module + "::"
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            name = row["name"]
            if not name.startswith(prefix):
                continue
            quoted = '"' + name.replace('"', '""') + '"'
            for key in conn.execute("PRAGMA foreign_key_list(" + quoted + ")"):
                if not key["table"].startswith(prefix):
                    raise ModuleStorageError("Foreign keys must stay within their owning module")

    @staticmethod
    def _schema(conn):
        return {row["name"]: tuple(row) for row in conn.execute(
            "SELECT name,type,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}

    @staticmethod
    def _check_schema_changes(module, before, after):
        for name in set(before) | set(after):
            if before.get(name) != after.get(name) and name != LEDGER:
                if not name.startswith(module + "::"):
                    raise ModuleStorageError("Migration schema objects must stay within their owning module")

    def apply(self, module, contract, package, expected_revision):
        """Atomically migrate this module file and its Core-owned ledger."""
        bound = self.for_module(module)
        if bound is not self:
            return bound.apply(module, contract, package, expected_revision)
        if legacy_pending(self.layout.root):
            with self.layout.guard():
                # A nested root guard is reentrant and skips admission checks.
                # Reject a newly published freeze before changing legacy data.
                if (Path(self.layout.root) / ".contextopus-freeze.json").exists():
                    raise ModuleStorageError("Root is frozen for relocation")
                reviewed, _ = self._inspect(module, contract, package)
                if reviewed["revision"] != expected_revision:
                    raise ModuleStorageError("Storage preparation changed; prepare and review again")
                if reviewed["errors"]:
                    raise ModuleStorageError("; ".join(reviewed["errors"]))
                ensure_partitioned(self.layout.root)
        with self._write_guard():
            before, files = self._inspect(module, contract, package)
            if before["revision"] != expected_revision:
                raise ModuleStorageError("Storage preparation changed; prepare and review again")
            if before["errors"]:
                raise ModuleStorageError("; ".join(before["errors"]))
            if not before["needs_migration"]:
                return {**before, "applied_versions": []}
            with self._connection(write=True, create=True) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    locked, files = self._inspect(module, contract, package, conn)
                    if locked["revision"] != expected_revision:
                        raise ModuleStorageError("Storage changed; prepare and review again")
                    conn.execute(f'CREATE TABLE IF NOT EXISTS "{LEDGER}" (module TEXT NOT NULL, version INTEGER NOT NULL, name TEXT NOT NULL, checksum TEXT NOT NULL, PRIMARY KEY(module,version))')
                    migrated = []
                    for item in files:
                        if item["version"] <= before["current_version"]:
                            continue
                        old_schema = self._schema(conn)
                        conn.set_authorizer(authorize(module, write=True, migration=True))
                        for statement in statements(render(module, item["sql"])):
                            conn.execute(statement)
                        conn.set_authorizer(None)
                        self._check_schema_changes(module, old_schema, self._schema(conn))
                        conn.execute(f'INSERT INTO "{LEDGER}" VALUES (?,?,?,?)',
                                     (module, item["version"], item["name"], item["checksum"]))
                        migrated.append(item["version"])
                    self._foreign_keys(conn, module)
                    result, _ = self._inspect(module, contract, package, conn)
                    self._writable_root()
                    conn.execute("COMMIT")
                    return {**result, "applied_versions": migrated}
                except BaseException:
                    conn.set_progress_handler(None, 0)
                    conn.set_authorizer(None)
                    if conn.in_transaction:
                        conn.execute("ROLLBACK")
                    raise

    def query(self, module, sql, parameters=(), *, deadline=None):
        bound = self.for_module(module)
        if bound is not self:
            return bound.query(module, sql, parameters, deadline=deadline)
        sql = render(module, sql)
        with self._connection(deadline=deadline) as conn:
            conn.set_authorizer(authorize(module))
            cursor = conn.execute(sql, parameters)
            columns = [field[0] for field in cursor.description or ()]
            rows = [dict(row) for row in cursor.fetchall()]
            return {"columns": columns, "rows": rows}

    def execute(self, module, sql, parameters=(), *, deadline=None):
        bound = self.for_module(module)
        if bound is not self:
            return bound.execute(module, sql, parameters, deadline=deadline)
        sql = render(module, sql)
        self._safe_path()
        self._writable_root()
        if not self.path.is_file():
            raise ModuleStorageError("Module storage is absent; explicitly prepare/apply its schema first")
        with self._write_guard(deadline):
            with self._connection(write=True, deadline=deadline) as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    authorization = authorize(module, write=True)
                    conn.set_authorizer(authorization)
                    cursor = conn.execute(sql, parameters)
                    if not authorization.wrote:
                        raise ModuleStorageError("execute accepts domain DML only; use query for reads")
                    cursor.fetchall()
                    result = {"rowcount": cursor.rowcount, "lastrowid": cursor.lastrowid}
                    check_deadline(deadline)
                    self._writable_root()
                    conn.set_authorizer(None)
                    conn.execute("COMMIT")
                    return result
                except BaseException:
                    conn.set_progress_handler(None, 0)
                    conn.set_authorizer(None)
                    if conn.in_transaction:
                        conn.execute("ROLLBACK")
                    raise

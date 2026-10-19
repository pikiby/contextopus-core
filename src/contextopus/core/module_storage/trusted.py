"""Core-owned connections for trusted module contributions.

Domain schema belongs to the contribution. Unlike the subprocess SQL bridge,
this API deliberately grants trusted Python code a real SQLite connection.
Every writer still uses the same module-file lease and relocation admission.
"""

from contextlib import contextmanager
import hashlib
import json

from .contract import ModuleStorageError, migration_files, validate_contract
from .service import LEDGER
from .sql import statements, check_deadline


class NativeModuleStorage:
    def __init__(self, storage):
        if storage.module is None:
            raise ModuleStorageError("A module-bound storage connection is required")
        self.storage = storage
        self.path = storage.path

    @contextmanager
    def connect(self, *, write=True, create=False, deadline=None):
        if create and not write:
            raise ModuleStorageError("Read connections cannot create module storage")
        if not write:
            with self.storage._connection(deadline=deadline) as connection:
                yield connection
            return
        with self.storage._write_guard(deadline):
            with self.storage._connection(write=True, create=create, deadline=deadline) as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("BEGIN IMMEDIATE")
                try:
                    yield connection
                    check_deadline(deadline)
                    self.storage._writable_root()
                    if connection.in_transaction:
                        connection.execute("COMMIT")
                except BaseException:
                    connection.set_progress_handler(None, 0)
                    if connection.in_transaction:
                        connection.execute("ROLLBACK")
                    raise

    def prepare_import(self, source):
        from .trusted_import import prepare
        return prepare(self.storage, source)

    def apply_import(self, source, expected_revision):
        from .trusted_import import apply
        return apply(self.storage, source, expected_revision)

    @contextmanager
    def guard(self, resource, *, deadline=None):
        """Coordinate module-owned files with relocation, outside the root lock."""
        from .coordination import module_resource
        self.storage._writable_root()
        with module_resource(self.storage.layout, self.storage.module, resource, deadline):
            yield

    def prepare_schema(self, contract, package, *, connection=None):
        """Inspect explicit native schema migrations without creating storage."""
        contract = validate_contract(contract)
        files = migration_files(contract, package)
        if connection is None and self.path.exists():
            with self.connect(write=False) as reader:
                return self.prepare_schema(contract, package, connection=reader)
        applied = []
        if connection is not None:
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if LEDGER in names:
                applied = self.storage._ledger(connection, self.storage.module)
            elif names:
                from .trusted_import import _read_marker
                if _read_marker(connection) is None:
                    raise ModuleStorageError("Existing native schema has no migration ledger or import provenance")
        if [item["version"] for item in applied] != list(range(1, len(applied) + 1)):
            raise ModuleStorageError("Native schema migration ledger has missing steps")
        if len(applied) > contract["schema_version"]:
            raise ModuleStorageError("Native schema is newer than this module; no downgrade")
        for old, new in zip(applied, files):
            if (old["name"], old["checksum"]) != (new["name"], new["checksum"]):
                raise ModuleStorageError("Applied native migration changed: " + old["name"])
        basis = {"module": self.storage.module, "contract": contract, "applied": applied,
                 "migrations": [{key: item[key] for key in ("version", "name", "checksum")} for item in files]}
        return {**basis, "revision": hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest(),
                "current_version": len(applied), "target_version": contract["schema_version"],
                "needs_migration": len(applied) < contract["schema_version"]}

    def apply_schema(self, contract, package, expected_revision, *, upgrade=None):
        """Run only reviewed migrations, with optional module-owned legacy adaptation."""
        reviewed = self.prepare_schema(contract, package)
        if reviewed["revision"] != expected_revision:
            raise ModuleStorageError("Native schema changed; prepare and review again")
        with self.connect(create=True) as connection:
            locked = self.prepare_schema(contract, package, connection=connection)
            if locked["revision"] != expected_revision:
                raise ModuleStorageError("Native schema changed; prepare and review again")
            connection.execute(f'CREATE TABLE IF NOT EXISTS "{LEDGER}" (module TEXT NOT NULL, version INTEGER NOT NULL, name TEXT NOT NULL, checksum TEXT NOT NULL, PRIMARY KEY(module,version))')
            for item in migration_files(validate_contract(contract), package):
                if item["version"] <= locked["current_version"]:
                    continue
                if upgrade is not None:
                    upgrade(connection, item["version"])
                for statement in statements(item["sql"]):
                    connection.execute(statement)
                connection.execute(f'INSERT INTO "{LEDGER}" VALUES (?,?,?,?)',
                    (self.storage.module, item["version"], item["name"], item["checksum"]))
            return self.prepare_schema(contract, package, connection=connection)

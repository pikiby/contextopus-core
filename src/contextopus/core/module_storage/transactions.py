"""Bounded module SQL sessions; no root guard is retained between RPC calls."""

import math
import sqlite3
import threading
import time
import uuid

from .contract import ModuleStorageError, module_id
from .sql import authorize, check_deadline, render


class StorageTransactions:
    """One connection/transaction per child, serialized even during cleanup.

    A per-database writer lease may be released by a different cleanup thread.
    SQLite thread checks are disabled only for this explicitly locked session.
    The root guard admits a database writer briefly; the lease protects begin,
    statements and commit without retaining the root guard during SQLite work.
    """

    MAX_SECONDS = 5.0

    def __init__(self, storage, module):
        self.module = module_id(module)
        self.storage = storage.for_module(self.module)
        self._lock = threading.RLock()
        self._connection = self._context = self._id = self._deadline = None
        self._lease = None

    @property
    def active(self):
        with self._lock:
            return self._id is not None

    def begin(self, timeout_seconds=MAX_SECONDS, *, deadline=None):
        with self._lock:
            self.expire()
            if self.active:
                raise ModuleStorageError("Only one transaction may be active per Core session")
            if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
                    or not 0 < timeout_seconds <= self.MAX_SECONDS):
                raise ModuleStorageError("Transaction timeout_seconds must be greater than zero and at most 5")
            bound = time.monotonic() + timeout_seconds
            bound = min(bound, deadline) if deadline is not None else bound
            check_deadline(bound)
            self._lease = self.storage._acquire_write_gate(bound)
            try:
                context = self.storage._connection(write=True, deadline=bound, cross_thread=True)
                connection = context.__enter__()
                self._connection, self._context = connection, context
                connection.execute("BEGIN IMMEDIATE")
                check_deadline(bound)
                self._id, self._deadline = uuid.uuid4().hex, bound
            except BaseException:
                self._finish()
                raise
            return {"transaction_id": self._id}

    def _finish(self):
        connection, context = self._connection, self._context
        self._connection = self._context = self._id = self._deadline = None
        try:
            if connection is not None:
                connection.set_progress_handler(None, 0)
                connection.set_authorizer(None)
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
        finally:
            try:
                if context is not None:
                    context.__exit__(None, None, None)
            finally:
                lease, self._lease = self._lease, None
                if lease is not None:
                    lease.close()

    def expire(self):
        with self._lock:
            if self.active and time.monotonic() >= self._deadline:
                self._finish()
                return True
            return False

    def _require(self, transaction_id, deadline=None):
        if self.expire():
            raise ModuleStorageError("Module storage transaction deadline exceeded; transaction rolled back")
        if not isinstance(transaction_id, str) or not self.active or transaction_id != self._id:
            raise ModuleStorageError("Unknown or inactive transaction_id")
        effective = min(self._deadline, deadline) if deadline is not None else self._deadline
        check_deadline(effective)
        return effective

    def statement(self, transaction_id, sql, parameters=(), *, write=False, deadline=None):
        with self._lock:
            # An invalid foreign token cannot abort the owner's transaction.
            effective = self._require(transaction_id)
            try:
                effective = self._require(transaction_id, deadline)
                self.storage._safe_path()
                if write:
                    self.storage._writable_root()
                connection = self._connection
                milliseconds = max(1, int((effective - time.monotonic()) * 1000))
                connection.set_authorizer(None)
                connection.execute("PRAGMA busy_timeout=" + str(milliseconds))
                connection.set_progress_handler(lambda: int(time.monotonic() >= effective), 1000)
                authorization = authorize(self.module, write=write)
                connection.set_authorizer(authorization)
                cursor = connection.execute(render(self.module, sql), parameters)
                if write:
                    if not authorization.wrote:
                        raise ModuleStorageError("execute accepts domain DML only; use query for reads")
                    # Drain RETURNING so COMMIT cannot fail with a pending cursor.
                    cursor.fetchall()
                    result = {"rowcount": cursor.rowcount, "lastrowid": cursor.lastrowid}
                else:
                    result = {"columns": [field[0] for field in cursor.description or ()],
                              "rows": [dict(row) for row in cursor.fetchall()]}
                check_deadline(effective)
                connection.set_authorizer(None)
                return result
            except BaseException as exc:
                self._finish()
                if isinstance(exc, sqlite3.Error):
                    raise ModuleStorageError("Module storage SQL rejected or failed; transaction rolled back: " + str(exc)) from exc
                raise

    def commit(self, transaction_id, *, deadline=None):
        with self._lock:
            self._require(transaction_id)
            try:
                effective = self._require(transaction_id, deadline)
                self.storage._safe_path()
                self.storage._writable_root()
                self._connection.set_authorizer(None)
                self._connection.set_progress_handler(None, 0)
                milliseconds = max(1, int((effective - time.monotonic()) * 1000))
                self._connection.execute("PRAGMA busy_timeout=" + str(milliseconds))
                check_deadline(effective)
                self._connection.execute("COMMIT")
            except sqlite3.Error as exc:
                raise ModuleStorageError("Module storage commit failed: " + str(exc)) from exc
            finally:
                if self.active:
                    self._finish()
            return {"committed": True}

    def rollback(self, transaction_id):
        with self._lock:
            self._require(transaction_id)
            self._finish()
            return {"rolled_back": True}

    def close(self):
        with self._lock:
            if self.active:
                self._finish()

    def abort_owned(self, transaction_id):
        """Malformed calls with the owner's token cannot leave partial writes."""
        with self._lock:
            if self.active and transaction_id == self._id:
                self._finish()

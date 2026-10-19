"""Portable per-database writer leases and short root admission.

The root guard admits writers, but is released before any SQLite work. A
relocator holds that guard, then drains these leases before copying databases.
The same lock file/byte is used on Unix and Windows, including across processes.
"""

from contextlib import contextmanager, ExitStack
from pathlib import Path
import errno
import threading
import time
import weakref
import hashlib

from .. import locking
from ..storage import _root_lock
from .contract import ModuleStorageError, module_id


_GATES = weakref.WeakValueDictionary()
_GATES_LOCK = threading.Lock()
_ADMISSIONS = threading.local()


def _admissions():
    if not hasattr(_ADMISSIONS, "leases"):
        _ADMISSIONS.leases = {}
    return _ADMISSIONS.leases


def _admitted_database(layout, path, module):
    if module is None:
        return False
    module_id(module)
    root = Path(layout.root).resolve()
    # Bypass is limited to the database of the exact module whose live resource
    # lease this thread owns. Another module/root always needs new admission.
    return ((str(root), module) in _admissions()
            and Path(path).resolve() == root / "core/storage/modules" / (module + ".sqlite3"))


def _gate(path):
    with _GATES_LOCK:
        return _GATES.setdefault(str(Path(path).resolve()), threading.Lock())


def _bound(deadline):
    return min(time.monotonic() + 5.0, deadline) if deadline is not None else time.monotonic() + 5.0


def _retry(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ModuleStorageError("Module storage write deadline exceeded or storage is busy")
    time.sleep(min(.01, remaining))


class DatabaseWriteLease:
    def __init__(self, gate, stream):
        self.gate, self.stream = gate, stream

    def close(self):
        stream, self.stream = self.stream, None
        if stream is None:
            return
        try:
            locking.flock(stream, locking.LOCK_UN)
        finally:
            try:
                stream.close()
            finally:
                self.gate.release()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _safe_path(layout, path):
    path = Path(path)
    root = Path(layout.root).resolve()
    if not path.resolve().is_relative_to(root):
        raise ModuleStorageError("Module storage escapes the common root")
    for ancestor in (path, *path.parents):
        if ancestor == root:
            break
        if ancestor.is_symlink():
            raise ModuleStorageError("Module storage paths cannot contain symlinks")


def _try_acquire(layout, path, gate):
    _safe_path(layout, path)
    if not gate.acquire(blocking=False):
        return None
    stream = None
    try:
        path = Path(path)
        lock_path = path.with_name(path.name + ".lock")
        if lock_path.is_symlink():
            raise ModuleStorageError("Module storage lock paths cannot contain symlinks")
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = lock_path.open("a+b")
        try:
            locking.flock(stream, locking.LOCK_EX | locking.LOCK_NB)
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
            stream.close()
            stream = None
            gate.release()
            return None
        return DatabaseWriteLease(gate, stream)
    except BaseException:
        if stream is not None:
            stream.close()
        gate.release()
        raise


def acquire_database_write(layout, path, deadline=None, *, module=None):
    """Acquire a module lease without waiting for a database under root guard."""
    deadline = _bound(deadline)
    gate = _gate(path)
    _, local = _root_lock(layout.root)
    outer_guard = bool(getattr(local, "depth", 0))
    while True:
        if time.monotonic() >= deadline:
            raise ModuleStorageError("Module storage write deadline exceeded or storage is busy")
        try:
            if _admitted_database(layout, path, module):
                lease = _try_acquire(layout, path, gate)
            else:
                with layout.guard(deadline=deadline):
                    lease = _try_acquire(layout, path, gate)
        except TimeoutError as exc:
            raise ModuleStorageError("Module storage write deadline exceeded waiting for root admission") from exc
        if lease is not None:
            return lease
        if outer_guard:
            raise ModuleStorageError("Module storage is busy; retry outside the root guard")
        _retry(deadline)


@contextmanager
def database_write(layout, path, deadline=None, *, module=None):
    with acquire_database_write(layout, path, deadline, module=module):
        yield


@contextmanager
def module_resource(layout, module, resource, deadline=None):
    """Admit one module resource, retain its lease without retaining root lock."""
    module_id(module)
    if not isinstance(resource, str) or not resource:
        raise ModuleStorageError("Module resource name must be nonempty")
    root = Path(layout.root).resolve()
    path = root / "core/storage/module-leases" / module / (hashlib.sha256(resource.encode()).hexdigest() + ".lease")
    key = (str(root), module)
    existing = _admissions().get(key)
    if existing is not None:
        if existing != path:
            raise ModuleStorageError("Finish the current module resource before entering another")
        yield
        return
    with acquire_database_write(layout, path, deadline):
        _admissions()[key] = path
        try:
            yield
        finally:
            del _admissions()[key]


@contextmanager
def quiesce_module_writes(layout, deadline=None):
    """Drain module writers while the caller holds the root guard.

    Call before publishing a relocation freeze and retain through the snapshot.
    No new writer can pass root admission while the caller owns that guard.
    Include lock files because an admitted migration may not have created its
    database yet. Do not remove lock files: doing so splits process ownership.
    """
    _, local = _root_lock(layout.root)
    if not getattr(local, "depth", 0):
        raise RuntimeError("Quiescing module storage requires the root guard")
    deadline = _bound(deadline)
    directory = Path(layout.root) / "core/storage/modules"
    _safe_path(layout, directory)
    paths = set(directory.glob("*.sqlite3"))
    paths.update(Path(str(path)[:-5]) for path in directory.glob("*.sqlite3.lock"))
    legacy = Path(layout.root) / "core/storage/modules.sqlite3"
    _safe_path(layout, legacy)
    if legacy.exists() or legacy.with_name(legacy.name + ".lock").exists():
        paths.add(legacy)
    resources = Path(layout.root) / "core/storage/module-leases"
    _safe_path(layout, resources)
    resource_paths = sorted(Path(str(path)[:-5]) for path in resources.glob("*/*.lease.lock"))
    with ExitStack() as leases:
        # Drain admitted module scopes first: they may still need their own
        # database lease to finish. Holding a database first would deadlock them.
        for path in [*resource_paths, *sorted(paths)]:
            gate = _gate(path)
            while True:
                lease = _try_acquire(layout, path, gate)
                if lease is not None:
                    leases.enter_context(lease)
                    break
                _retry(deadline)
        yield

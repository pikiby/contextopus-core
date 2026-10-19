"""A reentrant cross-process lifecycle gate, acquired before the root guard.

Child Core calls never acquire this gate. Module dependency preparation and
child shutdown can therefore wait here without blocking unrelated root work.
"""
from contextlib import contextmanager
from pathlib import Path
import threading

from .. import locking

_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


@contextmanager
def module_lifecycle(root):
    root = Path(root).resolve()
    with _LOCKS_GUARD:
        mutex, local = _LOCKS.setdefault(str(root), (threading.RLock(), threading.local()))
    with mutex:
        if getattr(local, 'depth', 0) or not root.exists():
            local.depth = getattr(local, 'depth', 0) + 1
            try:
                yield
            finally:
                local.depth -= 1
            return
        runtime = root / 'runtime'
        runtime.mkdir(exist_ok=True)
        with (runtime / 'module-lifecycle.lock').open('a+b') as stream:
            locking.flock(stream, locking.LOCK_EX)
            local.depth = 1
            try:
                yield
            finally:
                local.depth = 0
                locking.flock(stream, locking.LOCK_UN)

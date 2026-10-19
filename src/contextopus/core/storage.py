"""Open storage layout and explicit root-wide advisory locks."""

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from contextopus.core import locking as fcntl
import json
import errno
import threading
import time

_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def _root_lock(root):
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(str(root), (threading.RLock(), threading.local()))


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Root guard deadline exceeded")
    return min(.01, remaining)


@dataclass(frozen=True)
class StorageLayout:
    root: Path

    def __post_init__(self):
        object.__setattr__(self, "root", Path(self.root).expanduser().resolve())

    @property
    def rag(self):
        return self.root / "core/rag"

    @property
    def analytics(self):
        return self.root / "core/analytics"

    @property
    def configuration(self):
        return self.root / "core/configuration"

    def module_data(self, module):
        self._name(module)
        return self.root / 'modules' / module / 'data'

    def module_config(self, module):
        self._name(module)
        return self.root / 'modules' / module / 'config'

    @staticmethod
    def _name(name):
        if (
            not isinstance(name, str)
            or not name
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
        ):
            raise ValueError("Invalid context name")

    @contextmanager
    def guard(self, frozen_revision=None, deadline=None):
        """Hold root admission, optionally bounded by a monotonic deadline."""
        mutex, local = _root_lock(self.root)
        if deadline is None:
            mutex.acquire()
        else:
            while not mutex.acquire(timeout=_remaining(deadline)):
                pass
        try:
            if getattr(local, "depth", 0):
                local.depth += 1
                try:
                    yield
                finally:
                    local.depth -= 1
                return
            self.root.mkdir(parents=True, exist_ok=True)
            with (self.root / ".contextopus.lock").open("a+b") as stream:
                if deadline is None:
                    fcntl.flock(stream, fcntl.LOCK_EX)
                else:
                    while True:
                        _remaining(deadline)
                        try:
                            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except OSError as exc:
                            if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                                raise
                            time.sleep(_remaining(deadline))
                local.depth = 1
                try:
                    if (self.root / ".contextopus-freeze.json").exists():
                        frozen = json.loads(
                            (self.root / ".contextopus-freeze.json").read_text()
                        )
                        if (
                            frozen_revision is None
                            or frozen.get("revision") != frozen_revision
                        ):
                            raise RuntimeError("Root is frozen for relocation")
                    yield
                finally:
                    local.depth = 0
                    fcntl.flock(stream, fcntl.LOCK_UN)
        finally:
            mutex.release()

    @classmethod
    def resolve(cls, root):
        root = Path(root).expanduser().resolve()
        seen = set()
        while (root / ".contextopus-redirect.json").is_file():
            if root in seen:
                raise ValueError("Relocation redirect loop")
            seen.add(root)
            record = json.loads((root / ".contextopus-redirect.json").read_text())
            target = Path(record["destination"]).resolve()
            receipt = target / ".contextopus-receipt.json"
            if (
                not receipt.is_file()
                or json.loads(receipt.read_text()).get("revision") != record["revision"]
            ):
                raise ValueError("Relocation receipt is absent or mismatched")
            root = target
        return cls(root)


def sync_directory(path):
    """Persist a directory entry where the OS exposes directory fsync."""
    import os

    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

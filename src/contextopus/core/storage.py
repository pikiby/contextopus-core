"""Open storage layout and explicit root-wide advisory locks."""

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from contextopus.core import locking as fcntl
import json
import threading

_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def _root_lock(root):
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(str(root), (threading.RLock(), threading.local()))


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

    def workspace(self, name):
        self._name(name)
        return self.root / "modules/workspace/workspace_contexts" / name

    def control(self, name):
        self._name(name)
        return self.root / "modules/workspace/control" / name

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

    @property
    def legacy(self):
        return (
            not (self.root / "modules/workspace").is_dir()
            and not (self.configuration / "layout.json").is_file()
        )

    @property
    def workspace_base(self):
        return (
            self.root / ".pcw"
            if self.legacy
            else self.root / "modules/workspace/workspace_contexts"
        )

    @property
    def workspace_rag(self):
        return self.root / ".pcw/.rag" if self.legacy else self.rag

    @contextmanager
    def guard(self, frozen_revision=None):
        mutex, local = _root_lock(self.root)
        with mutex:
            if getattr(local, "depth", 0):
                local.depth += 1
                try:
                    yield
                finally:
                    local.depth -= 1
                return
            self.root.mkdir(parents=True, exist_ok=True)
            with (self.root / ".contextopus.lock").open("a+b") as stream:
                fcntl.flock(stream, fcntl.LOCK_EX)
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

"""Verified copy relocation with retained source and fail-closed legacy namespace.

No serialized approval or proposal is rewritten. Absolute legacy coordinates are
resolved using the checked relocation receipt, rather than text substitution.
"""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile
from contextlib import ExitStack, closing
from .storage import StorageLayout
from . import locking

_INTERNAL = {
    ".contextopus.lock",
    ".contextopus-freeze.json",
    ".contextopus-redirect.json",
    ".contextopus-receipt.json",
    ".contextopus-relocation-owner.json",
    ".contextopus-retained",
}


def _transient(relative):
    return str(relative) in {"runtime", "runtime/service.json", "runtime/service.log"}


def _digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def _write(path, value):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".contextopus-write-",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        from .storage import sync_directory

        sync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _safe(root, relative):
    path = root.joinpath(*_relative(relative).parts)
    for candidate in (path, *path.parents):
        if candidate == root:
            break
        if candidate.is_symlink():
            raise ValueError("Relocation refuses symlink path components")
    if not path.resolve(strict=False).is_relative_to(root):
        raise ValueError("Relocation path escapes root")
    return path


def _relative(value):
    path = PurePosixPath(value)
    if (
        not isinstance(value, str)
        or not value
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
    ):
        raise ValueError("Unsafe relocation path")
    return path


def _target(relative):
    parts = PurePosixPath(relative).parts
    if parts[0] != ".pcw":
        return relative
    if len(parts) < 2:
        return "modules/workspace"
    name = parts[1]
    suffix = parts[2:]
    if name == ".rag":
        return str(PurePosixPath("core/rag", *suffix))
    if name == ".analytics":
        return str(PurePosixPath("core/analytics", *suffix))
    if name == ".control":
        return str(PurePosixPath("modules/workspace/control", *suffix))
    return str(PurePosixPath("modules/workspace/workspace_contexts", name, *suffix))


def _sqlite_backup(source, target):
    with closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            dst.execute("PRAGMA journal_mode=DELETE")
            dst.commit()
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise IOError("SQLite backup integrity failed")


def _files(root):
    entries = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts[0] in _INTERNAL or _transient(relative.as_posix()):
            continue
        if path.is_symlink():
            raise ValueError(f"Relocation refuses symlinks: {relative}")
        if path.is_file():
            entries.append(path)
    return entries


def _observer_path(relative):
    parts = PurePosixPath(relative).parts
    return parts[:2] in {("core", "analytics"), (".pcw", ".analytics")}


def _revision(value):
    binding = {k: v for k, v in value.items() if k not in {"revision", "state"}}
    binding["files"] = [
        entry for entry in value["files"] if not _observer_path(entry["path"])
    ]
    binding["directories"] = [
        entry for entry in value["directories"] if not _observer_path(entry["path"])
    ]
    return hashlib.sha256(
        json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _entries(files):
    entries = []
    sqlite_paths = set()
    for relative, path in files:
        with path.open("rb") as stream:
            header = stream.read(16)
        if header == b"SQLite format 3\x00":
            sqlite_paths.add(relative)
    for relative, path in files:
        entry = {
            "path": relative,
            "target": _target(relative),
            "size": path.stat().st_size,
            "sha256": _digest(path),
            "mode": path.stat().st_mode & 0o777,
            "kind": "binary",
        }
        if _observer_path(relative):
            entry["snapshot"] = "refresh_under_freeze"
        if relative in sqlite_paths:
            with tempfile.TemporaryDirectory(
                prefix="contextopus-sqlite-preview-"
            ) as temp:
                backup = Path(temp) / "backup.sqlite"
                _sqlite_backup(path, backup)
                entry.update(kind="sqlite", output_sha256=_digest(backup))
        elif any(
            relative == base + suffix
            for base in sqlite_paths
            for suffix in ("-wal", "-shm")
        ):
            entry["target"] = "core/relocation/raw/" + relative
        entries.append(entry)
    return entries


def plan(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if (
        source == destination
        or source in destination.parents
        or destination in source.parents
    ):
        raise ValueError("Source and destination must be disjoint")
    if not source.is_dir():
        raise ValueError("Source root is absent")
    entries = _entries(
        [(path.relative_to(source).as_posix(), path) for path in _files(source)]
    )
    directories = [
        {
            "path": p.relative_to(source).as_posix(),
            "target": _target(p.relative_to(source).as_posix()),
        }
        for p in sorted(source.rglob("*"))
        if p.is_dir()
        and p.relative_to(source).parts[0] not in _INTERNAL
        and not _transient(p.relative_to(source).as_posix())
    ]
    value = {
        "source": str(source),
        "destination": str(destination),
        "files": entries,
        "directories": directories,
        "version": 1,
        "observer_snapshot": "Known analytics directories are refreshed under the apply freeze; authoring and index bytes remain revision-bound.",
    }
    value["revision"] = _revision(value)
    return value


def _refresh_observers(source, proposal):
    files = []
    for logical in ("core/analytics", ".pcw/.analytics"):
        root = _source_path(source, {"path": logical}, proposal["revision"])
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_symlink():
                    raise ValueError("Observer snapshot refuses symlinks")
                if path.is_file():
                    files.append(
                        (logical + "/" + path.relative_to(root).as_posix(), path)
                    )
    return {
        **proposal,
        "files": [
            entry for entry in proposal["files"] if not _observer_path(entry["path"])
        ]
        + _entries(files),
    }


def _validate(proposal):
    if proposal.get("version") != 1 or proposal.get("revision") != _revision(proposal):
        raise ValueError("Relocation plan revision mismatch")
    source, destination = Path(proposal["source"]), Path(proposal["destination"])
    if (
        not source.is_absolute()
        or source.resolve() != source
        or not destination.is_absolute()
        or destination.resolve() != destination
    ):
        raise ValueError("Relocation roots must be canonical absolute paths")
    if (
        source == destination
        or source in destination.parents
        or destination in source.parents
    ):
        raise ValueError("Overlapping relocation roots")
    targets = set()
    for entry in proposal["files"]:
        _relative(entry["path"])
        _relative(entry["target"])
        expected = _target(entry["path"])
        if (
            entry["target"] != expected
            and entry["target"] != "core/relocation/raw/" + entry["path"]
        ):
            raise ValueError("Invalid relocation mapping")
        if entry["target"] in targets:
            raise ValueError("Duplicate relocation target")
        targets.add(entry["target"])
    for entry in proposal["directories"]:
        _relative(entry["path"])
        _relative(entry["target"])
    return source, destination


def _source_path(source, entry, revision):
    relative = PurePosixPath(entry["path"])
    retained = source / ".contextopus-retained" / revision
    if relative.parts[0] == ".pcw" and (retained / ".pcw").is_dir():
        return _safe(
            source,
            str(PurePosixPath(".contextopus-retained", revision, *relative.parts)),
        )
    return _safe(source, str(relative))


def _verify_source(source, proposal):
    revision = proposal["revision"]
    retained = source / ".contextopus-retained" / revision / ".pcw"
    actual = {path.relative_to(source).as_posix() for path in _files(source)}
    if retained.is_dir():
        actual.discard(".pcw")
        for path in retained.rglob("*"):
            if path.is_symlink():
                raise ValueError("Retained source contains a symlink")
            if path.is_file():
                actual.add(".pcw/" + path.relative_to(retained).as_posix())
    actual = {path for path in actual if not _observer_path(path)}
    expected = {
        entry["path"]
        for entry in proposal["files"]
        if not _observer_path(entry["path"])
    }
    if actual != expected:
        raise ValueError(
            "Source changed after relocation preview: file inventory differs"
        )
    for entry in proposal["files"]:
        if _observer_path(entry["path"]):
            continue
        path = _source_path(source, entry, revision)
        if not path.is_file() or path.is_symlink() or _digest(path) != entry["sha256"]:
            raise ValueError(
                "Source changed after relocation preview: " + entry["path"]
            )


def _verify_target(destination, proposal):
    for entry in proposal["files"]:
        path = _safe(destination, entry["target"])
        expected = entry.get("output_sha256", entry["sha256"])
        mutable_observer = (
            proposal.get("state") == "complete"
            and _observer_path(entry["path"])
            and entry["kind"] == "sqlite"
        )
        if (
            not path.is_file()
            or path.is_symlink()
            or not mutable_observer
            and _digest(path) != expected
        ):
            raise ValueError("Destination verification failed: " + entry["target"])
        if entry["kind"] == "sqlite":
            raw = _safe(destination, "core/relocation/raw/" + entry["path"])
            if not raw.is_file() or _digest(raw) != entry["sha256"]:
                raise ValueError("SQLite binary snapshot missing")
            if mutable_observer:
                with closing(
                    sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
                ) as database:
                    if database.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                        raise ValueError("Active observer database is corrupt")


def apply(proposal):
    source, destination = _validate(proposal)
    revision = proposal["revision"]
    receipt = destination / ".contextopus-receipt.json"
    if receipt.exists():
        if json.loads(receipt.read_text()).get("revision") != revision:
            raise ValueError("Destination belongs to another relocation")
        _verify_target(destination, json.loads(receipt.read_text()))
        _write(
            source / ".contextopus-redirect.json",
            {"destination": str(destination), "revision": revision},
        )
        return {
            "status": "complete",
            "revision": revision,
            "destination": str(destination),
        }
    owner = destination / ".contextopus-relocation-owner.json"
    freeze = source / ".contextopus-freeze.json"
    if freeze.exists() and json.loads(freeze.read_text()).get("revision") != revision:
        raise ValueError("Another relocation is pending")
    with ExitStack() as locks:
        locks.enter_context(StorageLayout(source).guard(frozen_revision=revision))
        if not freeze.exists():
            _verify_source(source, proposal)
            if destination.exists() and any(destination.iterdir()):
                raise ValueError("Destination is not empty")
        # Exclude all operations in the old engine before replacing its path.
        if (source / ".pcw").is_dir():
            candidates = [
                source / ".pcw/.rag/lock",
                *sorted((source / ".pcw/.control").glob("*/lock")),
                *sorted((source / ".pcw").glob("*/.pcw-runtime/lock")),
            ]
            for path in candidates:
                if path.is_file():
                    stream = locks.enter_context(path.open("a+b"))
                    locking.flock(stream.fileno(), locking.LOCK_EX | locking.LOCK_NB)
            if not freeze.exists():
                _write(freeze, {"revision": revision, "destination": str(destination)})
            legacy = source / ".pcw"
            if legacy.is_dir():
                retained = source / ".contextopus-retained" / revision
                retained.mkdir(parents=True, exist_ok=True)
                os.replace(legacy, retained / ".pcw")
                _write(
                    legacy,
                    {
                        "state": "relocation_frozen",
                        "revision": revision,
                        "destination": str(destination),
                    },
                )
        retained = source / ".contextopus-retained" / revision / ".pcw"
        if retained.is_dir() and not (source / ".pcw").exists():
            _write(
                source / ".pcw",
                {
                    "state": "relocation_frozen",
                    "revision": revision,
                    "destination": str(destination),
                },
            )
        if not freeze.exists():
            _write(freeze, {"revision": revision, "destination": str(destination)})
        _verify_source(source, proposal)
        proposal = _refresh_observers(source, proposal)
        if destination.exists() and any(destination.iterdir()):
            if (
                not owner.exists()
                or json.loads(owner.read_text()).get("revision") != revision
            ):
                raise ValueError("Destination has no matching relocation ownership")
        destination.mkdir(parents=True, exist_ok=True)
        ownership = (
            json.loads(owner.read_text()) if owner.exists() else {"revision": revision}
        )
        accepted = ownership.setdefault("observer_hashes", {})
        for entry in proposal["files"]:
            if _observer_path(entry["path"]):
                hashes = accepted.setdefault(entry["target"], [])
                expected = entry.get("output_sha256", entry["sha256"])
                if expected not in hashes:
                    hashes.append(expected)
                if entry["kind"] == "sqlite":
                    raw_hashes = accepted.setdefault(
                        "core/relocation/raw/" + entry["path"], []
                    )
                    if entry["sha256"] not in raw_hashes:
                        raw_hashes.append(entry["sha256"])
        _write(owner, ownership)
        for directory in proposal["directories"]:
            _safe(destination, directory["target"]).mkdir(parents=True, exist_ok=True)
        for entry in proposal["files"]:
            src = _source_path(source, entry, revision)
            dst = _safe(destination, entry["target"])
            dst.parent.mkdir(parents=True, exist_ok=True)
            expected = entry.get("output_sha256", entry["sha256"])
            needs_copy = not dst.exists()
            if dst.exists():
                actual = _digest(dst)
                if dst.is_symlink() or actual != expected:
                    if _observer_path(entry["path"]) and actual in accepted.get(
                        entry["target"], []
                    ):
                        needs_copy = True
                    else:
                        raise ValueError(
                            "Refusing to overwrite changed target: " + entry["target"]
                        )
            if needs_copy:
                part = dst.with_name(dst.name + ".relocating")
                if part.exists():
                    part.unlink()
                if entry["kind"] == "sqlite":
                    _sqlite_backup(src, part)
                else:
                    shutil.copy2(src, part)
                if _digest(part) != expected:
                    raise IOError("Copy checksum mismatch")
                os.chmod(part, entry["mode"])
                os.replace(part, dst)
            if entry["kind"] == "sqlite":
                raw = _safe(destination, "core/relocation/raw/" + entry["path"])
                raw.parent.mkdir(parents=True, exist_ok=True)
                needs_raw = not raw.exists()
                if raw.exists() and _digest(raw) != entry["sha256"]:
                    relative = "core/relocation/raw/" + entry["path"]
                    if _observer_path(entry["path"]) and _digest(raw) in accepted.get(
                        relative, []
                    ):
                        needs_raw = True
                    else:
                        raise ValueError("SQLite raw snapshot conflict")
                if needs_raw:
                    shutil.copy2(src, raw)
        _verify_target(destination, proposal)
        record = {**proposal, "state": "complete"}
        _write(receipt, record)
        _write(
            source / ".contextopus-redirect.json",
            {"destination": str(destination), "revision": revision},
        )
    return {
        "status": "complete",
        "revision": revision,
        "destination": str(destination),
        "source_preserved": True,
    }


def rollback(proposal):
    source, destination = _validate(proposal)
    if (source / ".contextopus-redirect.json").exists() or (
        destination / ".contextopus-receipt.json"
    ).exists():
        raise ValueError("Published relocation cannot be rolled back")
    freeze = source / ".contextopus-freeze.json"
    if freeze.exists():
        if json.loads(freeze.read_text()).get("revision") != proposal["revision"]:
            raise ValueError("Freeze revision mismatch")
        _verify_source(source, proposal)
        retained = source / ".contextopus-retained" / proposal["revision"] / ".pcw"
        if retained.is_dir():
            tombstone = source / ".pcw"
            if tombstone.exists():
                if (
                    not tombstone.is_file()
                    or json.loads(tombstone.read_text()).get("revision")
                    != proposal["revision"]
                ):
                    raise ValueError("Legacy tombstone changed")
                tombstone.unlink()
            os.replace(retained, tombstone)
        freeze.unlink()
    return {
        "status": "rolled_back",
        "source_preserved": True,
        "partial_destination": str(destination),
    }


def checked_alias(layout, path):
    """Map a recorded absolute source coordinate after validating the receipt."""
    path = Path(path)
    if path.is_relative_to(layout.root):
        return path
    receipt = layout.root / ".contextopus-receipt.json"
    if not receipt.is_file():
        raise ValueError("Path is outside this root")
    record = json.loads(receipt.read_text())
    source = Path(record["source"])
    try:
        relative = path.relative_to(source).as_posix()
    except ValueError as exc:
        raise ValueError("Path is outside relocation source") from exc
    _relative(relative)
    allowed = {entry["path"] for entry in record["files"]} | {
        entry["path"] for entry in record["directories"]
    }
    if relative not in allowed:
        raise ValueError("Path was not part of the relocation manifest")
    mapped = layout.root / _target(relative)
    if mapped.is_symlink() or not mapped.resolve().is_relative_to(layout.root):
        raise ValueError("Relocated alias escapes root")
    return mapped

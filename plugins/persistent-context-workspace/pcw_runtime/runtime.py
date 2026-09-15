"""Knowledge is authoritative; LanceDB contains replaceable search representations.

There is deliberately no source-project reader, language-model splitter, remote
push, background service, or hidden embedding fallback in this module.
"""
from __future__ import annotations

import contextlib
import copy
import dataclasses
from datetime import datetime, timezone
from array import array
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import statistics
import subprocess
import tempfile
import threading
from typing import Any, Callable
import uuid

import lancedb
import pyarrow as pa
import yaml

from .embeddings import create_provider, default_config, embedding_identity, validate_config
from .provider_pool import PROCESS_PROVIDERS


class PCWError(ValueError):
    """An actionable memory error; completed multi-file writes are not rolled back."""


@dataclasses.dataclass(frozen=True)
class SearchConfig:
    # Engineering starting values, explicitly NOT empirically calibrated for PCW.
    N: int = 20
    d_max: float = 0.8
    min_jump: float = 0.02
    multiplier: float = 3.0
    metric: str = "cosine"

    def __post_init__(self):
        if isinstance(self.N, bool) or not isinstance(self.N, int) or not 1 <= self.N <= 1000:
            raise PCWError("N must be an integer between 1 and 1000")
        for field in ("d_max", "min_jump", "multiplier"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
                raise PCWError(f"{field} must be a finite nonnegative number")
        if self.min_jump <= 0 or self.multiplier <= 0:
            raise PCWError("min_jump and multiplier must be positive")
        if self.metric not in {"cosine", "l2"}:
            raise PCWError("metric must be cosine or l2 (squared Euclidean distance)")


def select_candidates(rows: list[dict], config: SearchConfig) -> list[dict]:
    """Apply N, d_max, first median-positive-gap jump, then material deduplication."""
    ordered = sorted(rows, key=lambda row: row["distance"])[:config.N]
    kept = [row for row in ordered if math.isfinite(row["distance"]) and row["distance"] <= config.d_max]
    if len(kept) >= 3:
        gaps = [b["distance"] - a["distance"] for a, b in zip(kept, kept[1:])]
        positive = [gap for gap in gaps if gap > 0]
        if positive:
            threshold = max(config.min_jump, statistics.median(positive) * config.multiplier)
            for index, gap in enumerate(gaps):
                if gap >= threshold:
                    kept = kept[:index + 1]
                    break
    unique = {}
    for row in kept:
        unique.setdefault(row["id"], row)
    return list(unique.values())


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_FRONT = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)


def _id(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise PCWError("Material ID must be an exact safe filename")
    return value


def _revision(content: str) -> str:
    # Only the saved knowledge body, never source-project files, is hashed.
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _unique_links(values: list[str], own_id: str) -> list[str]:
    if not isinstance(values, list):
        raise PCWError("links must be a list of exact IDs")
    return list(dict.fromkeys(_id(value) for value in values if value != own_id))


@dataclasses.dataclass
class Material:
    id: str
    path: str
    metadata: dict
    content: str
    revision: str = dataclasses.field(init=False)

    def __post_init__(self):
        self.revision = _revision(self.content)

    def set_content(self, content: str):
        self.content = content
        self.revision = _revision(content)

    @property
    def links(self):
        return self.metadata["links"]


def _parse(text: str) -> tuple[dict, str]:
    match = _FRONT.match(text)
    if not match:
        return {}, text
    try:
        metadata = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        raise PCWError("Invalid knowledge YAML frontmatter") from exc
    if not isinstance(metadata, dict):
        raise PCWError("Knowledge frontmatter must be a mapping")
    return metadata, text[match.end():]


class PCWRuntime:
    """One explicitly selected workspace. All managed writes stay below .pcw.

    provider_factory is an injection seam for tests. Production MCP always uses
    create_provider, and LanceDB is mandatory for both test and production runs.
    """

    def __init__(self, work_root: str | Path, workspace: str,
                 provider_factory: Callable = PROCESS_PROVIDERS.acquire):
        raw_root = Path(work_root)
        if not raw_root.is_absolute() or not raw_root.is_dir():
            raise PCWError("work_root must be an existing absolute directory")
        if not _ID.fullmatch(workspace) or workspace in {".", ".."}:
            raise PCWError("workspace must be one safe directory name")
        self.work_root = raw_root.resolve()
        self.root = self.work_root / ".pcw" / workspace
        self.knowledge = self.root / "knowledge"
        self.state = self.root / ".pcw-runtime"
        self._factory = provider_factory
        self._provider = None
        self._provider_config = None
        self._mutex = threading.RLock()
        self._depth = 0
        self._file_cache = {}
        self._reconciled_token = None
        self._assert_safe(self.state / "lancedb")
        self.knowledge.mkdir(parents=True, exist_ok=True)
        self.state.mkdir(parents=True, exist_ok=True)
        with self._guard():
            pass

    def _assert_safe(self, path: Path):
        try:
            path.relative_to(self.work_root / ".pcw")
        except ValueError as exc:
            raise PCWError("Path is outside selected .pcw storage") from exc
        for candidate in (self.work_root / ".pcw", *path.parents, path):
            if candidate == self.work_root or self.work_root not in candidate.parents:
                continue
            if candidate.is_symlink():
                raise PCWError(f"Symlinks are not allowed in memory paths: {candidate}")
        if not path.resolve(strict=False).is_relative_to(self.root):
            raise PCWError("Path escapes the selected memory workspace")

    def _knowledge_path(self, relative: str) -> Path:
        if not isinstance(relative, str) or "\\" in relative:
            raise PCWError("Use a relative knowledge path with forward slashes")
        parts = PurePosixPath(relative)
        if parts.is_absolute() or not parts.parts or any(p in {"..", "."} or p.startswith(".") for p in parts.parts):
            raise PCWError("Knowledge path must not traverse or use hidden files")
        if parts.suffix != ".md":
            raise PCWError("Knowledge materials must have the .md extension")
        path = self.knowledge.joinpath(*parts.parts)
        self._assert_safe(path)
        return path

    @staticmethod
    def _material_id(path: Path) -> str:
        """The filename, including .md, is the sole material identity."""
        return _id(path.name)

    def _write(self, path: Path, text: str):
        self._assert_safe(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                             dir=path.parent, prefix=".pcw-write-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            # Durability of the active-pointer rename includes its parent entry.
            descriptor = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def _save(self, material: Material):
        header = yaml.safe_dump(material.metadata, sort_keys=False, allow_unicode=True)
        self._write(self.root / material.path, f"---\n{header}---\n{material.content}")

    def _write_active(self, active: dict):
        self._write(self.state / "active.json", json.dumps(active, ensure_ascii=False, indent=2) + "\n")

    @staticmethod
    def _schema(dimensions: int):
        return pa.schema([
            ("material_id", pa.string()), ("part_index", pa.int32()),
            ("text", pa.string()), ("vector", pa.list_(pa.float32(), dimensions)),
            ("path", pa.string()), ("revision", pa.string()),
        ])

    @contextlib.contextmanager
    def _guard(self):
        with self._mutex:
            if self._depth:
                self._depth += 1
                try:
                    yield
                finally:
                    self._depth -= 1
                return
            self._assert_safe(self.state / "lock")
            with (self.state / "lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                self._depth = 1
                try:
                    self._assert_safe(self.state / "active.json")
                    self._assert_safe(self.state / "lancedb")
                    self.db = lancedb.connect(str(self.state / "lancedb"))
                    active_path = self.state / "active.json"
                    if not active_path.exists():
                        config = default_config()
                        name = "parts_" + uuid.uuid4().hex
                        self.db.create_table(name, schema=self._schema(config["profile"]["dimensions"]))
                        self._write_active({"config": config, "table": name,
                                            "search": dataclasses.asdict(SearchConfig()),
                                            "search_calibration": "engineering defaults; not calibrated on PCW"})
                    self.active = json.loads(active_path.read_text(encoding="utf-8"))
                    self.table = self.db.open_table(self.active["table"])
                    self._scan()
                    self._reconcile()
                    yield
                finally:
                    self._depth = 0
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def _scan(self):
        self.materials: dict[str, Material] = {}
        self.unregistered = []
        self._legacy_ids: dict[str, str] = {}
        self._legacy_id_paths: set[str] = set()
        self._legacy_link_paths: set[str] = set()
        cache = {}
        found = []
        found_ids = set()
        self._assert_safe(self.knowledge)
        for path in sorted(self.knowledge.rglob("*.md")):
            if any(part.startswith(".") for part in path.relative_to(self.knowledge).parts):
                continue
            self._assert_safe(path)
            if not path.is_file():
                continue
            relative = path.relative_to(self.root).as_posix()
            stat = path.stat()
            signature = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
            cached = self._file_cache.get(relative)
            if cached is not None and cached[0] == signature:
                metadata, body, revision = copy.deepcopy(cached[1:])
            else:
                metadata, body = _parse(path.read_bytes().decode("utf-8"))
                revision = _revision(body)
            cache[relative] = (signature, copy.deepcopy(metadata), body, revision)
            ident = self._material_id(path)
            if ident in found_ids:
                raise PCWError(f"Duplicate material filename ID: {ident}")
            found_ids.add(ident)
            # A legacy id is retained only as migration input. It is never used
            # to address the material during normal runtime operations.
            legacy_id = metadata.get("id")
            if legacy_id is not None:
                legacy_id = _id(legacy_id)
                previous = self._legacy_ids.get(legacy_id)
                if previous is not None and previous != ident:
                    raise PCWError(f"Duplicate legacy material ID: {legacy_id}")
                self._legacy_ids[legacy_id] = ident
                self._legacy_id_paths.add(relative)
            found.append((ident, relative, metadata, body, revision))

        for ident, relative, metadata, body, revision in found:
            raw_links = metadata.get("links", [])
            if not isinstance(raw_links, list):
                raise PCWError(f"links must be a list in {relative}")
            canonical_links = _unique_links(
                [self._legacy_ids.get(_id(value), _id(value)) for value in raw_links], ident)
            if canonical_links != raw_links:
                self._legacy_link_paths.add(relative)
            # Missing links are a valid empty navigation list. Do not write the
            # file merely because it is an older plain Markdown material.
            metadata["links"] = canonical_links
            material = Material.__new__(Material)
            material.id, material.path, material.metadata = ident, relative, metadata
            material.content, material.revision = body, revision
            self.materials[ident] = material
        self._file_cache = cache
        self._content_signature = tuple((material.id, material.path, material.revision)
                                        for material in self.materials.values())

    def _rows(self, columns=None) -> list[dict]:
        query = self.table.search()
        if columns is not None:
            query = query.select(columns)
        return query.limit(None).to_list()

    def _delete_rows(self, ident: str):
        _id(ident)
        aliases = [ident] + [old for old, target in self._legacy_ids.items() if target == ident]
        for value in dict.fromkeys(aliases):
            self.table.delete(f"material_id = '{_id(value)}'")

    def _reconcile(self):
        """Reconcile saved memory only, including externally restored Git content."""
        token = (self.table.name, self.table.version, self._content_signature)
        if token == self._reconciled_token:
            return
        rows = self._rows(["material_id", "revision", "path"])
        changed, paths, indexed = set(), {}, set()
        for row in rows:
            stored_id = row["material_id"]
            ident = self._legacy_ids.get(stored_id, stored_id)
            material = self.materials.get(ident)
            if material is None or material.revision != row["revision"]:
                changed.add(stored_id)
            else:
                indexed.add(ident)
                if row["path"] != material.path:
                    paths[stored_id] = material.path
        for ident in changed:
            self._delete_rows(ident)
        for ident, path in paths.items():
            if ident not in changed:
                self.table.update(where=f"material_id = '{_id(ident)}'", values={"path": path})
        self.pending = {ident for ident, material in self.materials.items()
                        if material.content.strip() and (ident not in indexed or ident in changed)}
        self._reconciled_token = (self.table.name, self.table.version, self._content_signature)

    def _material(self, ident: str):
        _id(ident)
        if ident not in self.materials:
            raise PCWError(f"Unknown material ID: {ident}")
        return self.materials[ident]

    def _check_links(self, links: list[str], ident: str):
        links = _unique_links(links, ident)
        for target in links:
            self._material(target)
        return links

    def _result(self, material: Material, content=False):
        result = {"id": material.id, "path": material.path, "links": material.links,
                  "revision": material.revision,
                  "index_status": "pending_preparation" if material.id in self.pending else "indexed"}
        if content:
            result["content"] = material.content
        for field in ("saved_at", "executor_session_id"):
            if field in material.metadata:
                result[field] = material.metadata[field]
        return result

    def status(self):
        with self._guard():
            return {"workspace": str(self.root), "materials": len(self.materials),
                    "pending_preparation": sorted(self.pending)[:50], "pending_count": len(self.pending),
                    "unregistered": self.unregistered[:50], "unregistered_count": len(self.unregistered),
                    "active": self.active}

    def list(self, offset: int = 0, limit: int = 50):
        with self._guard():
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
                raise PCWError("offset must be nonnegative and limit between 1 and 100")
            values = list(self.materials.values())
            return {"materials": [self._result(material) for material in values[offset:offset + limit]],
                    "total": len(values), "offset": offset,
                    "next_offset": offset + limit if offset + limit < len(values) else None,
                    "unregistered": self.unregistered[offset:offset + limit],
                    "unregistered_count": len(self.unregistered)}

    def read(self, material_id: str):
        with self._guard():
            return self._result(self._material(material_id), content=True)

    def save_subagent_result(self, material_name: str, result: str, executor_session_id: str,
                             expected_previous_revision: str | None = None):
        """Persist one returned subagent result without changing its Markdown body."""
        with self._guard():
            if not isinstance(result, str):
                raise PCWError("Subagent result must be a text string")
            if not isinstance(executor_session_id, str) or not executor_session_id.strip():
                raise PCWError("executor_session_id is required and must be the actual executor session ID")
            if not isinstance(material_name, str) or "/" in material_name or "\\" in material_name:
                raise PCWError("material_name must be one safe Markdown filename")
            target = self._knowledge_path(material_name)
            ident = self._material_id(target)
            existing = self.materials.get(ident)
            if existing is not None:
                if (existing.content == result and
                        existing.metadata.get("executor_session_id") == executor_session_id and
                        isinstance(existing.metadata.get("saved_at"), str)):
                    return {**self._result(existing, content=False), "status": "already_saved"}
                if expected_previous_revision is None:
                    # Keep the existing occupied-name behavior for callers that
                    # did not explicitly opt into a CAS raw-result revision.
                    raise PCWError(
                        f"Material filename {ident} is already occupied by a different result or executor session; "
                        "choose another material_name")
                if not isinstance(existing.metadata.get("saved_at"), str):
                    raise PCWError(
                        f"Material filename {ident} is not a saved raw subagent result and cannot be revised")
                if existing.metadata.get("executor_session_id") != executor_session_id:
                    raise PCWError(
                        f"Material filename {ident} is already occupied by a different executor session")
                if not isinstance(expected_previous_revision, str) or not expected_previous_revision:
                    raise PCWError(
                        f"Material filename {ident} is already occupied by a different result; "
                        "provide its expected_previous_revision to save a new raw result")
                if existing.revision != expected_previous_revision:
                    raise PCWError("Saved subagent result changed since it was read; read it again")
                metadata = copy.deepcopy(existing.metadata)
                metadata["saved_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                # The executor was compared above. Set it explicitly so the
                # persisted metadata exactly identifies the new raw return.
                metadata["executor_session_id"] = executor_session_id
                replacement = Material(existing.id, existing.path, metadata, result)
                # Write the authoritative body first. If it fails, the previous
                # body, metadata, revision, and search rows remain usable.
                self._save(replacement)
                self.materials[ident] = replacement
                self.pending.add(ident)
                # A successful body revision must never leave its prior vector
                # rows visible while literal semantic preparation is pending.
                self._delete_rows(ident)
                return {**self._result(replacement), "status": "updated"}
            if target.exists():
                # A path that scan did not register must never be overwritten by
                # a primary save just because its basename looks available.
                raise PCWError(f"Material filename {ident} already exists and cannot be overwritten")
            saved_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            material = Material(ident, target.relative_to(self.root).as_posix(), {
                "links": [], "saved_at": saved_at, "executor_session_id": executor_session_id,
            }, result)
            self._save(material)
            self.materials[ident] = material
            if result.strip():
                self.pending.add(ident)
            return {**self._result(material), "status": "saved"}

    def create(self, path: str, content: str, links: list[str] | None = None):
        with self._guard():
            target = self._knowledge_path(path)
            if target.exists():
                raise PCWError("Knowledge path already exists; use update or explicit adoption")
            ident = self._material_id(target)
            if ident in self.materials:
                raise PCWError(f"Material filename ID already exists: {ident}")
            material = Material(ident, target.relative_to(self.root).as_posix(),
                                {"links": self._check_links(links or [], ident)}, content)
            self._save(material)
            self.materials[ident] = material
            if content.strip():
                self.pending.add(ident)
            return self._result(material)

    def adopt(self, path: str):
        with self._guard():
            target = self._knowledge_path(path)
            metadata, content = _parse(target.read_bytes().decode("utf-8"))
            ident = self._material_id(target)
            relative = target.relative_to(self.root).as_posix()
            if ident in self.materials and self.materials[ident].path != relative:
                raise PCWError(f"Material filename ID already exists: {ident}")
            # id was an old transport identity. Keep every other metadata field,
            # but remove it when this file is explicitly adopted.
            metadata.pop("id", None)
            # Do not infer or reinterpret legacy free-text links.
            raw_links = metadata.get("links", [])
            if not isinstance(raw_links, list):
                raise PCWError("links must be a list of exact IDs")
            metadata["links"] = _unique_links(
                [self._legacy_ids.get(_id(value), _id(value)) for value in raw_links], ident)
            material = Material(ident, relative, metadata, content)
            self._save(material)
            self._scan()
            self._reconcile()
            return self._result(material)

    def migrate_legacy_ids(self):
        """Explicitly replace legacy YAML UUID identities with filename identities.

        This preserves bodies and existing LanceDB vectors. It is deliberately a
        separate operation: merely opening a workspace never rewrites knowledge.
        """
        with self._guard():
            mappings: dict[str, str] = {}
            for material in self.materials.values():
                if "id" not in material.metadata:
                    continue
                old = _id(material.metadata["id"])
                previous = mappings.get(old)
                if previous is not None and previous != material.id:
                    raise PCWError(f"Duplicate legacy material ID: {old}")
                mappings[old] = material.id
            # Never acknowledge a migration that leaves an old, unknown ID in
            # navigation. Keep the legacy file unchanged so the caller can
            # resolve the intended target and retry explicitly.
            for material in self.materials.values():
                missing = [link for link in material.links if link not in self.materials]
                if missing:
                    raise PCWError(
                        f"Legacy migration cannot resolve links in {material.id}: "
                        + ", ".join(missing))
            if not mappings and not self._legacy_link_paths:
                return {"status": "already_migrated", "migrated": [], "index_updated": []}

            applied = []
            index_updated = []
            try:
                # Update existing search rows in place: their text and vectors
                # remain untouched, only the material address changes.
                for old, new in mappings.items():
                    material = self._material(new)
                    if old != new:
                        self.table.update(where=f"material_id = '{_id(old)}'",
                                          values={"material_id": new, "path": material.path})
                        index_updated.append(f"index:{old}:{new}")
                for material in self.materials.values():
                    changed = material.path in self._legacy_id_paths or material.path in self._legacy_link_paths
                    if "id" in material.metadata:
                        material.metadata.pop("id")
                        changed = True
                    canonical = _unique_links(
                        [mappings.get(value, value) for value in material.links], material.id)
                    if canonical != material.links:
                        material.metadata["links"] = canonical
                        changed = True
                    if changed:
                        self._save(material)
                        applied.append(f"saved:{material.id}")
            except Exception as exc:
                return {"status": "partial", "migrated": applied, "index_updated": index_updated,
                        "error": str(exc),
                        "repair": "Retry pcw_migrate_legacy_ids to complete the interrupted migration; pcw_reconcile is diagnostic only"}
            self._scan()
            self._reconciled_token = None
            self._reconcile()
            return {"status": "ok", "migrated": applied, "index_updated": index_updated,
                    "pending_preparation": sorted(self.pending)[:50], "pending_count": len(self.pending)}

    def _update(self, material: Material, content: str):
        if material.content != content:
            # Deleting first makes even a failed/partial save safely unsearchable.
            self._delete_rows(material.id)
            material.set_content(content)
            self._save(material)
            if content.strip():
                self.pending.add(material.id)
            else:
                self.pending.discard(material.id)

    def update(self, material_id: str, content: str, expected_revision: str | None = None):
        with self._guard():
            material = self._material(material_id)
            if expected_revision is not None and material.revision != expected_revision:
                raise PCWError("Material changed since it was read; read it again")
            self._update(material, content)
            return self._result(material)

    def _move_same_id(self, material: Material, destination: Path, requested_path: str):
        """Move one filename-ID to another directory without changing identity."""
        old_path = material.path
        destination_relative = destination.relative_to(self.root).as_posix()
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.rename(self.root / old_path, destination)
        except Exception as exc:
            return {"status": "partial", "applied": [], "error": str(exc),
                    "repair": f"Retry pcw_rename({material.id!r}, {requested_path!r}); the source path remains authoritative"}

        # The filesystem has one source file after os.rename. If the index path
        # update fails, a fresh runtime's reconciliation observes that same file
        # and completes only the derived path update; it never needs a copied
        # second material with the same filename-ID.
        material.path = destination_relative
        applied = [f"moved:{material.id}:{old_path}:{destination_relative}"]
        try:
            aliases = [material.id] + [old for old, target in self._legacy_ids.items() if target == material.id]
            for stored_id in dict.fromkeys(aliases):
                self.table.update(where=f"material_id = '{_id(stored_id)}'", values={"path": destination_relative})
                applied.append(f"index_path:{stored_id}:{destination_relative}")
        except Exception as exc:
            self._reconciled_token = None
            return {"status": "partial", "applied": applied, "error": str(exc),
                    "repair": f"Retry pcw_rename({material.id!r}, {requested_path!r}) to complete the index path update; pcw_reconcile can diagnose it"}
        self._reconciled_token = None
        return self._result(material)

    def rename(self, material_id: str, path: str):
        with self._guard():
            material = self._material(material_id)
            destination = self._knowledge_path(path)
            if destination == self.root / material.path:
                return self._result(material)
            old_id = material.id
            new_id = self._material_id(destination)
            if new_id == old_id:
                if destination.exists():
                    raise PCWError("Destination already exists")
                return self._move_same_id(material, destination, path)
            destination_relative = destination.relative_to(self.root).as_posix()
            destination_metadata = copy.deepcopy(material.metadata)
            # A copied legacy id would make a fresh runtime see two legacy
            # sources. The destination already has its filename identity.
            destination_metadata.pop("id", None)
            prepared = Material(new_id, destination_relative, destination_metadata, material.content)
            existing = self.materials.get(new_id)
            if destination.exists():
                # A matching destination is an interrupted rename. Retrying the
                # same call completes it; a different file remains protected.
                if (existing is None or existing.content != prepared.content or
                        existing.metadata != prepared.metadata):
                    raise PCWError("Destination already exists")
            else:
                if existing is not None:
                    raise PCWError(f"Material filename ID already exists: {new_id}")
                self._save(prepared)
                self.materials[new_id] = prepared

            # Keep the old source file addressable while every incoming link is
            # saved. On a write failure, both old and new IDs still resolve and
            # retrying this exact rename resumes from the prepared destination.
            applied = [f"destination_prepared:{new_id}:{destination_relative}"]
            try:
                self._rewrite({old_id: new_id}, applied)
                legacy_aliases = [old for old, target in self._legacy_ids.items() if target == old_id]
                aliases = [old_id, *legacy_aliases]
                for stored_id in dict.fromkeys(aliases):
                    self.table.update(where=f"material_id = '{_id(stored_id)}'",
                                      values={"material_id": new_id, "path": destination_relative})
                (self.root / material.path).unlink()
                self.materials.pop(old_id)
                self.materials[new_id] = prepared
                for legacy, target in list(self._legacy_ids.items()):
                    if target == old_id:
                        self._legacy_ids[legacy] = new_id
                if old_id in self.pending:
                    self.pending.remove(old_id)
                    self.pending.add(new_id)
                applied.append(f"renamed:{old_id}:{new_id}:{destination_relative}")
            except Exception as exc:
                self._reconciled_token = None
                return {"status": "partial", "applied": applied,
                        "error": str(exc),
                        "repair": f"Retry pcw_rename({old_id!r}, {path!r}) to complete the prepared rename"}
            self._reconciled_token = None
            return self._result(prepared)

    def links(self, source_id: str, add: list[str] | None = None, remove: list[str] | None = None):
        with self._guard():
            material = self._material(source_id)
            additions = self._check_links(add or [], source_id)
            removals = {_id(value) for value in (remove or [])}
            material.metadata["links"] = _unique_links(
                [value for value in material.links if value not in removals] + additions, source_id)
            self._save(material)
            return self._result(material)

    def _mapping(self, mapping: dict[str, str]):
        for old, target in mapping.items():
            self._material(old)
            self._material(target)
            if old == target or target in mapping:
                raise PCWError("Replacements must map removed IDs directly to surviving IDs without chains")

    def _rewrite(self, mapping: dict[str, str | None], applied: list[str]):
        for material in self.materials.values():
            links = _unique_links([mapping.get(value, value) for value in material.links
                                   if mapping.get(value, value) is not None], material.id)
            if links != material.links:
                material.metadata["links"] = links
                self._save(material)
                applied.append(f"links:{material.id}")

    def reassign(self, mapping: dict[str, str]):
        with self._guard():
            self._mapping(mapping)
            applied = []
            try:
                self._rewrite(mapping, applied)
            except Exception as exc:
                return {"status": "partial", "applied": applied, "error": str(exc)}
            return {"status": "ok", "applied": applied}

    def _delete(self, material: Material, applied: list[str]):
        self._delete_rows(material.id)
        applied.append(f"index_removed:{material.id}")
        (self.root / material.path).unlink()
        applied.append(f"deleted:{material.id}")
        self.materials.pop(material.id)
        self.pending.discard(material.id)

    def delete(self, material_id: str):
        with self._guard():
            material = self._material(material_id)
            applied = []
            try:
                self._rewrite({material_id: None}, applied)
                self._delete(material, applied)
            except Exception as exc:
                return {"status": "partial", "applied": applied, "error": str(exc)}
            return {"status": "ok", "applied": applied}

    def merge(self, materials: list[dict], replacements: dict[str, str]):
        """Apply agent-written survivors and exact old-ID to target-ID mappings."""
        with self._guard():
            self._mapping(replacements)
            targets = {item["id"] for item in materials}
            if len(targets) != len(materials) or targets != set(replacements.values()):
                raise PCWError("Supply exactly one final content entry for each replacement target")
            plans = []
            for item in materials:
                target = self._material(item["id"])
                if not isinstance(item.get("content"), str):
                    raise PCWError("Each merge target requires final content supplied by the main agent")
                outgoing = item.get("links")
                if outgoing is None:
                    outgoing = target.links + [link for old, dest in replacements.items()
                                               if dest == target.id for link in self._material(old).links]
                outgoing = self._check_links(outgoing, target.id)
                outgoing = _unique_links([replacements.get(link, link) for link in outgoing], target.id)
                plans.append((target, item["content"], outgoing))
            applied = []
            try:
                for target, content, outgoing in plans:
                    if target.content != content:
                        self._delete_rows(target.id)
                        applied.append(f"index_removed:{target.id}")
                        target.set_content(content)
                        if content.strip():
                            self.pending.add(target.id)
                        else:
                            self.pending.discard(target.id)
                    target.metadata["links"] = outgoing
                    self._save(target)
                    applied.append(f"saved:{target.id}")
                # Every incoming rewrite must finish before any old file is removed.
                self._rewrite(replacements, applied)
                for old in replacements:
                    self._delete(self._material(old), applied)
            except Exception as exc:
                return {"status": "partial", "applied": applied, "error": str(exc),
                        "pending_preparation": sorted(self.pending)[:50], "pending_count": len(self.pending)}
            return {"status": "ok", "applied": applied,
                    "pending_preparation": sorted(self.pending)[:50], "pending_count": len(self.pending)}

    def prepare(self, material_id: str):
        with self._guard():
            material = self._material(material_id)
            return {"id": material.id, "path": material.path, "revision": material.revision,
                    "content": material.content,
                    "instruction": "A native subagent in the agent environment must return original semantic parts in order, without paraphrase or additions. Preserve tables, code, conditions and explanations together. Only inter-part whitespace may be omitted. Do not open source files."}

    @staticmethod
    def _validate_parts(content: str, parts: list[str]):
        if not isinstance(parts, list):
            raise PCWError("parts must be a list of original text strings")
        cursor = 0
        for part in parts:
            if not isinstance(part, str) or not part.strip():
                raise PCWError("Each semantic part must be nonempty original text")
            at = content.find(part, cursor)
            if at < 0 or content[cursor:at].strip():
                raise PCWError("Parts must preserve original text, order and all non-whitespace content")
            cursor = at + len(part)
        if content[cursor:].strip():
            raise PCWError("Parts omit original material content")

    def _get_provider(self):
        config = self.active["config"]
        if self._provider is None or self._provider_config != config:
            if self._provider is not None:
                self._provider.close()
            self._provider = self._factory(config)
            self._provider_config = config
        return self._provider

    @staticmethod
    def _vectors(provider, parts: list[str], dimensions: int, purpose: str):
        vectors = provider.embed(parts, purpose=purpose)
        if len(vectors) != len(parts):
            raise PCWError("Embedding provider returned the wrong vector count")
        converted = []
        for vector in vectors:
            if len(vector) != dimensions or not all(math.isfinite(float(value)) for value in vector):
                raise PCWError("Embedding provider returned invalid vector dimensions or numbers")
            if not any(float(value) != 0 for value in vector):
                raise PCWError("Embedding provider returned a zero vector")
            stored = array("f", (float(value) for value in vector)).tolist()
            if not all(math.isfinite(value) for value in stored) or not any(value != 0 for value in stored):
                raise PCWError("Embedding vector is not representable as nonzero finite float32")
            converted.append(stored)
        return converted

    def submit_parts(self, material_id: str, revision: str, parts: list[str]):
        with self._guard():
            material = self._material(material_id)
            if material.revision != revision:
                raise PCWError("Stale semantic preparation: material revision changed")
            self._validate_parts(material.content, parts)
            vectors = []
            if parts:
                vectors = self._vectors(self._get_provider(), parts,
                                        self.active["config"]["profile"]["dimensions"], "document")
            # Runtime writers obey the lock; an external editor need not. Never
            # publish a delayed embedding response for an externally changed body.
            _, saved_body = _parse((self.root / material.path).read_bytes().decode("utf-8"))
            if _revision(saved_body) != revision:
                self._scan()
                self._reconcile()
                raise PCWError("Stale semantic preparation: material changed while embedding")
            rows = [{"material_id": material.id, "part_index": index, "text": part,
                     "vector": vector, "path": material.path, "revision": material.revision}
                    for index, (part, vector) in enumerate(zip(parts, vectors))]
            # Explicit replacement, not a claim of transactionality across file/DB.
            self._delete_rows(material.id)
            if rows:
                try:
                    self.table.add(rows)
                except Exception:
                    self._delete_rows(material.id)
                    self.pending.add(material.id)
                    raise
            self.pending.discard(material.id)
            return {**self._result(material), "parts": len(rows)}

    def search(self, query: str, N: int | None = None, d_max: float | None = None,
               min_jump: float | None = None, multiplier: float | None = None):
        with self._guard():
            options = dict(self.active["search"])
            for key, value in {"N": N, "d_max": d_max, "min_jump": min_jump, "multiplier": multiplier}.items():
                if value is not None:
                    options[key] = value
            config = SearchConfig(**options)
            results = []
            if self.table.count_rows():
                vector = self._vectors(self._get_provider(), [query],
                                       self.active["config"]["profile"]["dimensions"], "query")[0]
                # No fast_search: LanceDB includes fresh rows outside an ANN index.
                rows = (self.table.search(vector).distance_type(config.metric)
                        .select(["material_id", "path"]).limit(config.N).to_list())
                results = select_candidates([{"id": row["material_id"], "path": row["path"],
                                              "distance": row["_distance"]} for row in rows], config)
            return {"results": results, "pending_preparation": sorted(self.pending)[:50],
                    "pending_count": len(self.pending), "unregistered": self.unregistered[:50],
                    "unregistered_count": len(self.unregistered), "search": dataclasses.asdict(config),
                    "search_calibration": self.active["search_calibration"]}

    def reconcile(self):
        with self._guard():
            return {"status": "ok", "pending_preparation": sorted(self.pending)[:50],
                    "pending_count": len(self.pending), "unregistered": self.unregistered[:50],
                    "unregistered_count": len(self.unregistered)}

    def switch_embeddings(self, config: dict, search: dict):
        with self._guard():
            config = validate_config(config)
            search_config = dataclasses.asdict(SearchConfig(**search))
            provider = None
            new_table = None
            previous = self.active
            active = None
            publication_warning = None
            try:
                provider = self._factory(config)
                compatible = embedding_identity(config) == embedding_identity(previous["config"])
                if compatible:
                    # Credential-only changes still test that the new connection works.
                    self._vectors(provider, ["PCW embedding connection verification"],
                                  config["profile"]["dimensions"], "document")
                    name = previous["table"]
                else:
                    name = "parts_" + uuid.uuid4().hex
                    new_table = self.db.create_table(name, schema=self._schema(config["profile"]["dimensions"]))
                    rows = self._rows()
                    # Batches bound provider requests; the stored semantic parts stay intact.
                    if not rows:
                        self._vectors(provider, ["PCW embedding connection verification"],
                                      config["profile"]["dimensions"], "document")
                    for start in range(0, len(rows), 32):
                        batch = rows[start:start + 32]
                        vectors = self._vectors(provider, [row["text"] for row in batch],
                                                config["profile"]["dimensions"], "document")
                        for row, vector in zip(batch, vectors):
                            row["vector"] = vector
                        new_table.add(batch)
                active = {"config": config, "table": name, "search": search_config,
                          "search_calibration": "explicit engineering settings; calibration not established by switching"}
                self._write_active(active)  # provider profile + table change in one replace
            except Exception as exc:
                # A directory fsync can fail AFTER pointer publication. Inspect
                # the pointer before ever deleting the candidate search table.
                try:
                    observed = json.loads((self.state / "active.json").read_text(encoding="utf-8"))
                except Exception:
                    if provider is not None:
                        provider.close()
                    return {"status": "partial", "active_unchanged": False, "error": str(exc),
                            "repair": "Cannot determine active pointer; retained both tables for repair"}
                if active is not None and observed == active:
                    publication_warning = str(exc)
                else:
                    cleanup = None
                    if new_table is not None:
                        try:
                            self.db.drop_table(new_table.name)
                        except Exception as cleanup_exc:
                            cleanup = str(cleanup_exc)
                    if provider is not None:
                        provider.close()
                    return {"status": "failed", "active_unchanged": observed == previous, "error": str(exc),
                            "cleanup_error": cleanup}
            old_provider = self._provider
            self.active = active
            self.table = self.db.open_table(name)
            self._provider = provider
            self._provider_config = config
            if old_provider is not None and old_provider is not provider:
                old_provider.close()
            if new_table is not None:
                try:
                    self.db.drop_table(previous["table"])
                except Exception as exc:
                    return {"status": "partial", "switched": True, "active": active,
                            "error": f"Old table cleanup failed: {exc}"}
            if publication_warning:
                return {"status": "partial", "switched": True, "active": active,
                        "error": f"Pointer published; durability confirmation failed: {publication_warning}"}
            return {"status": "ok", "reembedded": new_table is not None, "active": active}

    _CURRENT_FIELDS = ("goal", "constraints", "completion", "step", "blocker")
    _CURRENT_HEADINGS = {
        "goal": "Goal", "constraints": "Constraints", "completion": "Completion", "step": "Current step", "blocker": "Blocker",
    }

    @classmethod
    def _render_current(cls, current: dict[str, str]) -> str:
        sections = []
        for field in cls._CURRENT_FIELDS:
            value = current[field]
            if not isinstance(value, str):
                raise PCWError(f"Current {field} must be a text string")
            # The length marker makes each readable section unambiguous even
            # when a value contains another section heading or a fenced block.
            sections.append(
                f"# {cls._CURRENT_HEADINGS[field]}\n"
                f"<!-- pcw-current-length: {len(value)} -->\n"
                f"{value}")
        return "\n\n".join(sections) + "\n"

    @classmethod
    def _parse_current_markdown(cls, text: str) -> dict[str, str] | None:
        cursor = 0
        values = {}
        for index, field in enumerate(cls._CURRENT_FIELDS):
            heading = f"# {cls._CURRENT_HEADINGS[field]}\n"
            prefix = heading if index == 0 else "\n\n" + heading
            if not text.startswith(prefix, cursor):
                return None
            start = cursor + len(prefix)
            marker_end = text.find("\n", start)
            marker = text[start:marker_end] if marker_end >= 0 else ""
            match = re.fullmatch(r"<!-- pcw-current-length: ([0-9]+) -->", marker)
            if match is None:
                return None
            value_start = marker_end + 1
            value_end = value_start + int(match.group(1))
            if value_end > len(text):
                return None
            values[field] = text[value_start:value_end]
            cursor = value_end
        if text[cursor:] != "\n":
            return None
        return values

    def current_get(self):
        with self._guard():
            path = self.root / "current.md"
            self._assert_safe(path)
            if not path.exists():
                return {field: "" for field in self._CURRENT_FIELDS}
            text = path.read_bytes().decode("utf-8")
            current = self._parse_current_markdown(text)
            if current is not None:
                return current
            metadata, body = _parse(text)
            # Known YAML-only Current is safe to translate on the next write.
            # Other Markdown (including arbitrary YAML-fronted documents) must
            # be returned verbatim until the caller explicitly replaces it.
            if metadata.get("pcw_current") == 1 and not body and set(metadata).issubset({"pcw_current", *self._CURRENT_FIELDS}):
                return {field: metadata.get(field, "") for field in self._CURRENT_FIELDS}
            return {"legacy_content": text, "requires_explicit_replacement": True}

    def current_set(self, goal: str | None = None, constraints: str | None = None,
                    completion: str | None = None, step: str | None = None,
                    blocker: str | None = None, replace_legacy: bool = False):
        with self._guard():
            current = self.current_get()
            if "legacy_content" in current:
                if not replace_legacy or any(value is None for value in (goal, constraints, completion)):
                    raise PCWError("Legacy Current: read it and explicitly replace with goal, constraints, completion and replace_legacy=true")
                current = {key: "" for key in self._CURRENT_FIELDS}
            for key, value in {"goal": goal, "constraints": constraints, "completion": completion,
                               "step": step, "blocker": blocker}.items():
                if value is not None:
                    current[key] = value
            self._write(self.root / "current.md", self._render_current(current))
            return current

    def _git_paths(self, paths: list[str]):
        if not paths:
            raise PCWError("Specify exact memory files for the Git operation")
        for relative in paths:
            if relative == "current.md":
                self._assert_safe(self.root / relative)
            elif relative.startswith("knowledge/"):
                self._knowledge_path(relative[len("knowledge/"):])
            else:
                raise PCWError("Git scope allows only current.md and exact knowledge/*.md paths")
        return list(dict.fromkeys(paths))

    def _git(self, *args, check=True):
        self._assert_safe(self.root / ".git")
        environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        result = subprocess.run(["git", "--literal-pathspecs", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                                 "-C", str(self.root), *args], env=environment, text=False,
                                capture_output=True, check=False)
        # Git blob reads must preserve original CRLF material bodies.
        result.stdout = result.stdout.decode("utf-8")
        result.stderr = result.stderr.decode("utf-8", errors="replace")
        if check and result.returncode:
            raise PCWError(result.stderr.strip() or result.stdout.strip() or "Git operation failed")
        return result

    def _own_git(self):
        if not (self.root / ".git").is_dir():
            raise PCWError("Workspace has no separate Git repository; create an explicit checkpoint first")
        if Path(self._git("rev-parse", "--show-toplevel").stdout.strip()).resolve() != self.root:
            raise PCWError("Git repository is not the selected memory workspace")

    def checkpoint(self, paths: list[str], message: str):
        with self._guard():
            paths = self._git_paths(paths)
            applied = []
            try:
                if not (self.root / ".git").exists():
                    self._git("-c", "init.templateDir=", "init", ".")
                    applied.append("initialized memory Git repository")
                self._own_git()
                exclude = self.root / ".git" / "info" / "exclude"
                self._assert_safe(exclude)
                previous_exclude = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
                if "/.pcw-runtime/" not in previous_exclude.splitlines():
                    self._write(exclude, previous_exclude.rstrip("\n") + "\n/.pcw-runtime/\n")
                self._git("add", "--", *paths)
                applied.append("staged exact requested paths")
                self._git("commit", "--only", "-m", message, "--", *paths)
                commit = self._git("rev-parse", "HEAD").stdout.strip()
            except Exception as exc:
                return {"status": "partial", "applied": applied, "error": str(exc)}
            return {"status": "ok", "commit": commit, "paths": paths}

    def restore(self, commit: str, paths: list[str]):
        with self._guard():
            paths = self._git_paths(paths)
            self._own_git()
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.~^/-]*", commit) or commit.startswith("-"):
                raise PCWError("Invalid Git revision")
            revision = self._git("rev-parse", "--verify", commit + "^{commit}").stdout.strip()
            tree = self._git("ls-tree", "-r", revision, "--", *paths).stdout
            for line in tree.splitlines():
                if line.split()[0] not in {"100644", "100755"}:
                    raise PCWError("Restoring symlinks or nonregular memory files is not allowed")
            affected = [material for material in self.materials.values() if material.path in paths]
            for material in affected:
                historical = self._git("show", f"{revision}:{material.path}", check=False)
                if historical.returncode:
                    self._delete_rows(material.id)
                    continue
                _, body = _parse(historical.stdout)
                if body != material.content:
                    self._delete_rows(material.id)
            try:
                self._git("restore", "--source", revision, "--worktree", "--", *paths)
                self._scan()
                self._reconcile()
            except Exception as exc:
                return {"status": "partial", "error": str(exc), "paths": paths,
                        "repair": "pcw_reconcile; restored or changed bodies require fresh semantic preparation"}
            return {"status": "ok", "paths": paths, "pending_preparation": sorted(self.pending)[:50],
                    "pending_count": len(self.pending)}

    def close(self):
        with self._mutex:
            if self._provider is not None:
                self._provider.close()
                self._provider = None
                self._provider_config = None

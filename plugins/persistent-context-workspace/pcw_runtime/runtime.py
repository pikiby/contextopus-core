"""Knowledge is authoritative; LanceDB contains replaceable search representations.

There is deliberately no source-project reader, language-model splitter, remote
push, background service, or hidden embedding fallback in this module.
"""
from __future__ import annotations

import contextlib
import copy
import dataclasses
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
        raise PCWError("Material ID must be an exact UUID or existing safe slug")
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
        cache = {}
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
            if "id" not in metadata or "links" not in metadata:
                self.unregistered.append({"path": relative, "reason": "explicit pcw_adopt required for id/links metadata"})
                continue
            ident = _id(metadata["id"])
            links = _unique_links(metadata["links"], ident)
            if links != metadata["links"]:
                self.unregistered.append({"path": relative, "reason": "explicit pcw_adopt required to normalize links"})
                continue
            if ident in self.materials:
                raise PCWError(f"Duplicate material ID: {ident}")
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
        self.table.delete(f"material_id = '{_id(ident)}'")

    def _reconcile(self):
        """Reconcile saved memory only, including externally restored Git content."""
        token = (self.table.name, self.table.version, self._content_signature)
        if token == self._reconciled_token:
            return
        rows = self._rows(["material_id", "revision", "path"])
        changed, paths, indexed = set(), {}, set()
        for row in rows:
            ident = row["material_id"]
            material = self.materials.get(ident)
            if material is None or material.revision != row["revision"]:
                changed.add(ident)
            else:
                indexed.add(ident)
                if row["path"] != material.path:
                    paths[ident] = material.path
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

    def create(self, path: str, content: str, links: list[str] | None = None):
        with self._guard():
            target = self._knowledge_path(path)
            if target.exists():
                raise PCWError("Knowledge path already exists; use update or explicit adoption")
            ident = str(uuid.uuid4())
            material = Material(ident, target.relative_to(self.root).as_posix(),
                                {"id": ident, "links": self._check_links(links or [], ident)}, content)
            self._save(material)
            self.materials[ident] = material
            if content.strip():
                self.pending.add(ident)
            return self._result(material)

    def adopt(self, path: str):
        with self._guard():
            target = self._knowledge_path(path)
            metadata, content = _parse(target.read_bytes().decode("utf-8"))
            ident = _id(metadata["id"]) if "id" in metadata else str(uuid.uuid4())
            relative = target.relative_to(self.root).as_posix()
            if ident in self.materials and self.materials[ident].path != relative:
                raise PCWError("ID belongs to another material")
            metadata["id"] = ident
            # Do not infer or reinterpret legacy free-text links.
            metadata["links"] = _unique_links(metadata.get("links", []), ident)
            material = Material(ident, relative, metadata, content)
            self._save(material)
            self._scan()
            self._reconcile()
            return self._result(material)

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

    def rename(self, material_id: str, path: str):
        with self._guard():
            material = self._material(material_id)
            destination = self._knowledge_path(path)
            if destination == self.root / material.path:
                return self._result(material)
            if destination.exists():
                raise PCWError("Destination already exists")
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.rename(self.root / material.path, destination)
            material.path = destination.relative_to(self.root).as_posix()
            try:
                self.table.update(where=f"material_id = '{material.id}'", values={"path": material.path})
            except Exception as exc:
                return {"status": "partial", "applied": [f"renamed:{material.id}:{material.path}"],
                        "error": str(exc), "repair": "pcw_reconcile"}
            return self._result(material)

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
                    "instruction": "Native Codex subagent must return original semantic parts in order, without paraphrase or additions. Preserve tables, code, conditions and explanations together. Only inter-part whitespace may be omitted. Do not open source files."}

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

    def current_get(self):
        with self._guard():
            path = self.root / "current.md"
            self._assert_safe(path)
            if not path.exists():
                return {"goal": "", "constraints": "", "completion": "", "step": "", "blocker": ""}
            text = path.read_bytes().decode("utf-8")
            metadata, _ = _parse(text)
            if metadata.get("pcw_current") != 1:
                return {"legacy_content": text, "requires_explicit_replacement": True}
            return {field: metadata.get(field, "") for field in ("goal", "constraints", "completion", "step", "blocker")}

    def current_set(self, goal: str | None = None, constraints: str | None = None,
                    completion: str | None = None, step: str | None = None,
                    blocker: str | None = None, replace_legacy: bool = False):
        with self._guard():
            current = self.current_get()
            if "legacy_content" in current:
                if not replace_legacy or any(value is None for value in (goal, constraints, completion)):
                    raise PCWError("Legacy Current: read it and explicitly replace with goal, constraints, completion and replace_legacy=true")
                current = {key: "" for key in ("goal", "constraints", "completion", "step", "blocker")}
            for key, value in {"goal": goal, "constraints": constraints, "completion": completion,
                               "step": step, "blocker": blocker}.items():
                if value is not None:
                    current[key] = value
            header = yaml.safe_dump({"pcw_current": 1, **current}, sort_keys=False, allow_unicode=True)
            self._write(self.root / "current.md", "---\n" + header + "---\n")
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
                metadata, body = _parse(historical.stdout)
                if metadata.get("id") != material.id or body != material.content:
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

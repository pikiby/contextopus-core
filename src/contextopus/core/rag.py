"""Generic document index. Source identity and authoring rules belong to modules."""

from dataclasses import dataclass, field
import hashlib
import json
import math
from .chunking import TokenChunker


@dataclass(frozen=True)
class DocumentKey:
    module: str
    collection: str
    id: str

    def value(self):
        return json.dumps(
            [self.module, self.collection, self.id], separators=(",", ":")
        )


@dataclass(frozen=True)
class IndexDocument:
    key: DocumentKey
    revision: str
    text: str
    location: str
    metadata: dict = field(default_factory=dict)


class RagIndex:
    """Shared LanceDB representation builder, independent of cards and cycles."""

    def __init__(self, layout=None, resources=None, embeddings=None, chunking=None):
        self.layout, self.resources = layout, resources
        self.embeddings, self.chunking = embeddings, chunking
        self._requested_embeddings = embeddings
        self.db = self.table = self._provider = None
        self.source_adapters = {}

    def register_source(self, module, adapter):
        self.source_adapters[module] = adapter

    @staticmethod
    def stored_status(layout):
        state = layout.workspace_rag
        pointer = state / "active.json"
        if not pointer.is_file() or not (state / "lancedb").is_dir():
            return {"state": "not_initialized", "chunks": None, "documents": None}
        active = json.loads(pointer.read_text())
        import lancedb

        db = lancedb.connect(str(state / "lancedb"))
        table = db.open_table(active["table"])
        rows = RagIndex.read_rows(table, ["material_id"])
        if "module" in table.schema.names:
            rows = RagIndex.read_rows(
                table, ["module", "collection", "object_id", "material_id"]
            )
            count = len(
                {
                    (
                        r["module"] or "workspace",
                        r["collection"] or "",
                        r["object_id"] or r["material_id"],
                    )
                    for r in rows
                }
            )
        else:
            count = len({r["material_id"] for r in rows})
        return {
            "state": "available",
            "chunks": table.count_rows(),
            "documents": count,
            "active": active,
        }

    @staticmethod
    def schema(dimensions):
        import pyarrow as pa

        return pa.schema(
            [
                ("material_id", pa.string()),
                ("part_index", pa.int32()),
                ("text", pa.string()),
                ("vector", pa.list_(pa.float32(), dimensions)),
                ("path", pa.string()),
                ("revision", pa.string()),
                ("token_start", pa.int64()),
                ("token_end", pa.int64()),
                ("char_start", pa.int64()),
                ("char_end", pa.int64()),
                ("chunking_id", pa.string()),
                ("part_count", pa.int32()),
                ("module", pa.string()),
                ("collection", pa.string()),
                ("object_id", pa.string()),
                ("metadata", pa.string()),
                ("workspace", pa.string()),
            ]
        )

    def connect(self, path):
        import lancedb

        self.db = lancedb.connect(str(path))
        return self.db

    def open_table(self, name):
        self.table = self.db.open_table(name)
        return self.table

    def create_table(self, name, dimensions, *, schema=None):
        return self.db.create_table(
            name, schema=schema if schema is not None else self.schema(dimensions)
        )

    @staticmethod
    def read_rows(table, columns=None, predicate=None):
        query = table.search()
        if predicate:
            query = query.where(predicate)
        if columns is not None:
            query = query.select(columns)
        return query.limit(None).to_list()

    @staticmethod
    def nearest(
        table, vector, *, predicate=None, columns=None, limit=20, metric="cosine"
    ):
        query = table.search(vector).distance_type(metric)
        if predicate:
            query = query.where(predicate, prefilter=True)
        if columns is not None:
            query = query.select(columns)
        return query.limit(limit).to_list()

    @staticmethod
    def reconcile_rows(rows, documents, chunk_id, aliases=None):
        aliases = aliases or {}
        changed, paths, indexed, groups = set(), {}, set(), {}
        for row in rows:
            stored_id = row["material_id"]
            ident = aliases.get(stored_id, stored_id)
            document = documents.get(ident)
            groups.setdefault(stored_id, []).append(row)
            if (
                document is None
                or document.revision != row["revision"]
                or row["chunking_id"] != chunk_id
            ):
                changed.add(stored_id)
            else:
                indexed.add(ident)
                if row["path"] != document.location:
                    paths[stored_id] = document.location
        for ident, group in groups.items():
            if any(row["part_count"] != len(group) for row in group) or {
                row["part_index"] for row in group
            } != set(range(len(group))):
                changed.add(ident)
        return changed, paths, indexed

    def _generic_table(self, create=False):
        from .embeddings import default_config
        from .chunking import default_chunking
        import os, uuid

        if create and not (self.layout.root / ".pcw").exists() and self.layout.legacy:
            self.layout.configuration.mkdir(parents=True, exist_ok=True)
            (self.layout.configuration / "layout.json").write_text(
                json.dumps({"format": "contextopus", "version": 1})
            )
        state = self.layout.workspace_rag
        if not create and not (state / "active.json").is_file():
            return None
        if create:
            state.mkdir(parents=True, exist_ok=True)
        self.connect(state / "lancedb")
        pointer = state / "active.json"
        if pointer.exists():
            active = json.loads(pointer.read_text())
            if (
                self._requested_embeddings is not None
                and active["config"] != self._requested_embeddings
            ):
                raise ValueError(
                    "Generic module must use the root's active embedding profile"
                )
            if (
                self.embeddings is not None
                and self.embeddings != active["config"]
                and self._provider is not None
            ):
                self._provider.close()
                self._provider = None
            self.embeddings, self.chunking = active["config"], active["chunking"]
            self.table = self.open_table(active["table"])
        else:
            self.embeddings = self.embeddings or default_config()
            self.chunking = self.chunking or default_chunking()
            name = "parts_" + uuid.uuid4().hex
            self.table = self.create_table(
                name, self.embeddings["profile"]["dimensions"]
            )
            active = {
                "config": self.embeddings,
                "chunking": self.chunking,
                "table": name,
                "index_format": 2,
                "search": {
                    "N": 20,
                    "d_max": 0.8,
                    "min_jump": 0.02,
                    "multiplier": 3.0,
                    "metric": "cosine",
                },
                "search_calibration": "engineering defaults; not calibrated",
            }
            temporary = pointer.with_suffix(".tmp")
            temporary.write_text(json.dumps(active))
            os.replace(temporary, pointer)
        missing = set(
            self.schema(self.embeddings["profile"]["dimensions"]).names
        ) - set(self.table.schema.names)
        expressions = {
            "module": "'workspace'",
            "collection": "workspace",
            "object_id": "material_id",
            "metadata": "'{}'",
            "workspace": "''",
        }
        if missing:
            if not create:
                raise ValueError(
                    "Index requires explicit migration before generic search"
                )
            self.table.add_columns({name: expressions[name] for name in missing})
        return self.table

    def _get_provider(self):
        if self._provider is None:
            self._provider = self.resources.acquire(self.embeddings)
        return self._provider

    @staticmethod
    def _quote(value):
        return "'" + str(value).replace("'", "''") + "'"

    def index(self, document):
        from .chunking import chunking_identity

        with self.layout.guard():
            table = self._generic_table(create=True)
            provider = self._get_provider()
            chunker = TokenChunker(self.chunking, self.embeddings, provider)
            rows = self.rows(
                document,
                chunker,
                provider,
                self.embeddings,
                chunking_identity(self.chunking, self.embeddings),
            )
            predicate = (
                "module="
                + self._quote(document.key.module)
                + " AND collection="
                + self._quote(document.key.collection)
                + " AND object_id="
                + self._quote(document.key.id)
            )
            if rows:
                table.merge_insert(
                    ["module", "collection", "object_id", "part_index"]
                ).when_matched_update_all().when_not_matched_insert_all().when_not_matched_by_source_delete(
                    predicate
                ).execute(rows)
            else:
                table.delete(predicate)
        return {
            "key": document.key.value(),
            "revision": document.revision,
            "chunks": len(rows),
        }

    def search(
        self,
        query,
        *,
        module=None,
        collection=None,
        object_type=None,
        include_archived=False,
        distance=None,
        limit=20,
    ):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("Invalid result limit")
        table = self._generic_table()
        if table is None:
            return []
        clauses = []
        for name, value in (("module", module), ("collection", collection)):
            if value is not None:
                clauses.append(name + "=" + self._quote(value))
        # Metadata filtering is resolved into identities before nearest lookup.
        rows = self.read_rows(
            table,
            ["module", "collection", "object_id", "metadata", "path"],
            " AND ".join(clauses) or None,
        )
        from .settings import Settings, matches_location

        filters = Settings(self.layout).snapshot(
            module=module, context=collection if module else None
        )["values"]
        source_documents = {
            module: adapter.eligible_documents(
                [row for row in rows if row["module"] == module]
            )
            for module, adapter in self.source_adapters.items()
            if any(row["module"] == module for row in rows)
        }
        eligible = []
        for row in rows:
            key = DocumentKey(row["module"], row["collection"], row["object_id"])
            if row["module"] in source_documents:
                source_document = source_documents[row["module"]].get(key)
                if source_document is None:
                    continue
                row = {
                    **row,
                    "path": source_document.location,
                    "metadata": json.dumps(source_document.metadata),
                }
            if not matches_location(row["path"], filters):
                continue
            meta = json.loads(row["metadata"] or "{}")
            if object_type is not None and meta.get("object_type") != object_type:
                continue
            if not include_archived and meta.get("archived", False):
                continue
            eligible.append(
                "(module="
                + self._quote(row["module"])
                + " AND collection="
                + self._quote(row["collection"])
                + " AND object_id="
                + self._quote(row["object_id"])
                + ")"
            )
        if not eligible:
            return []
        vector = self.vectors(
            self._get_provider(),
            [query],
            self.embeddings["profile"]["dimensions"],
            "query",
        )[0]
        found = self.nearest(
            table, vector, predicate=" OR ".join(eligible), limit=limit
        )
        result, seen = [], set()
        for row in found:
            key = DocumentKey(row["module"], row["collection"], row["object_id"])
            if key in seen or distance is not None and row["_distance"] > distance:
                continue
            seen.add(key)
            source_document = source_documents.get(row["module"], {}).get(key)
            if source_document is not None:
                row = {
                    **row,
                    "path": source_document.location,
                    "metadata": json.dumps(source_document.metadata),
                }
            result.append(
                {
                    "key": json.loads(key.value()),
                    "revision": row["revision"],
                    "location": row["path"],
                    "metadata": json.loads(row["metadata"] or "{}"),
                    "distance": row["_distance"],
                }
            )
        return result

    @staticmethod
    def vectors(provider, parts, dimensions, purpose):
        from array import array

        vectors = provider.embed(parts, purpose=purpose)
        if len(vectors) != len(parts):
            raise ValueError("Embedding provider returned the wrong vector count")
        converted = []
        for vector in vectors:
            if len(vector) != dimensions or not all(
                math.isfinite(float(x)) for x in vector
            ):
                raise ValueError(
                    "Embedding provider returned invalid vector dimensions or numbers"
                )
            stored = array("f", (float(x) for x in vector)).tolist()
            if not all(math.isfinite(x) for x in stored) or not any(stored):
                raise ValueError(
                    "Embedding vector is not representable as nonzero finite float32"
                )
            converted.append(stored)
        return converted

    def rows(self, document, chunker, provider, config, chunk_id):
        pieces = chunker.split(document.text) if document.text.strip() else []
        vectors = []
        for start in range(0, len(pieces), 32):
            vectors.extend(
                self.vectors(
                    provider,
                    [x["text"] for x in pieces[start : start + 32]],
                    config["profile"]["dimensions"],
                    "document",
                )
            )
        return [
            {
                **piece,
                "material_id": document.key.id,
                "part_index": index,
                "part_count": len(pieces),
                "vector": vector,
                "path": document.location,
                "revision": document.revision,
                "chunking_id": chunk_id,
                "module": document.key.module,
                "collection": document.key.collection,
                "object_id": document.key.id,
                "metadata": json.dumps(document.metadata),
                "workspace": document.key.collection
                if document.key.module == "workspace"
                else "",
            }
            for index, (piece, vector) in enumerate(zip(pieces, vectors))
        ]


VectorIndex = RagIndex


def rebuild_profile(
    index,
    *,
    previous,
    config,
    search,
    chunking,
    documents,
    validate_snapshot,
    read_active,
    write_active,
    factory,
    schema=None,
):
    """Publish a complete replacement representation after source validation.

    Source callbacks are module-owned. A post-publication fsync error never
    deletes a candidate table that the durable pointer may already reference.
    """
    import uuid
    from .embeddings import validate_config, embedding_identity
    from .chunking import validate_chunking, chunking_identity

    config = validate_config(config)
    chunking = validate_chunking(chunking, config)
    chunk_id = chunking_identity(chunking, config)
    provider = new_table = active = None
    warning = None
    try:
        provider = factory(config)
        compatible = embedding_identity(config) == embedding_identity(
            previous["config"]
        ) and chunk_id == chunking_identity(previous["chunking"], previous["config"])
        if compatible:
            index.vectors(
                provider,
                ["Embedding connection verification"],
                config["profile"]["dimensions"],
                "document",
            )
            name = previous["table"]
        else:
            name = "parts_" + uuid.uuid4().hex
            new_table = index.create_table(
                name, config["profile"]["dimensions"], schema=schema
            )
            chunker = TokenChunker(chunking, config, provider)
            snapshots = list(documents)
            if not any(d.text.strip() for d in snapshots):
                index.vectors(
                    provider,
                    ["Embedding connection verification"],
                    config["profile"]["dimensions"],
                    "document",
                )
            for document in snapshots:
                rows = index.rows(document, chunker, provider, config, chunk_id)
                if rows:
                    new_table.add(rows)
            validate_snapshot()
        active = {
            "config": config,
            "table": name,
            "search": search,
            "chunking": chunking,
            "index_format": 2,
            "search_calibration": "explicit engineering settings; calibration not established by switching",
        }
        write_active(active)
    except Exception as exc:
        try:
            observed = read_active()
        except Exception:
            if provider is not None:
                provider.close()
            return {
                "status": "partial",
                "active_unchanged": False,
                "error": str(exc),
                "repair": "Cannot determine active pointer; retained both tables for repair",
            }
        if active is not None and observed == active:
            warning = str(exc)
        else:
            cleanup = None
            if new_table is not None:
                try:
                    index.db.drop_table(new_table.name)
                except Exception as cleanup_exc:
                    cleanup = str(cleanup_exc)
            if provider is not None:
                provider.close()
            return {
                "status": "failed",
                "active_unchanged": observed == previous,
                "error": str(exc),
                "cleanup_error": cleanup,
            }
    result = {
        "status": "ok",
        "reembedded": new_table is not None,
        "active": active,
        "_provider": provider,
    }
    if new_table is not None:
        try:
            index.db.drop_table(previous["table"])
        except Exception as exc:
            result.update(
                status="partial",
                switched=True,
                error="Old table cleanup failed: " + str(exc),
            )
    if warning:
        result.update(
            status="partial",
            switched=True,
            error="Pointer published; durability confirmation failed: " + warning,
        )
    return result

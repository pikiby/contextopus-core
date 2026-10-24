"""Apply a validated source snapshot to one collection of the shared RAG."""

from dataclasses import replace
import json

from ..rag import DocumentKey, IndexDocument
from .reconcile import plan


def reconcile_index(index, snapshot):
    """Replayable per-document writes; source owner must serialize scan and call.

    Additions/updates precede removals. On failure the caller retries from a fresh
    source snapshot. This is not an atomic transaction across SQL and RAG.
    """
    plan(snapshot, ())  # Reject failed/invalid snapshots before opening storage.
    for document in snapshot.documents:
        json.dumps(document.metadata, allow_nan=False)
    with index.layout.guard():
        table = index._generic_table()
        predicate = ("module=" + index._quote(snapshot.module)
                     + " AND collection=" + index._quote(snapshot.collection))
        rows = [] if table is None else index.read_rows(table, predicate=predicate,
            columns=["object_id", "revision", "path", "metadata", "part_index", "part_count", "chunking_id"])
        groups = {}
        for row in rows:
            groups.setdefault(row["object_id"], []).append(row)
        previous = []
        for ident, group in groups.items():
            first = group[0]
            document = IndexDocument(DocumentKey(snapshot.module, snapshot.collection, ident),
                first["revision"], "", first["path"], json.loads(first["metadata"] or "{}"))
            valid = (all(row["part_count"] == len(group) for row in group)
                     and {row["part_index"] for row in group} == set(range(len(group)))
                     and all((row["revision"], row["path"], row["metadata"], row["chunking_id"])
                             == (first["revision"], first["path"], first["metadata"], first["chunking_id"])
                             for row in group))
            if not valid:
                # Force repair even if the surviving fragment has the current revision.
                document = replace(document, revision="incomplete:" + document.revision)
            previous.append(document)
        changes = plan(snapshot, previous)
        for document in changes.upsert:
            index.index(document)
        if changes.refresh:
            for document in changes.refresh:
                index.update_document(document)
        for key in changes.delete:
            index.delete_document(key)
        return {"indexed": len(changes.upsert), "refreshed": len(changes.refresh),
                "deleted": len(changes.delete), "unchanged": len(changes.unchanged),
                "complete": snapshot.complete}

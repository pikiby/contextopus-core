"""Plan derived-store changes without interpreting a failed scan as deletion."""

from dataclasses import dataclass
from typing import Iterable

from ..rag import DocumentKey, IndexDocument


@dataclass(frozen=True)
class SourceSnapshot:
    module: str
    collection: str
    documents: tuple[IndexDocument, ...]
    complete: bool = False
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class Reconciliation:
    upsert: tuple[IndexDocument, ...]
    refresh: tuple[IndexDocument, ...]
    delete: tuple[DocumentKey, ...]
    unchanged: tuple[DocumentKey, ...]


def _documents(items, scope):
    result = {}
    for document in items:
        key = document.key
        if (key.module, key.collection) != scope:
            raise ValueError("Document is outside the declared source scope")
        if not key.id or not document.revision:
            raise ValueError("Documents require stable identity and revision")
        if key in result:
            raise ValueError("Duplicate document identity: " + key.id)
        result[key] = document
    return result


def plan(snapshot: SourceSnapshot, previous: Iterable[IndexDocument]) -> Reconciliation:
    """Compare one collection; callers serialize capture/apply with source writes.

    A partial snapshot can add/update but cannot infer deletions. Failed scans
    abort before any effects. SQL and RAG adapters apply the same plan to their
    own projections; this function makes no cross-database atomicity claim.
    Revisions identify indexed text; metadata/path-only changes need no embedding.
    """
    if not snapshot.module or not snapshot.collection:
        raise ValueError("An explicit module and collection are required")
    if type(snapshot.complete) is not bool:
        raise ValueError("Snapshot completeness must be boolean")
    if snapshot.errors:
        raise ValueError("Source scan failed: " + "; ".join(snapshot.errors))
    scope = snapshot.module, snapshot.collection
    current = _documents(snapshot.documents, scope)
    old = _documents(previous, scope)
    upsert, refresh, unchanged = [], [], []
    for key, document in current.items():
        prior = old.get(key)
        if prior is None or prior.revision != document.revision:
            upsert.append(document)
        elif prior.location != document.location or prior.metadata != document.metadata:
            refresh.append(document)
        else:
            unchanged.append(key)
    deleted = tuple(key for key in old if key not in current) if snapshot.complete else ()
    return Reconciliation(tuple(upsert), tuple(refresh), deleted, tuple(unchanged))

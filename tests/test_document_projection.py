"""Real local RAG projection with deterministic embeddings and no downloads."""

from dataclasses import replace
from unittest.mock import patch

import pytest

from contextopus.core.documents import SourceSnapshot, reconcile_index
from contextopus.core.embeddings import default_config
from contextopus.core.rag import DocumentKey, IndexDocument, RagIndex
from contextopus.core.resources import ProcessResources
from contextopus.core.storage import StorageLayout
from fake_embeddings import Factory


def doc(ident, text="Instructions", **kwargs):
    return IndexDocument(DocumentKey("example", "rules", ident), text, text,
                         kwargs.get("path", ident + ".md"), kwargs.get("metadata", {"type": "instruction"}))


def snapshot(*docs, complete=True):
    return SourceSnapshot("example", "rules", docs, complete=complete)


def test_index_refresh_delete_and_retry_without_cross_scope_changes(tmp_path):
    factory = Factory()
    config = default_config()
    config["profile"]["dimensions"] = 2
    with ProcessResources(factory) as resources:
        index = RagIndex(StorageLayout(tmp_path), resources, embeddings=config)
        a, b = doc("a"), doc("b")
        assert reconcile_index(index, snapshot(a, b))["indexed"] == 2
        foreign = replace(a, key=DocumentKey("other", "rules", "a"))
        index.index(foreign)
        calls = len(factory.calls)
        moved = replace(a, location="moved.md", metadata={"type": "instruction", "model": "new"})
        assert reconcile_index(index, snapshot(moved, b))["refreshed"] == 1
        assert len(factory.calls) == calls
        assert reconcile_index(index, snapshot(moved, b))["unchanged"] == 2
        assert reconcile_index(index, snapshot(moved, complete=False))["deleted"] == 0
        changed = doc("a", "Changed instruction")
        with patch.object(index, "index", side_effect=RuntimeError("embedding unavailable")):
            with pytest.raises(RuntimeError):
                reconcile_index(index, snapshot(changed))
        assert index.read_rows(index.table, predicate=index.key_predicate(b.key))
        assert reconcile_index(index, snapshot(changed))["deleted"] == 1
        assert index.read_rows(index.table, predicate=index.key_predicate(foreign.key))
        assert reconcile_index(index, snapshot(changed))["unchanged"] == 1
        with pytest.raises(ValueError, match="scan failed"):
            reconcile_index(index, replace(snapshot(), errors=("disk unavailable",)))
        assert index.read_rows(index.table, predicate=index.key_predicate(changed.key))


def test_invalid_snapshot_does_not_create_storage(tmp_path):
    root = tmp_path / "absent"
    index = RagIndex(StorageLayout(root))
    with pytest.raises(ValueError, match="Duplicate"):
        reconcile_index(index, snapshot(doc("a"), doc("a")))
    assert not root.exists()

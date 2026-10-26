"""Owner-independent, deterministic one-hop navigation."""

import pytest

from contextopus.core.documents import direct_relations
from contextopus.core.rag import DocumentKey
from contextopus.interfaces.mcp.presentation import present


def key(ident, module="example"):
    return DocumentKey(module, "records", ident)


def test_directions_deduplication_and_no_transitive_expansion():
    a, b, c = map(key, "abc")
    edges = [(a, b), (b, c), (a, b), (b, b)]
    result = direct_relations([b, b], reversed(edges))
    assert result["items"] == [
        {"anchor": b, "key": a, "direction": "incoming"},
        {"anchor": b, "key": c, "direction": "outgoing"},
    ]
    assert direct_relations([a], edges)["total"] == 1
    assert direct_relations([b], edges + [(b, a)])["items"][0]["direction"] == "both"


def test_pagination_is_stable_and_keys_keep_owner_identity():
    anchor, other = key("a"), key("a", "other")
    edges = [(anchor, key(str(index))) for index in range(101)] + [(other, anchor)]
    first = direct_relations([anchor], edges, limit=100)
    last = direct_relations([anchor], reversed(edges), offset=first["next_offset"], limit=100)
    assert first["total"] == last["total"] == 102
    assert last["next_offset"] is None
    assert len(first["items"] + last["items"]) == 102
    assert last["items"][-1]["key"] == other
    assert direct_relations([anchor], edges, offset=1000)["items"] == []


@pytest.mark.parametrize("offset,limit", [(True, 1), (-1, 1), (0, True), (0, 0), (0, 101)])
def test_invalid_bounds(offset, limit):
    with pytest.raises(ValueError):
        direct_relations([], [], offset, limit)


def test_presentation_preserves_relation_evidence_exactly():
    envelope = {"items": [{"id": "missing", "title": "missing", "path": None,
                           "revision": None, "description": "", "in_proposal": False}],
                "total": 1, "next_offset": None, "inventory_complete": False}
    result = {"id": "anchor", "content": "Body", "relation_candidates": envelope}
    assert present(result, operation="workspace.read")["relation_candidates"] == envelope
    assert present(result, operation="workspace.read", detail="full")["relation_candidates"] == envelope


def test_keys_with_the_same_id_in_different_collections_do_not_merge():
    anchor = key("anchor")
    one = DocumentKey("example", "first", "shared")
    two = DocumentKey("example", "second", "shared")
    result = direct_relations([anchor], [(anchor, two), (one, anchor)])
    assert [(row["key"], row["direction"]) for row in result["items"]] == [
        (one, "incoming"), (two, "outgoing")]


def test_unrelated_edges_and_empty_anchors_never_expand_the_scope():
    a, b, c = map(key, "abc")
    assert direct_relations([a], [(b, c)])["items"] == []
    assert direct_relations([], [(a, b), (b, c)])["total"] == 0


def test_compact_batch_preserves_all_relation_pages_and_missing_evidence():
    envelope = {"items": [{"id": "missing", "revision": None, "missing": True}],
                "offset": 0, "limit": 1, "total": 101, "next_offset": 1,
                "inventory_complete": False, "unavailable_contexts": ["old"],
                "coverage": "owner_declared_edges", "coverage_limits": ["Partial inventory"]}
    value = {"materials": [{"id": "anchor", "content": "Body", "relation_candidates": envelope}]}
    assert present(value, operation="workspace.read_many")["materials"][0]["relation_candidates"] == envelope

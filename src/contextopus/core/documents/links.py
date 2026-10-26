"""Exact wikilink resolution for explicitly required instruction documents."""

from pathlib import PurePosixPath

from ..rag import DocumentKey


def direct_relations(anchors, edges, offset=0, limit=50):
    """Page one-hop relations supplied by an owner, without reading documents.

    An edge is a pair of DocumentKeys (source, target). Reciprocal edges have
    direction ``both``; repeated anchors and edges do not duplicate rows.
    """
    if type(offset) is not int or offset < 0:
        raise ValueError("offset must be a nonnegative integer")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    selected = set(anchors)
    if any(not isinstance(key, DocumentKey) for key in selected):
        raise ValueError("anchors must contain DocumentKeys")
    neighbors = {}
    for source, target in edges:
        if not isinstance(source, DocumentKey) or not isinstance(target, DocumentKey):
            raise ValueError("edges must contain pairs of DocumentKeys")
        if source == target:
            continue
        if source in selected:
            neighbors.setdefault((source, target), set()).add("outgoing")
        if target in selected:
            neighbors.setdefault((target, source), set()).add("incoming")
    def order(pair):
        return tuple((key.module, key.collection, key.id) for key in pair)
    pairs = sorted(neighbors, key=order)
    rows = [{"anchor": anchor, "key": key,
             "direction": "both" if len(neighbors[(anchor, key)]) == 2
             else next(iter(neighbors[(anchor, key)]))}
            for anchor, key in pairs[offset:offset + limit]]
    return {"items": rows, "total": len(pairs), "offset": offset, "limit": limit,
            "next_offset": offset + limit if offset + limit < len(pairs) else None}


def resolve_required(documents, references):
    """Return full documents, dependencies first, once each; never use similarity.

    Only the YAML instructions mapping is expanded. Ordinary links remain ordinary.
    References may name stable IDs, relative paths, or unique file stems. A label
    is presentation text; ambiguous/missing targets and cycles are errors.
    """
    aliases, identities = {}, set()
    for document in documents:
        if document.key in identities:
            raise ValueError("Duplicate instruction identity")
        identities.add(document.key)
        for name in {document.key.id, document.location,
                     str(PurePosixPath(document.location).with_suffix("")),
                     PurePosixPath(document.location).stem}:
            aliases.setdefault(name, []).append(document)
    active, done, result = set(), set(), []

    def visit(reference):
        if not isinstance(reference, str) or not reference.startswith("[[") or not reference.endswith("]]"):
            raise ValueError("Expected an instruction wikilink")
        name = reference[2:-2].split("|", 1)[0].strip()
        targets = aliases.get(name, [])
        if len(targets) != 1:
            raise ValueError("Missing or ambiguous instruction: " + name)
        document = targets[0]
        if document.metadata.get("type") != "instruction":
            raise ValueError("Required target is not an instruction: " + name)
        key = document.key
        if key in active:
            raise ValueError("Cyclic required instructions: " + name)
        if key in done:
            return
        active.add(key)
        required = document.metadata.get("instructions", {})
        if not isinstance(required, dict):
            raise ValueError("instructions must map roles to wikilinks")
        for dependency in required.values():
            visit(dependency)
        active.remove(key)
        done.add(key)
        result.append(document)

    for reference in references:
        visit(reference)
    return tuple(result)

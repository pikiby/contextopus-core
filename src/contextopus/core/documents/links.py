"""Exact wikilink resolution for explicitly required instruction documents."""

from pathlib import PurePosixPath


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

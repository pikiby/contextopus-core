"""Shared instruction bodies remain authoritative when derived storage fails."""

import hashlib
from unittest.mock import patch

import pytest

from contextopus.core.documents.instructions import InstructionLibrary
from contextopus.core.embeddings import default_config
from contextopus.core.rag import DocumentKey, IndexDocument, RagIndex
from contextopus.core.resources import ProcessResources
from contextopus.core.storage import StorageLayout
from contextopus.startup import Application
from fake_embeddings import Factory


def metadata(ident, **values):
    return {"id": ident, "type": "instruction", "title": ident,
            "description": "Instructions for " + ident, **values}


def test_missing_reads_do_not_initialize_any_storage(tmp_path):
    root = tmp_path / "absent"
    library = InstructionLibrary(StorageLayout(root))
    assert library.list() == {"instructions": []}
    assert library.resolve([])["instructions"] == []
    with pytest.raises(FileNotFoundError):
        library.read("[[missing]]")
    assert not root.exists()


def test_lossless_body_full_file_revision_and_yaml_conflicts(tmp_path):
    library = InstructionLibrary(StorageLayout(tmp_path))
    body = "---\nuser: front matter\n---\n\nРусский текст  \n[[ordinary]]\n"
    saved = library.save("workspace.project.md", metadata("stable", config={"model": "chosen"}), body)
    assert saved["content"] == body
    assert saved["index"] == {"status": "pending"}
    path = library.root / saved["path"]
    assert saved["revision"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert library.read("[[workspace.project|Project]]")["content"] == body
    assert library.read("stable")["metadata"]["config"] == {"model": "chosen"}
    listing = library.list()["instructions"][0]
    assert "content" not in listing and "metadata" not in listing
    with pytest.raises(ValueError, match="revision conflict"):
        library.save(saved["path"], saved["metadata"], "overwrite")
    changed = path.read_text().replace("model: chosen", "model: externally-changed")
    path.write_text(changed)
    with pytest.raises(ValueError, match="revision conflict"):
        library.save(saved["path"], saved["metadata"], "overwrite", saved["revision"])
    assert path.read_text() == changed
    current = library.read("stable")
    updated = library.save(current["path"], current["metadata"], body + "Updated\n", current["revision"])
    assert updated["revision"] != current["revision"]


def test_exact_dependency_resolution_deduplicates_and_tracks_metadata(tmp_path):
    library = InstructionLibrary(StorageLayout(tmp_path))
    common = library.save("common.md", metadata("common"), "Common body")
    library.save("first.md", metadata("first", instructions={"base": "[[common]]"}), "First [[not-required]]")
    library.save("second.md", metadata("second", instructions={"base": "[[common]]"}), "Second")
    result = library.resolve(["first", "[[second|Label]]", "first"])
    assert [item["id"] for item in result["instructions"]] == ["common", "first", "second"]
    library.save("common.md", metadata("common", config={"changed": True}), "Common body", common["revision"])
    assert library.resolve(["first", "second"])["revision"] != result["revision"]
    first = library.read("first")
    library.save("first.md", metadata("first", instructions={"self": "[[first]]"}), "body", first["revision"])
    with pytest.raises(ValueError, match="Cyclic"):
        library.resolve(["first"])


def test_ambiguity_duplicate_identity_and_invalid_dependency_fail_closed(tmp_path):
    library = InstructionLibrary(StorageLayout(tmp_path))
    library.save("a/rules.md", metadata("first"), "one")
    library.save("b/rules.md", metadata("second"), "two")
    with pytest.raises(ValueError, match="Ambiguous"):
        library.read("[[rules]]")
    assert library.read("a/rules.md")["id"] == "first"
    with pytest.raises(ValueError, match="Duplicate"):
        library.save("another.md", metadata("first"), "duplicate")
    library.save("missing.md", metadata("missing", instructions={"base": "[[absent]]"}), "body")
    with pytest.raises(ValueError, match="Missing"):
        library.resolve(["missing"])


@pytest.mark.parametrize("path", ["../escape.md", "/escape.md", "nested/../../escape.md", ".hidden.md", "rules.txt", "a\\b.md", "C:escape.md"])
def test_path_rejection_precedes_writes(tmp_path, path):
    root = tmp_path / "absent"
    library = InstructionLibrary(StorageLayout(root))
    with pytest.raises(ValueError):
        library.save(path, metadata("id"), "body")
    assert not root.exists()


def test_symlinks_and_invalid_source_yaml_are_errors(tmp_path):
    library = InstructionLibrary(StorageLayout(tmp_path / "root"))
    library.save("a.md", metadata("a"), "body")
    (library.root / "alias.md").symlink_to(library.root / "a.md")
    with pytest.raises(ValueError, match="symlink"):
        library.read("a")
    (library.root / "alias.md").unlink()
    (library.root / "invalid.md").write_text("---\nid: invalid\nid: duplicate\ntype: instruction\n---\nbody")
    with pytest.raises(ValueError, match="unique"):
        library.list()


def test_missing_reconcile_source_refuses_deletions_and_core_passthrough_avoids_scan(tmp_path):
    index = RagIndex(StorageLayout(tmp_path))
    library = InstructionLibrary(index.layout, index)
    with patch("contextopus.core.documents.instructions.reconcile_index") as reconcile:
        with pytest.raises(ValueError, match="source directory is missing"):
            library.reconcile()
        reconcile.assert_not_called()
    with patch.object(library, "_snapshot", side_effect=AssertionError("Unexpected instruction scan")):
        row = {"module": "core", "collection": "search_algorithm", "object_id": "algorithm",
               "revision": "revision", "path": "algorithm.md", "metadata": '{}'}
        result = library.eligible_documents([row])
        assert result[DocumentKey("core", "search_algorithm", "algorithm")].revision == "revision"


def test_invalid_nested_yaml_metadata_rejected_before_source_creation(tmp_path):
    root = tmp_path / "absent"
    library = InstructionLibrary(StorageLayout(root))
    with pytest.raises(ValueError, match="unique strings"):
        library.save("bad.md", metadata("bad", config={1: "numeric key"}), "body")
    assert not root.exists()


def test_failed_index_save_is_readable_and_explicit_reconcile_repairs(tmp_path):
    factory = Factory()
    config = default_config()
    config["profile"]["dimensions"] = 2
    with ProcessResources(factory) as resources:
        index = RagIndex(StorageLayout(tmp_path), resources, embeddings=config)
        library = InstructionLibrary(index.layout, index)
        with patch.object(index, "index", side_effect=RuntimeError("embedding unavailable")):
            saved = library.save("a.md", metadata("a"), "Complete authoritative body")
        assert saved["index"] == {"status": "pending", "error": "embedding unavailable"}
        assert library.read("a")["content"] == "Complete authoritative body"
        assert library.reconcile()["indexed"] == 1
        calls = len(factory.calls)
        path = library.root / "a.md"
        path.write_text(path.read_text().replace("title: a", "title: New title"))
        assert library.reconcile()["refreshed"] == 1
        assert len(factory.calls) == calls
        selection = {"algorithm": "none", "parameters": {"page_size": 20}}
        assert library.search("authoritative", selection=selection)["results"]
        path.write_text(path.read_text().replace("Complete authoritative body", "New source body"))
        assert library.search("authoritative", selection=selection)["results"] == []
        assert library.reconcile()["indexed"] == 1
        unrelated = IndexDocument(DocumentKey("core", "search_algorithm", "algorithm"),
                                  "revision", "Algorithm", "algorithm.md", {"type": "algorithm"})
        index.index(unrelated)
        assert index.search_detailed("Algorithm", module="core", collection="search_algorithm",
                                     selection=selection)["results"]
        path.unlink()
        result = library.search("authoritative", selection=selection)
        assert result["results"] == []
        assert library.reconcile()["deleted"] == 1
        assert index.read_rows(index.table, predicate=index.key_predicate(unrelated.key))


def test_core_registry_exposes_typed_instruction_operations_without_models(tmp_path):
    def forbidden(config):
        raise AssertionError("Instruction file operation loaded an embedding model")

    with ProcessResources(forbidden) as resources:
        with Application(tmp_path / "root", resources=resources, discover=False) as app:
            operations = app.query("describe")["operations"]
            assert "core.instructions_read" in operations["query"]
            assert "core.instructions_save" in operations["execute"]
            assert app.query("core.instructions_list") == {"instructions": []}
            saved = app.execute("core.instructions_save", {"path": "main.md", "metadata": metadata("main"), "content": "Main"})
            assert saved["index"]["status"] == "pending"
            assert not resources.providers._entries
            assert not (app.layout.rag / "active.json").exists()
            assert app.execute("core.instructions_reconcile")["status"] == "pending"
            assert not resources.providers._entries
            assert app.query("core.instructions_read", {"reference": "main"})["content"] == "Main"
            assert app.query("core.instructions_resolve", {"references": ["main"]})["instructions"][0]["id"] == "main"

"""File-source deletion safety, identity, metadata and required-link behavior."""

from dataclasses import replace
from unittest.mock import patch

import pytest

from contextopus.core.documents import SourceSnapshot, plan, resolve_required, scan_markdown
from contextopus.core.documents import files
from contextopus.core.rag import DocumentKey, IndexDocument


def write(root, name, ident, body="Body", extra=""):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nid: {ident}\ntype: instruction\n{extra}---\n{body}", encoding="utf-8")
    return path


def scan(root):
    return scan_markdown(root, module="demo", collection="rules")


def test_create_edit_move_metadata_delete_and_isolation(tmp_path):
    a = write(tmp_path, "one.md", "stable", extra="model: sample\n")
    old = scan(tmp_path)
    assert len(plan(old, []).upsert) == 1
    assert old.documents[0].text == "Body"
    assert old.documents[0].metadata["model"] == "sample"
    a.rename(tmp_path / "renamed.md")
    moved = scan(tmp_path)
    delta = plan(moved, old.documents)
    assert not delta.upsert and not delta.delete
    assert delta.refresh[0].location == "renamed.md"
    write(tmp_path, "renamed.md", "stable", extra="model: changed\n")
    metadata = scan(tmp_path)
    assert len(plan(metadata, moved.documents).refresh) == 1
    write(tmp_path, "renamed.md", "stable", body="New instructions")
    edited = scan(tmp_path)
    assert len(plan(edited, metadata.documents).upsert) == 1
    (tmp_path / "renamed.md").unlink()
    assert plan(scan(tmp_path), edited.documents).delete == (edited.documents[0].key,)
    foreign = replace(edited.documents[0], key=DocumentKey("other", "rules", "stable"))
    with pytest.raises(ValueError, match="scope"):
        plan(scan(tmp_path), [foreign])


def test_partial_and_failed_scans_never_infer_deletion(tmp_path):
    write(tmp_path, "a.md", "a")
    old = scan(tmp_path)
    partial = SourceSnapshot("demo", "rules", ())
    assert not plan(partial, old.documents).delete
    with pytest.raises(ValueError, match="scan failed"):
        plan(replace(partial, complete=True, errors=("unreadable",)), old.documents)
    with pytest.raises(ValueError, match="missing"):
        scan(tmp_path / "missing")
    with patch.object(files.os, "walk", side_effect=PermissionError("blocked")):
        with pytest.raises(PermissionError):
            scan(tmp_path)


@pytest.mark.parametrize("content", ["no YAML", "---\nid: a", "---\nid: a\nid: b\ntype: instruction\n---\n",
                                      "---\nid: a\ntype: [\n---\n"])
def test_malformed_files_abort_whole_scan(tmp_path, content):
    write(tmp_path, "good.md", "good")
    (tmp_path / "bad.md").write_text(content, encoding="utf-8")
    with pytest.raises((ValueError, files.yaml.YAMLError)):
        scan(tmp_path)


def test_duplicate_ids_and_validator_failure_abort(tmp_path):
    write(tmp_path, "one.md", "duplicate")
    write(tmp_path, "two.md", "duplicate")
    with pytest.raises(ValueError, match="Duplicate"):
        scan(tmp_path)
    (tmp_path / "two.md").unlink()
    def validate(document):
        raise ValueError("Invalid module configuration")
    with pytest.raises(ValueError, match="module configuration"):
        scan_markdown(tmp_path, module="demo", collection="rules", validate=validate)


def test_observed_concurrent_edit_aborts_scan(tmp_path):
    path = write(tmp_path, "one.md", "one")
    reader = files.read_document
    def edit(*args, **kwargs):
        result = reader(*args, **kwargs)
        path.write_text(path.read_text(encoding="utf-8") + " changed", encoding="utf-8")
        return result
    with patch.object(files, "read_document", side_effect=edit):
        with pytest.raises(ValueError, match="changed during scan"):
            scan(tmp_path)


def test_required_links_deduplicate_ignore_ordinary_links_and_return_full_text(tmp_path):
    write(tmp_path, "shared.md", "shared", body="All the rules, verbatim.")
    write(tmp_path, "first.md", "first", extra='instructions: {shared: "[[shared|Shared rules]]"}\nlinks: ["[[missing]]"]\n')
    write(tmp_path, "second.md", "second", extra='instructions: {shared: "[[shared.md]]"}\n')
    docs = scan(tmp_path).documents
    found = resolve_required(docs, ["[[first]]", "[[second]]"])
    assert [x.key.id for x in found] == ["shared", "first", "second"]
    assert found[0].text == "All the rules, verbatim."
    with pytest.raises(ValueError, match="Missing"):
        resolve_required(docs, ["[[unknown]]"])


def test_required_cycles_and_ambiguous_names_fail(tmp_path):
    write(tmp_path, "a.md", "a", extra='instructions: {shared: "[[b]]"}\n')
    write(tmp_path, "b.md", "b", extra='instructions: {shared: "[[a]]"}\n')
    with pytest.raises(ValueError, match="Cyclic"):
        resolve_required(scan(tmp_path).documents, ["[[a]]"])
    write(tmp_path, "nested/a.md", "different")
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_required(scan(tmp_path).documents, ["[[a]]"])


def test_scan_skips_hidden_work_and_rejects_symlinks(tmp_path):
    write(tmp_path, ".tmp/hidden.md", "hidden")
    write(tmp_path, "visible.md", "visible")
    assert len(scan(tmp_path).documents) == 1
    try:
        (tmp_path / "linked.md").symlink_to(tmp_path / "visible.md")
    except OSError:
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ValueError, match="symlink"):
        scan(tmp_path)

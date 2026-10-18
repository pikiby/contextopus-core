"""Bounded public relocation reviews retain exact durable manifests."""

import json
from unittest.mock import patch

import pytest

from contextopus.core import relocation
from contextopus.startup import Application


def source_tree(tmp_path):
    source = tmp_path / "source"
    path = source / ".pcw/alpha/knowledge/topic.md"
    path.parent.mkdir(parents=True)
    path.write_text("original bytes")
    return source, tmp_path / "destination"


def test_large_manifest_review_is_bounded_and_handle_survives_application_restart(
    tmp_path,
):
    source, destination = source_tree(tmp_path)
    original = relocation.plan

    def large_manifest(*args):
        value = original(*args)
        value["files"][0]["review_metadata"] = "x" * (6 * 1024 * 1024)
        value["revision"] = relocation._revision(value)
        return value

    with Application(source, discover=False) as app:
        with patch.object(relocation, "plan", side_effect=large_manifest):
            review = app.query(
                "core.relocation_plan", {"destination": str(destination)}
            )
        assert len(json.dumps(review)) < 4096
        assert review["manifest"]["bytes"] > 6 * 1024 * 1024
        assert review["files"] >= 1
        assert review["contexts"] == ["alpha"]
        assert review["effects"]["initializes_missing_instructions"] is False
    with Application(source, discover=False) as restarted:
        result = restarted.execute(
            "core.relocation_apply", {"plan_revision": review["revision"]}
        )
        assert result["status"] == "complete"
    assert (
        destination / "modules/workspace/workspace_contexts/alpha/knowledge/topic.md"
    ).read_text() == "original bytes"


def test_partial_freeze_retry_uses_owned_plan_after_restart(tmp_path):
    source, destination = source_tree(tmp_path)
    with Application(source, discover=False) as app:
        review = app.query("core.relocation_plan", {"destination": str(destination)})
        with patch.object(
            relocation.shutil, "copy2", side_effect=OSError("interrupted")
        ):
            with pytest.raises(OSError):
                app.execute(
                    "core.relocation_apply", {"plan_revision": review["revision"]}
                )
    assert (source / ".contextopus-freeze.json").is_file()
    with Application(source, discover=False) as restarted:
        resumed = restarted.query(
            "core.relocation_plan", {"destination": str(destination)}
        )
        assert resumed == review
        assert (
            restarted.execute(
                "core.relocation_apply", {"plan_revision": review["revision"]}
            )["status"]
            == "complete"
        )


def test_tampered_owned_artifact_and_foreign_handle_are_rejected(tmp_path):
    source, destination = source_tree(tmp_path)
    with Application(source, discover=False) as app:
        review = app.query("core.relocation_plan", {"destination": str(destination)})
        artifact = __import__("pathlib").Path(review["manifest"]["path"])
        value = json.loads(artifact.read_text())
        value["destination"] = str(tmp_path / "unexpected")
        artifact.write_text(json.dumps(value))
        with pytest.raises(ValueError, match="revision"):
            app.execute("core.relocation_apply", {"plan_revision": review["revision"]})
        with pytest.raises(ValueError, match="revision"):
            app.execute("core.relocation_apply", {"plan_revision": "../outside"})
    assert (source / ".pcw").is_dir()
    assert not destination.exists()


def test_permanent_source_change_stales_review_but_observer_query_does_not(tmp_path):
    source, destination = source_tree(tmp_path)
    with Application(source, discover=False) as app:
        review = app.query("core.relocation_plan", {"destination": str(destination)})
        app.query("core.doctor")
        assert (
            app.query("core.relocation_plan", {"destination": str(destination)})
            == review
        )
        (source / ".pcw/alpha/knowledge/topic.md").write_text("changed source")
        with pytest.raises(ValueError, match="Source changed"):
            app.execute("core.relocation_apply", {"plan_revision": review["revision"]})


def test_open_layout_unicode_review_survives_owned_artifact_reload(tmp_path):
    source = tmp_path / "исходный-корень"
    document = source / "modules/workspace/workspace_contexts/проект/knowledge/тема.md"
    document.parent.mkdir(parents=True)
    document.write_text("Исходный текст", encoding="utf-8")
    destination = tmp_path / "новое-место"
    with Application(source, discover=False) as app:
        review = app.query("core.relocation_plan", {"destination": str(destination)})
        assert review["contexts"] == ["проект"]
        assert review["context_count"] == 1
    with Application(source, discover=False) as restarted:
        assert (
            restarted.execute(
                "core.relocation_apply", {"plan_revision": review["revision"]}
            )["status"]
            == "complete"
        )
    assert (
        destination / "modules/workspace/workspace_contexts/проект/knowledge/тема.md"
    ).read_text(encoding="utf-8") == "Исходный текст"


def test_relocation_preserves_unfinished_temporary_cards_and_pending_proposals(tmp_path):
    source, destination = source_tree(tmp_path)
    relative = 'alpha/.tmp/unfinished'
    files = {
        f'{relative}/materials/Readable finding.md': '---\nid: stable-card\ntype: knowledge\nlinks: []\n---\n# Unfinished evidence\n',
        f'{relative}/proposals/pending.json': '{"revision": "exact pending proposal"}\n',
    }
    for name, content in files.items():
        path = source / '.pcw' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    with Application(source, discover=False) as app:
        review = app.query('core.relocation_plan', {'destination': str(destination)})
        assert app.execute('core.relocation_apply', {'plan_revision': review['revision']})['status'] == 'complete'
    for name, content in files.items():
        assert (destination / 'modules/workspace/workspace_contexts' / name).read_text() == content

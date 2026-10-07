"""Workspace approval policy with real cycle storage and deterministic vectors."""
from unittest.mock import patch

import pytest

from pcw_runtime import PCWError
from pcw_runtime.server import pcw_query
from test_cycles import workspace
from test_instructions import edit, apply as apply_instructions


def policy(required):
    return f"---\nknowledge_approval_required: {str(required).lower()}\n---\n# Project\n"


def prepare(r, c, text="# Facts\nAccurate project description"):
    return r.proposal_prepare(c, [{"key": "topic", "content": text}])


def apply_knowledge(r, c, p, **kwargs):
    return r.proposal_apply(c, p["proposal_id"], p["revision"], **kwargs)


def test_default_shows_changes_then_applies_indexes_and_closes_without_confirmation(workspace):
    r, _ = workspace
    opened = r.startup("auto")
    c = opened["cycle_id"]
    assert "knowledge_approval_required: false" in opened["instructions"]["content"]
    r.tmp_write(c, "Verified result")
    p = prepare(r, c)
    assert p["approval_required"] is False
    assert p["next_action"] == "present_changes_in_chat_then_apply"
    assert p["review_changes"][0]["body_changes"][0]["after"] == "# Facts\nAccurate project description"
    assert r.proposal_read(c, p["proposal_id"])["approval_required"] is False
    assert r.status(c)["materials"] == 0
    assert r.finish(c)["status"] == "blocked"
    result = apply_knowledge(r, c, p)
    assert result["status"] == "applied" and result["materials"][0]["index_status"] == "indexed"
    assert r._tmp(c).exists()
    assert apply_knowledge(r, c, p)["replayed"]
    assert r.finish(c)["tmp_cleared"]


@pytest.mark.parametrize("content", [policy(True), "# Existing custom rules", "", "# Rules\nknowledge_approval_required: false"])
def test_manual_or_missing_policy_requires_actual_confirmation_without_mutation(workspace, content):
    r, f = workspace
    c = r.startup("manual")["cycle_id"]
    apply_instructions(r, c, edit(r, c, content))
    p = prepare(r, c)
    assert p["approval_required"] is True
    assert p["next_action"] == "present_changes_in_chat_for_approval"
    for confirmation in (None, "", " "):
        with pytest.raises(PCWError, match="confirmation"):
            apply_knowledge(r, c, p, confirmation=confirmation)
    assert r.status(c)["materials"] == 0 and f.calls == []
    assert apply_knowledge(r, c, p, confirmation="Approve the shown text")["status"] == "applied"


@pytest.mark.parametrize("required", [False, True])
def test_instructions_always_require_approval_and_cannot_use_knowledge_apply(workspace, required):
    r, _ = workspace
    c = r.startup("rules")["cycle_id"]
    apply_instructions(r, c, edit(r, c, policy(required)))
    before = r.instructions_read(c)
    p = edit(r, c, policy(not required))
    assert p["approval_required"] is True
    assert p["next_action"] == "present_changes_in_chat_for_approval"
    with pytest.raises(PCWError, match="confirmation"):
        r.instructions_apply(c, p["proposal_id"], p["revision"], "")
    with pytest.raises(PCWError, match="instructions_apply"):
        apply_knowledge(r, c, p)
    assert r.instructions_read(c) == before


@pytest.mark.parametrize("header", [
    'knowledge_approval_required: "false"', 'knowledge_approval_required: null',
    'knowledge_approval_required: 0', 'knowledge_approval_required: no',
    'knowledge_approval_required: [false]',
    'knowledge_approval_required: true\nknowledge_approval_required: false',
    '- false', 'knowledge_approval_required: [',
])
def test_invalid_policy_fails_without_saving_a_proposal_or_changing_instructions(workspace, header):
    r, _ = workspace
    c = r.startup("invalid")["cycle_id"]
    before = r.instructions_read(c)
    with pytest.raises(PCWError):
        edit(r, c, "---\n" + header + "\n---\n")
    assert r.instructions_read(c) == before
    # Manual invalid files can still be read/repaired, but cannot authorize a write.
    (r.engine.root / "INSTRUCTIONS.md").write_text("---\n" + header + "\n---\n")
    with pytest.raises(PCWError):
        prepare(r, c)
    assert r.status(c)["materials"] == 0
    assert r.status(c)["outstanding_proposal_count"] == 0


@pytest.mark.parametrize("required", [False, True])
def test_policy_change_invalidates_old_preparation_in_both_directions(workspace, required):
    r, _ = workspace
    c = r.startup("change")["cycle_id"]
    apply_instructions(r, c, edit(r, c, policy(required)))
    p = prepare(r, c)
    apply_instructions(r, c, edit(r, c, policy(not required)))
    with pytest.raises(PCWError, match="Instructions changed"):
        apply_knowledge(r, c, p, confirmation="yes")
    assert r.status(c)["materials"] == 0
    renewed = r.proposal_prepare(c, [{"key": "topic", "content": "Fact"}], proposal_id=p["proposal_id"])
    assert renewed["approval_required"] is not required


def test_automatic_retry_recovers_same_partial_write_after_policy_changes(workspace):
    r, _ = workspace
    c = r.startup("recovery")["cycle_id"]
    p = prepare(r, c)
    write = r.engine._write
    def fail(path, text):
        write(path, text)
        if path.parent == r.engine.knowledge:
            raise OSError("write acknowledgement lost")
    with patch.object(r.engine, "_write", side_effect=fail):
        assert apply_knowledge(r, c, p)["status"] == "partial"
    apply_instructions(r, c, edit(r, c, policy(True)))
    assert apply_knowledge(r, c, p)["status"] == "applied"
    assert r.status(c)["materials"] == 1
    assert r.finish(c)["status"] == "blocked"
    r.proposal_prepare(c, [], no_changes_reason="The same stored fact meets the updated rules")
    assert r.finish(c)["status"] == "closed"


def test_auto_mode_still_checks_file_conflicts_and_full_revision(workspace):
    r, _ = workspace
    c = r.startup("conflict")["cycle_id"]
    seed = prepare(r, c)
    apply_knowledge(r, c, seed)
    material = r.read(c, seed["created_ids"]["topic"])
    p = r.proposal_prepare(c, [{"material_id": material["id"], "expected_revision": material["revision"], "content": "Updated fact"}])
    with pytest.raises(PCWError, match="exact presented"):
        r.proposal_apply(c, p["proposal_id"], "wrong")
    path = r.engine.root / material["path"]
    path.write_text(path.read_text() + "\nConcurrent edit")
    with pytest.raises(PCWError, match="conflict"):
        apply_knowledge(r, c, p)
    assert "Concurrent edit" in path.read_text()


def test_mcp_schema_allows_omitting_confirmation_only_for_knowledge():
    knowledge = pcw_query("describe", arguments={"operation": "proposal_apply"})["arguments_schema"]
    instructions = pcw_query("describe", arguments={"operation": "instructions_apply"})["arguments_schema"]
    assert "confirmation" not in knowledge["required"]
    assert "confirmation" in instructions["required"]
    assert "knowledge_approval_required" not in knowledge["properties"]

"""Regression of the observed PCW failures, using real files, LanceDB and Git."""
import shutil
from pathlib import Path
import re
from unittest.mock import patch

import pytest

from test_runtime import Factory
from pcw_runtime import PCWRuntime
from pcw_runtime.control import RecoveryRequired
from pcw_runtime.agent_workflow import AgentWorkflow
from workflow_helpers import open_task, register, process, finish


@pytest.fixture
def workspace(tmp_path):
    runtime = PCWRuntime(tmp_path, "closeout", provider_factory=Factory())
    open_task(runtime)
    runtime.current_set(goal="Test request", constraints="Temporary test memory", completion="Verified result", step="Working", blocker="")
    yield runtime
    runtime.close()


def prepare(runtime, ident):
    p = runtime.prepare(ident)
    runtime.submit_parts(ident, p["revision"], [p["content"]])


def test_mcp_generates_both_ordinary_and_raw_filenames(workspace):
    runtime = workspace
    item = runtime.create("# Source knowledge")
    assert re.fullmatch(r"[a-f0-9]{32}\.md", item["id"])
    assert item["path"] == "knowledge/" + item["id"]
    with pytest.raises(TypeError):
        runtime.create(path="chosen.md", content="no")
    assignment = register(runtime)
    saved = runtime.save_subagent_result(assignment, "Raw exact\n", "worker-1")
    assert re.fullmatch(r"[a-f0-9]{32}\.md", saved["id"])
    assert saved["id"] != item["id"]
    assert runtime.read(saved["id"])["content"] == "Raw exact\n"


def test_finish_blocks_pending_and_missing_checkpoint_and_ignores_unrelated_pending(workspace):
    runtime = workspace
    item = runtime.create("# Observed result")
    result = finish(runtime)
    assert not result["ready"]
    assert any(m["action"] == "prepare" for m in result["missing"])
    assert any(m["action"] == "checkpoint" for m in result["missing"])
    prepare(runtime, item["id"])
    assert not finish(runtime)["ready"]
    assert runtime.checkpoint(["current.md", item["path"]], "Temporary fixture")["status"] == "ok"
    assert finish(runtime)["ready"]


def test_unsaved_recovery_return_blocks_finish_after_repair(workspace):
    runtime = workspace
    shutil.rmtree(runtime.state)
    flow = AgentWorkflow(runtime)
    assert flow.environment_get()["status"] == "current"
    req = flow.action_requirements("finish")
    assert req["requirements"] and not req["ready"]
    assignment = register(runtime, "diagnostic", purpose="work")
    with pytest.raises(RecoveryRequired):
        runtime.status()
    assert runtime.recover_workspace()["status"] == "recovered"
    missing = finish(runtime)
    assert any(m["field"] == "assignments." + assignment for m in missing["missing"])
    raw = runtime.save_subagent_result(assignment, "Recovered only the runtime directory.\n", "diagnostic")
    assert not finish(runtime)["ready"]
    process(runtime, assignment, raw)
    prepare(runtime, raw["id"])
    runtime.checkpoint(["current.md", raw["path"]], "Record diagnostic return")
    assert finish(runtime)["ready"]


def test_missing_knowledge_is_not_silently_recreated(workspace):
    runtime = workspace
    shutil.rmtree(runtime.root)
    with pytest.raises(RecoveryRequired):
        runtime.status()
    assert AgentWorkflow(runtime).task_status()["task"] is not None
    assert runtime.recover_workspace()["status"] == "blocked"
    assert not runtime.knowledge.exists()
    fresh = PCWRuntime(runtime.work_root, runtime.root.name, provider_factory=Factory(), initialize=False)
    try:
        with pytest.raises(RecoveryRequired):
            fresh.status()
    finally:
        fresh.close()


def test_complete_context_is_retrieved_and_read_is_required(workspace):
    runtime = workspace
    assignment = register(runtime, goal="Fresh indexed state, not earlier pending status")
    handoff = AgentWorkflow(runtime).ledger.handoff(AgentWorkflow(runtime).task_status()["task"]["assignments"][assignment])
    assert handoff["assignment"]["context"]["summary"] == "Fresh indexed state, not earlier pending status"
    raw = runtime.save_subagent_result(assignment, "pending_preparation", "worker-1")
    flow = AgentWorkflow(runtime)
    result = flow.action_requirements("process_result", {"result": {"assignment_id": assignment,
        "material_name": raw["id"], "executor_session_id": "worker-1"},
        "assessment": {"status": "accepted", "reason": "not read"}})
    assert not result["ready"]
    process(runtime, assignment, raw, status="needs_attention")
    assert any("discrepancy" in m["reason"] for m in finish(runtime)["missing"])
    process(runtime, assignment, raw, status="accepted")
    assert any("discrepancy" in m["reason"] for m in finish(runtime)["missing"])
    clarification = register(runtime, goal="Recheck actual index status", continuation_of=assignment)
    corrected = runtime.save_subagent_result(clarification, "Observed indexed", "worker-1", raw["revision"])
    runtime.read(corrected["id"], assignment_id=clarification)
    blocked = flow.result_assess(clarification, {"status": "accepted", "reason": "Clarification alone",
                                               "resolves": [assignment]})
    assert not blocked["ready"]
    runtime.update(raw["id"], "Actual observed state is indexed", expected_revision=raw["revision"])
    process(runtime, clarification, corrected, resolves=[assignment])
    assert not any("discrepancy" in m["reason"] for m in finish(runtime)["missing"])


def test_instructions_and_recovery_assignment_survive_an_index_exception(workspace):
    runtime = workspace
    with patch.object(runtime, "_reconcile", side_effect=RuntimeError("Injected unreadable index")):
        flow = AgentWorkflow(runtime)
        assert flow.tools_map_get()["status"] == "current"
        requirements = flow.action_requirements("finish")
        assert requirements["requirements"] and not requirements["ready"]
        assignment = register(runtime, "recovery", purpose="work")
        assert flow.task_status()["task"]["assignments"][assignment]["delivered_at"]


def test_checkpoint_prohibition_and_unrelated_changes_are_respected(tmp_path):
    runtime = PCWRuntime(tmp_path, "scope", provider_factory=Factory())
    try:
        unrelated = runtime.create("Unrelated pending body")
        open_task(runtime, checkpoint_policy="forbidden")
        runtime.current_set(goal="Test request", constraints="Temporary test memory", completion="Verified result", step="Done", blocker="")
        own = runtime.create("Owned result")
        prepare(runtime, own["id"])
        # A direct concurrent edit to an unrelated file must not become a
        # required checkpoint path of the active request.
        (runtime.root / unrelated["path"]).write_text("Concurrent unrelated edit\n")
        assert runtime.status()["pending_count"] == 1
        assert finish(runtime)["ready"]
        assert not (runtime.root / ".git").exists()
    finally:
        runtime.close()


def test_invalid_material_and_stale_current_block_completion(workspace):
    runtime = workspace
    (runtime.root / "current.md").write_text(runtime._render_current({**runtime.current_get(), "goal": "Different request"}))
    result = finish(runtime)
    assert not result["ready"]
    assert any(m["field"] == "current.goal" for m in result["missing"])
    runtime.current_set(goal="Test request")
    runtime._write(runtime.knowledge / "invalid.md", "---\nlinks: not-a-list\n---\nchanged")
    result = finish(runtime)
    assert result["requirements"] and not result["ready"]
    assert any(m["field"] == "runtime" and "links must be a list" in m["reason"] for m in result["missing"])


def test_processed_raw_can_be_compacted_without_retaining_source_metadata(workspace):
    runtime = workspace
    assignment = register(runtime, purpose="check")
    raw = runtime.save_subagent_result(assignment, "Verified fact with redundant wording", "worker-1")
    process(runtime, assignment, raw)
    final = runtime.create("Verified fact")
    assert runtime.delete(raw["id"])["status"] == "ok"
    prepare(runtime, final["id"])
    runtime.checkpoint(["current.md", final["path"]], "Retain compacted knowledge")
    result = AgentWorkflow(runtime).action_requirements("finish", {"acceptance_checks": {
        "status": "assigned", "scope": "Test request", "checks": [{"assignment_id": assignment,
        "material_name": raw["id"], "executor_session_id": "worker-1"}]}})
    assert result["ready"], result
    assert "saved_at" not in runtime.read(final["id"])

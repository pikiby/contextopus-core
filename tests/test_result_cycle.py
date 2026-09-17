"""Regression coverage for the ordinary return -> memory cycle, including failures."""
import pytest

from pcw_runtime.agent_workflow import AgentWorkflow
from pcw_runtime.assignments import TaskLedger
from pcw_runtime.runtime import PCWError
from test_runtime_071 import memory
from workflow_helpers import register, finish


def evidence(ident="worker-1"):
    return {"source": "native_launch", "reference": "fixture launch response", "executor_session_id": ident}


def accept(flow, aid, **extra):
    result = flow.result_assess(aid, {"status": "accepted", "reason": "Observed actual fixture result", **extra})
    assert result["ready"], result


def test_incomplete_return_continues_without_knowledge_or_false_acceptance(memory):
    runtime, factory = memory
    flow = AgentWorkflow(runtime)
    aid = register(runtime)
    result = flow.return_record(aid, "worker-1", "incomplete", "File created; full text omitted",
                                "Required content is missing", ["Return the full written content"])
    assert result["result_storage"] == "control"
    assert not runtime.materials and not factory.instances
    assert not flow.result_assess(aid, {"status": "accepted", "reason": "File exists"})["ready"]
    assert not finish(runtime)["ready"]
    next_id = register(runtime, session="fresh-child", continuation_of=aid, goal="Return the omitted full text")
    # This follow-up adds no reusable knowledge: it is evidence about an external artifact.
    flow.return_record(next_id, "fresh-child", "complete", "Full literal fixture note and resolving link checks",
                       "Artifact verification only; no new durable project facts", [])
    accept(flow, next_id, resolves=[aid])
    assert finish(runtime)["ready"]
    assert not list(runtime.knowledge.glob("*.md"))
    assert not factory.instances


def test_control_factual_check_can_finish_without_a_material_coordinate(memory):
    runtime, _ = memory
    flow = AgentWorkflow(runtime)
    aid = register(runtime, purpose="check")
    flow.return_record(aid, "worker-1", "complete", "Actual note equals expected text; link targets exist",
                       "Verification observations belong to the task log", [])
    accept(flow, aid)
    result = flow.finish({"status": "assigned", "scope": "Verify fixture note",
                          "checks": [{"assignment_id": aid, "executor_session_id": "worker-1"}]})
    assert result["ready"], result


def test_composite_store_reads_disk_links_topics_and_skips_separate_prepare(memory):
    runtime, factory = memory
    flow = AgentWorkflow(runtime)
    aid = register(runtime)
    bodies = ["# Routing\n\nThe API routes requests.\n", "# Storage\n\nThe database persists rows.\n"]
    links = [{"block": 1, "to_blocks": [2]}, {"block": 2, "to_blocks": [1]}]
    stored = runtime.result_store(aid, "worker-1", bodies, links)
    assert stored["complete"] and stored["read_back_verified"] and stored["assessment_required"]
    assert [m["content"] for m in stored["materials"]] == bodies
    ids = [m["id"] for m in stored["materials"]]
    assert stored["materials"][0]["links"] == [ids[1]]
    assert stored["materials"][1]["links"] == [ids[0]]
    assert len(runtime.materials) == 2 and not factory.instances
    accept(flow, aid)
    again = runtime.result_store(aid, "worker-1", bodies, links)
    assert again["status"] == "already_saved" and again["split_sources"] == stored["split_sources"]
    # Accepted return is not repeated in startup; pending IDs remain available.
    startup = flow.startup()
    assert startup["assignments"] == [] and set(startup["pending_material_ids"]) == set(ids)
    assignment = flow.task_status()["task"]["assignments"][aid]["assignment"]
    prepared = flow.assignment_prepare({**assignment, "purpose": "semantic_split", "goal": "Return boundaries for supplied texts"},
                                       split_sources=stored["split_sources"])
    assert prepared["ready"], prepared
    handoff = prepared["handoff"]
    flow.assignment_bind(handoff["assignment_id"], "splitter", evidence("splitter"))
    runtime.submit_boundaries_many(handoff["assignment_id"], "splitter",
        [{"text_number": n, "boundaries": [len(body.splitlines(keepends=True))]} for n, body in enumerate(bodies, 1)])
    assert finish(runtime)["ready"]
    startup = flow.startup()
    assert startup["assignments"] == [] and startup["checks_plan"] == []
    assert len(flow.task_status()["task"]["assignments"]) == 2  # Explicit history is intact.
    assert runtime.result_store(aid, "worker-1", bodies, links)["status"] == "already_saved"
    assert flow.task_status()["status"] == "complete"
    with pytest.raises(PCWError, match="completed task"):
        runtime.result_store(aid, "worker-1", ["Different", bodies[1]], links)


def test_composite_store_validates_links_before_writes_and_readback_before_receipt(memory, monkeypatch):
    runtime, _ = memory
    aid = register(runtime)
    with pytest.raises(PCWError):
        runtime.result_store(aid, "worker-1", ["Fact"], [{"block": 1, "to_blocks": [2]}])
    assert not runtime.materials
    save = runtime._save
    def corrupt(material):
        save(material)
        path = runtime.root / material.path
        path.write_text(path.read_text() + "unexpected text")
    monkeypatch.setattr(runtime, "_save", corrupt)
    result = runtime.result_store(aid, "worker-1", ["Fact"])
    assert not result["complete"] and not result["read_back_verified"]
    entry = TaskLedger(runtime).entry(TaskLedger(runtime).load(), aid)[1]
    assert not entry.get("read_revision")


def test_composite_store_retries_link_failure_without_duplicate_materials(memory, monkeypatch):
    runtime, _ = memory
    aid = register(runtime)
    links_many = runtime.links_many
    monkeypatch.setattr(runtime, "links_many", lambda changes: {"status": "partial", "error": "fixture link failure"})
    links = [{"block": 1, "to_blocks": [2]}]
    first = runtime.result_store(aid, "worker-1", ["Routing", "Storage"], links)
    assert not first["complete"]
    assert any("storage" in m["field"] for m in TaskLedger(runtime).completion_missing())
    assert not AgentWorkflow(runtime).result_assess(aid, {"status": "accepted", "reason": "Bodies alone exist"})["ready"]
    monkeypatch.setattr(runtime, "links_many", links_many)
    second = runtime.result_store(aid, "worker-1", ["Routing", "Storage"], links)
    assert second["complete"] and [m["id"] for m in second["materials"]] == first["material_ids"]


def test_wrong_binding_blocks_old_id_workaround_and_can_be_repaired(memory):
    runtime, _ = memory
    flow = AgentWorkflow(runtime)
    aid = register(runtime, session="parent-shared")
    stored = runtime.result_store(aid, "parent-shared", ["# Routing\nThe API routes requests."])
    accept(flow, aid)
    material = stored["materials"][0]
    with pytest.raises(ValueError, match="another executor"):
        flow.assignment_bind(aid, "worker-1", evidence())
    with pytest.raises(ValueError, match="identity conflict"):
        flow.assignment_bind(aid, "parent-shared")
    assert any("identity" in m["field"] for m in flow.ledger.completion_missing())
    repaired = runtime.assignment_rebind([aid], "parent-shared", "worker-1", evidence(), "Native launch identifies the child")
    assert repaired["status"] == "corrected"
    actual = runtime.read(material["id"])
    assert actual["executor_session_id"] == "worker-1" and actual["revision"] == material["revision"]
    assert actual["content"] == material["content"]
    assert runtime.materials[material["id"]].metadata["identity_history"][0]["previous"] == "parent-shared"
    assert flow.task_status()["task"]["assignments"][aid]["executor_session_id"] == "worker-1"
    assert runtime.assignment_rebind([aid], "parent-shared", "worker-1", evidence(), "Native launch identifies the child")["status"] == "corrected"


def test_identity_repair_failure_is_resumable_and_never_silently_complete(memory, monkeypatch):
    runtime, _ = memory
    aid = register(runtime, session="parent")
    stored = runtime.result_store(aid, "parent", ["Routing", "Storage"])
    save = runtime._save
    def fail_second(material):
        if material.id == stored["materials"][1]["id"]:
            raise OSError("fixture storage failure")
        save(material)
    monkeypatch.setattr(runtime, "_save", fail_second)
    first = runtime.assignment_rebind([aid], "parent", "worker-1", evidence(), "Native metadata proves mismatch")
    assert first["status"] == "partial"
    assert any("identity" in m["field"] for m in TaskLedger(runtime).completion_missing())
    monkeypatch.setattr(runtime, "_save", save)
    assert runtime.assignment_rebind([aid], "parent", "worker-1", evidence(), "Native metadata proves mismatch")["status"] == "corrected"
    assert all(m.metadata["executor_session_id"] == "worker-1" for m in runtime.materials.values())


def test_environment_variable_is_not_identity_evidence(memory):
    runtime, _ = memory
    aid = register(runtime)
    with pytest.raises(ValueError, match="shell environment"):
        AgentWorkflow(runtime).assignment_bind(aid, "worker-1", {**evidence(), "source": "CODEX_SESSION_ID"})


def test_current_set_verifies_actual_written_fields(memory, monkeypatch):
    runtime, _ = memory
    write = runtime._write
    def corrupt(path, content):
        write(path, content)
        if path.name == "current.md":
            path.write_text("bad current")
    monkeypatch.setattr(runtime, "_write", corrupt)
    with pytest.raises(PCWError, match="read-back"):
        runtime.current_set(step="Completed", blocker="")

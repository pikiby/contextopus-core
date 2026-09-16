"""Test setup uses the same explicit registration and delivery protocol as MCP."""
from pcw_runtime.agent_workflow import AgentWorkflow


def open_task(runtime, checkpoint_policy="required"):
    flow = AgentWorkflow(runtime)
    flow.task_begin("Test request", "Temporary test memory", "Verified result",
                    checkpoint_policy, "User explicitly forbids a checkpoint" if checkpoint_policy == "forbidden" else "Test authorizes temporary checkpoint")
    checked = flow.environment_check({"environment": "test", "version": "1", "models": [{"id": "worker"}], "native": {}})
    flow.tools_map_publish(checked["environment_revision"], [{"id": "test-worker", "model": "worker", "reasoning": {},
                          "roles": ["test"], "suitable_when": ["bounded fixture"]}])
    return flow


def register(runtime, session="worker-1", *, goal="Observe state", continuation_of=None, purpose="work"):
    flow = AgentWorkflow(runtime)
    if flow.task_status()["status"] == "absent":
        open_task(runtime)
    assignment = {"goal": goal, "expected_result": "Return actual observations", "boundaries": "Temporary memory",
                  "context": {"summary": goal}, "constraints": [],
                  "acceptance_criteria": ["Facts are observed"], "knowledge_to_return": "Facts and blockers",
                  "profile": "test-worker", "selection_reason": "Bounded test", "purpose": purpose}
    context = {"assignment": assignment}
    if continuation_of:
        context["continuation_of"] = continuation_of
    ready = flow.action_requirements("prepare_assignment", context)
    assert ready["ready"], ready
    ident = ready["handoff"]["assignment_id"]
    flow.assignment_bind(ident, session)
    return ident


def process(runtime, assignment_id, saved, *, status="accepted", resolves=None):
    runtime.read(saved["id"], assignment_id=assignment_id)
    assessment = {"status": status, "reason": "Observed fixture facts"}
    if resolves:
        assessment["resolves"] = resolves
    result = AgentWorkflow(runtime).action_requirements("process_result", {
        "result": {"assignment_id": assignment_id, "material_name": saved["id"], "executor_session_id": saved["executor_session_id"]},
        "assessment": assessment})
    assert result["ready"], result
    return result


def finish(runtime):
    return AgentWorkflow(runtime).action_requirements("finish", {"acceptance_checks": {
        "status": "none_assigned", "scope": "Test request", "reason": "No separate factual check assigned"}})

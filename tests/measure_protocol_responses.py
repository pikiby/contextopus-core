"""Compare response bodies with an in-memory control-plane fixture.

Runs historical workflow/ledger Python from a Git revision and current code.
Only persistence, locking, durable-state observations, IDs and clocks are stubbed.
No workspace, database, embedding model, native worker or MCP transport is used.
The counted bytes are canonical UTF-8 JSON result bodies, not wire traffic or
latency. Rules-path strings are equalized to avoid checkout-path noise.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import types
from unittest.mock import patch
import uuid


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = "plugins/persistent-context-workspace"
FIXED_TIME = "2026-09-16T00:00:00Z"


def read_source(relative: str, revision: str | None) -> str:
    if revision is None:
        return (ROOT / relative).read_text(encoding="utf-8")
    return subprocess.run(
        ["git", "show", f"{revision}:{relative}"], cwd=ROOT, check=True,
        capture_output=True, text=True, encoding="utf-8", timeout=10,
    ).stdout


def load_workflow(label: str, revision: str | None):
    # A private package prevents importing runtime/LanceDB through normal imports.
    package_name = "_pcw_measure_" + label
    package = types.ModuleType(package_name)
    package.__path__ = []
    sys.modules[package_name] = package
    control = types.ModuleType(package_name + ".control")
    control.RecoveryRequired = type("RecoveryRequired", (Exception,), {})
    sys.modules[control.__name__] = control
    hashes = {}
    modules = {}
    for name in ("assignments", "agent_workflow"):
        relative = f"{PLUGIN}/pcw_runtime/{name}.py"
        source = read_source(relative, revision)
        hashes[relative] = hashlib.sha256(source.encode("utf-8")).hexdigest()
        module = types.ModuleType(package_name + "." + name)
        module.__file__ = "/fixture/plugin/pcw_runtime/" + name + ".py"
        module.__package__ = package_name
        sys.modules[module.__name__] = module
        exec(compile(source, module.__file__, "exec"), module.__dict__)
        modules[name] = module
    rules_path = f"{PLUGIN}/skills/pcw/references/action-requirements.md"
    rules = read_source(rules_path, revision)
    hashes[rules_path] = hashlib.sha256(rules.encode("utf-8")).hexdigest()

    def requirements(action):
        match = re.search(r"^## " + re.escape(action) + r"\n(.*?)(?=^## |\Z)", rules,
                          re.MULTILINE | re.DOTALL)
        assert match, action
        return match.group(1).strip()

    flow_type = modules["agent_workflow"].AgentWorkflow
    flow_type._requirements = staticmethod(requirements)
    flow_type._requirements_paths = staticmethod(lambda action: (
        "/fixture/plugin/skills/pcw/references/action-requirements.md#" + action,
        "/fixture/plugin/skills/pcw/references",
    ))
    modules["agent_workflow"]._now = lambda: FIXED_TIME
    modules["assignments"].now = lambda: FIXED_TIME
    return flow_type, hashes


class RuntimeFixture:
    def __init__(self):
        self.root = Path("/fixture/memory")
        self.state = Path("/fixture/runtime")
        self.control = types.SimpleNamespace(root=Path("/fixture/control"), guard=nullcontext)
        self.materials = {}

    def _guard(self):
        return nullcontext()

    def _allocate_material_id(self):
        return "b" * 32 + ".md"

    def durable_state(self):
        return {"files": {}, "paths": {key: value.path for key, value in self.materials.items()},
                "pending": [], "unregistered": []}

    def current_get(self):
        return {"goal": "Inspect the fixture", "constraints": "Read only",
                "completion": "Observation assessed", "step": "Complete", "blocker": ""}


def fixture(flow_type):
    runtime = RuntimeFixture()
    flow = flow_type(runtime)
    state = {"workflow": {"schema_version": 1, "environment": None, "tools_map": None},
             "ledger": {"active": None, "tasks": {}}}
    flow._load = lambda **kwargs: deepcopy(state["workflow"])

    def store_workflow(value):
        persisted = deepcopy(value)
        body = {key: item for key, item in persisted.items() if key != "state_revision"}
        persisted["state_revision"] = "sha256:" + hashlib.sha256(json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")).hexdigest()
        state["workflow"] = persisted
        return deepcopy(persisted)

    flow._store = store_workflow
    flow.ledger.load = lambda: deepcopy(state["ledger"])
    flow.ledger.store = lambda value: state.update(ledger=deepcopy(value))
    flow.task_begin("Inspect the fixture", "Read only", "Observation assessed")
    checked = flow.environment_check({
        "environment": "fixture-host", "version": "1.0",
        "native": {"launch": {"supports_clean_context": True}},
        "models": [{"id": "fixture-worker", "reasoning": {"effort": ["low", "high"]}}],
    })
    flow.tools_map_publish(checked["environment_revision"], [{
        "id": "bounded-research", "model": "fixture-worker", "reasoning": {"effort": "low"},
        "roles": ["research"], "suitable_when": ["A complete bounded task is supplied"],
    }])
    return flow


def run_case(flow_type, compact: bool):
    assignment = {
        "goal": "Inspect the authorized fixture",
        "expected_result": "Return the observed fixture value",
        "boundaries": "Read only fixture.txt",
        "context": {"summary": "The fixture contains the value to inspect; no changes are needed."},
        "constraints": ["Read only"], "acceptance_criteria": ["Report the observed value"],
        "knowledge_to_return": "Actual value, method, conditions and uncertainty",
        "profile": "bounded-research", "selection_reason": "A sufficient profile for this bounded observation",
        "purpose": "work",
    }
    # Fixed values make both the logical state and response byte counts repeatable.
    fixed_ids = iter([uuid.UUID(int=1), uuid.UUID(int=2)])
    with patch("uuid.uuid4", side_effect=lambda: next(fixed_ids)):
        flow = fixture(flow_type)
        prepared = (flow.assignment_prepare(deepcopy(assignment)) if compact else
                    flow.action_requirements("prepare_assignment", {"assignment": deepcopy(assignment)}))
    assert prepared["ready"], prepared
    handoff = prepared["handoff"]
    aid = handoff["assignment_id"]
    executor = "fixture-worker-session"
    flow.assignment_bind(aid, executor)
    material = types.SimpleNamespace(
        id=handoff["return_id"], revision="fixture-body-revision",
        path="knowledge/" + handoff["return_id"], content="Observed value: 42.\n",
        metadata={"saved_at": FIXED_TIME, "executor_session_id": executor},
    )
    flow.runtime.materials[material.id] = material
    # Seed the same saved/read observation through the real ledger methods.
    # Persistence/content APIs are outside this control-response measurement.
    flow.note_saved(aid, material)
    flow.note_read(aid, material)
    assessment = {"status": "accepted", "reason": "The saved observation satisfies the bounded task"}
    assessed = (flow.result_assess(aid, assessment) if compact else
                flow.action_requirements("process_result", {
                    "result": {"assignment_id": aid, "material_name": material.id,
                               "executor_session_id": executor}, "assessment": assessment}))
    checks = {"status": "none_due", "reason": "No planned check or discrepancy is due"}
    transitioned = (flow.transition(checks) if compact else
                    flow.action_requirements("transition", {"checks_due": checks}))
    acceptance = {"status": "none_assigned", "scope": "Whole fixture request",
                  "reason": "This bounded fixture has no separately assigned factual check"}
    finished = (flow.finish(acceptance) if compact else
                flow.action_requirements("finish", {"acceptance_checks": acceptance}))
    responses = dict(prepare_assignment=prepared, process_result=assessed,
                     transition=transitioned, finish=finished)
    assert all(response["ready"] for response in responses.values()), responses
    assert flow.task_status()["task"]["status"] == "complete"
    return responses


def byte_count(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="v0.7.0")
    args = parser.parse_args()
    previous, previous_hashes = load_workflow("baseline", args.baseline)
    current, current_hashes = load_workflow("current", None)
    cases = {"baseline": run_case(previous, False),
             "current_compatibility": run_case(current, False),
             "current_compact": run_case(current, True)}
    for label in ("baseline", "current_compatibility"):
        assert (cases[label]["prepare_assignment"]["handoff"]["launch_message"] ==
                cases["current_compact"]["prepare_assignment"]["handoff"]["launch_message"])
    rows = []
    for operation in cases["baseline"]:
        counts = {label: byte_count(responses[operation]) for label, responses in cases.items()}
        rows.append({"operation": operation, **counts,
                     "baseline_reduction_percent": round(100 * (1 - counts["current_compact"] / counts["baseline"]), 2)})
    totals = {label: sum(byte_count(response) for response in responses.values()) for label, responses in cases.items()}
    print(json.dumps({
        "method": "Actual historical/current workflow and ledger code; equivalent successful four-operation sequence; in-memory persistence and durable-state fixture",
        "baseline": args.baseline,
        "serialization": "JSON ensure_ascii=False, sort_keys=True, separators=(',', ':'); counted UTF-8 result-body bytes; equalized rules paths",
        "counts_exclude": ["requests", "MCP envelopes", "setup", "bind", "save/read body APIs", "rules_get fetched separately"],
        "operation_counts": {label: len(responses) for label, responses in cases.items()},
        "all_ready": True, "all_tasks_complete": True, "same_launch_message": True,
        "response_bytes": rows, "total_response_bytes": totals,
        "total_baseline_reduction_percent": round(100 * (1 - totals["current_compact"] / totals["baseline"]), 2),
        "source_sha256": {"baseline": previous_hashes, "current": current_hashes},
        "limitations": "No workspace/database/embedding/native-worker/MCP execution; no timing or model-token measurement; one small fixture, not an end-to-end benchmark",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

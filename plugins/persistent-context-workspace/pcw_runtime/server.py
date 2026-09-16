"""Import-safe local stdio MCP server. Workspaces and models are created on demand."""
from __future__ import annotations

import atexit
import inspect
from pathlib import Path
import threading
from typing import get_type_hints

from mcp.server.fastmcp import FastMCP

from .agent_workflow import (ActionContext, ActionName, AgentWorkflow, EnvironmentSnapshot,
                             ToolsMapProfile, PlannedCheck, AssignmentContext, SplitSource,
                             ResultAssessment, ChecksDue, AcceptanceChecks)
from .assignments import CheckpointPolicy
from .runtime import PCWRuntime
from .control import RecoveryRequired

mcp = FastMCP("persistent-context-workspace", instructions=(
    "PCW is the primary agent's working memory. Only the primary may call these tools. "
    "Workers receive a standalone assignment with facts as text, no memory coordinates, "
    "and return findings to the primary. Workers must not use PCW or access .pcw through "
    "filesystem tools or shell. The primary saves substantive returns, updates Current, "
    "applies compaction, links and authorized checkpoints. Semantic helpers return only "
    "end positions; the primary calls pcw_submit_boundaries. Service results are control "
    "state, never knowledge. These are assignment restrictions, not filesystem isolation. "
    "No tool grants authority to execute the user task or expand its scope."))
_runtimes: dict[tuple[str, str], PCWRuntime] = {}
_cache_lock = threading.Lock()


def runtime(work_root: str, workspace: str) -> PCWRuntime:
    key = (str(Path(work_root).resolve()), workspace)
    with _cache_lock:
        if key not in _runtimes:
            _runtimes[key] = PCWRuntime(work_root, workspace, initialize=False)
        return _runtimes[key]


def workflow(work_root: str, workspace: str) -> AgentWorkflow:
    """Return workflow state explicitly bound to the selected PCW workspace."""
    return AgentWorkflow(runtime(work_root, workspace))


def close_runtimes():
    for instance in _runtimes.values():
        instance.close()


atexit.register(close_runtimes)

_DESCRIPTIONS = {
    "startup": "Read task, Current, memory counts and tools-map freshness in one compact response. Use task_status or map getters only when full recovery details are needed.",
    "rules_get": "Read workflow rules on demand at startup or context recovery. Read-only: never registers, assesses or completes work.",
    "assignment_prepare": "Validate and register a complete standalone assignment. Return only its ID and handoff. Optional check_id binds a planned check; split sources stay primary-only. Launch only when ready.",
    "result_assess": "Record primary assessment after every saved topic block has been read. Resolving a discrepancy requires actual correction of affected knowledge. It never dispatches agents or gives semantic acceptance.",
    "transition": "Verify declared planned or mismatch-triggered checks before changing stage. Return only status and concrete missing prerequisites.",
    "finish": "Verify registered work, accepted checks, corrected knowledge, Current, preparation and authorized checkpoint. Return completion or actionable blockers; primary still judges meaning.",
    "save_result_blocks": "Save a primary-partitioned substantive return as separate coherent topic files with generated IDs, UTC time and executor. No monolithic duplicate. Exact retry is idempotent; conflicting same-count correction needs prior revisions.",
    "read_many": "Read selected complete topic materials and links in one call. With assignment_id, record that its saved blocks were read before assessment.",
    "links_many": "Apply a batch of explicit outgoing-link changes. Links do not correct claims or require new embeddings.",
    "prepare_many": "Read selected saved topic bodies and revisions for subsequent within-topic semantic boundary selection.",
    "submit_boundaries_many": "Apply a semantic helper's separate end arrays for numbered texts. Validate original revisions and literal coverage; record service state only.",
    "service_error": "Primary records an actual semantic-helper failure in control state, without creating knowledge. A successful corrected continuation is needed before finish.",
    "status": "Open selected workspace; report counts, pending preparation and active embedding/search configuration without loading model weights.",
    "list": "List bounded knowledge metadata; does not return material bodies.",
    "read": "Read the complete original material and exact navigation links by its filename-ID.",
    "create": "Create a material from supplied Markdown. MCP generates its unique ID and filename; do not provide a name. Then prepare and submit original semantic parts.",
    "adopt": "Explicitly add navigation metadata to an existing knowledge Markdown file while preserving its body and other metadata; the filename remains its ID.",
    "update": "Save a supplied final body under the same ID; invalidate stale vectors and return pending preparation. Optional revision prevents overwriting a newer body.",
    "rename": "Move a material inside knowledge/ while preserving its generated filename-ID. Update search paths without re-embedding unchanged text. A different basename is rejected.",
    "delete": "Delete exact material after removing incoming navigation IDs. Reports partial applied changes on failure.",
    "links": "Add/remove exact outgoing IDs, deduplicate and avoid self-links. No semantic editing or embedding calls.",
    "reassign": "Rewrite incoming links using explicit old-ID to surviving-ID mapping; does not delete materials or change bodies.",
    "merge": "Apply supplied final target bodies and explicit replacements, union outgoing links unless supplied, rewrite all incoming IDs before deleting old materials. Targets must already exist. Reports partial failure.",
    "prepare": 'Primary obtains source text and revision. Prepare a semantic_split assignment; pass only its launch_message, never this memory-coordinate response, to the helper.',
    "submit_boundaries": "Primary submits the semantic helper end positions. Validate order, full coverage and revision; reconstruct exact source parts, index them and record only service state.",
    "submit_parts": "Accept original semantic parts for unchanged revision, validate source fidelity, embed and replace the material rows in real LanceDB.",
    "search": "Return bounded nearest material IDs, paths and distances; apply d_max then first median-gap jump before ID deduplication. Pending count is visible; empty results are not proof of absent knowledge.",
    "reconcile": "Reconcile LanceDB with current saved knowledge after external edits/restoration; remove stale rows and queue changed bodies for native semantic preparation. Does not inspect project sources.",
    "switch_embeddings": "Explicitly switch embedding config. Requires separate search settings; lock search/writes, reembed stored original parts into inactive table, atomically activate provider+table, then remove old table. Failure retains old active index.",
    "current_get": "Load compact task focus and current step into the main agent's context, or report existing legacy Current verbatim.",
    "current_set": 'Primary updates Current. With an active task, goal/constraints/completion come from its registered request; pass step and blocker (empty string means no blocker). Use task_update for authorized changes to the request. No worker is needed.',
    "checkpoint": "Explicit local Git checkpoint of exact current.md/knowledge Markdown paths. Initialize separate memory Git if needed. No source-project commits, broad staging, hooks or remote push.",
    "restore": "Explicitly restore selected exact memory paths from local Git commit, invalidate changed search rows and report pending original semantic preparation. This can replace current contents.",
    "migrate_legacy_ids": "Explicitly migrate legacy YAML UUID identities and links to filename IDs without rewriting material bodies or vectors. Opening a workspace never performs this migration.",
    "recover_workspace": 'Primary explicitly recreates missing runtime directories. Missing knowledge remains blocked unless its recreation is explicitly authorized; this does not restore lost knowledge.',
    "task_begin": "Primary records the user request before native work. Capture its baseline and checkpoint authority independently of the workspace index; preserve an unfinished request on retry.",
    "task_update": "Primary explicitly corrects the active request with request_revision and a reason based on user authority; preserves all outstanding assignments. Then synchronize Current.",
    "task_checks_set": "Primary records intermediate/final checks with timing, scope, observable criteria and optional check assignment IDs. State the reason when revising the plan. Finish requires accepted results for planned checks.",
    "task_status": "Read the active request and every registered assignment, executor, reserved return ID, save/read/assessment state and outstanding discrepancy.",
    "assignment_bind": 'Primary binds the actual executor after sending only handoff.launch_message in a separate context. This records delivery; the worker does not call PCW. Detects an environment change after preparation.',
    "assignment_cancel": "Cancel an unlaunched prepared assignment with an explicit reason. A launched worker must return its findings or blocker and cannot be silently discarded.",
    "environment_get": "Read the selected workspace environment snapshot and whether its model map is absent, current, or refresh_required.",
    "environment_check": "Record an actual portable environment snapshot and derive canonical environment_revision from version, launchable models, reasoning capabilities and native launch constraints. A changed revision requires a map refresh.",
    "tools_map_get": "Read profiles published by the primary agent and their binding to the current environment revision. This tool never chooses a model.",
    "tools_map_publish": "Publish exact model/reasoning profiles, roles and suitable_when only for the supplied current environment revision. Rejects stale revisions and unavailable model/reasoning combinations.",
}


def _register(method_name: str, description: str):
    """Publish the programmatic method signature with explicit workspace routing."""
    method = getattr(PCWRuntime, method_name)
    annotations = get_type_hints(method)
    parameters = [inspect.Parameter("work_root", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str),
                  inspect.Parameter("workspace", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str)]
    for parameter in inspect.signature(method).parameters.values():
        if parameter.name != "self":
            parameters.append(parameter.replace(annotation=annotations.get(parameter.name, parameter.annotation)))

    def tool(work_root: str, workspace: str, **kwargs):
        try:
            return getattr(runtime(work_root, workspace), method_name)(**kwargs)
        except RecoveryRequired as exc:
            return exc.details

    tool.__name__ = "pcw_" + method_name
    tool.__doc__ = description
    tool.__signature__ = inspect.Signature(parameters, return_annotation=dict)
    tool.__annotations__ = {p.name: p.annotation for p in parameters if p.annotation is not inspect.Parameter.empty}
    tool.__annotations__["return"] = dict
    mcp.tool(name=tool.__name__, description=description)(tool)


for _method, _description in _DESCRIPTIONS.items():
    if hasattr(PCWRuntime, _method):
        _register(_method, _description)


def pcw_environment_get(work_root: str, workspace: str) -> dict:
    """Read the selected workspace's last checked environment and map freshness."""
    return workflow(work_root, workspace).environment_get()


def pcw_environment_check(work_root: str, workspace: str,
                          environment_snapshot: EnvironmentSnapshot) -> dict:
    """Store an actual environment snapshot and report whether a map refresh is required."""
    return workflow(work_root, workspace).environment_check(environment_snapshot)


def pcw_tools_map_get(work_root: str, workspace: str) -> dict:
    """Read the current model/reasoning launch map and its environment binding."""
    return workflow(work_root, workspace).tools_map_get()


def pcw_tools_map_publish(work_root: str, workspace: str, expected_environment_revision: str,
                          profiles: list[ToolsMapProfile]) -> dict:
    """Publish primary-agent profiles only if their expected environment is still current."""
    return workflow(work_root, workspace).tools_map_publish(expected_environment_revision, profiles)


def pcw_action_requirements(work_root: str, workspace: str, action: ActionName,
                            context: ActionContext | None = None) -> dict:
    """Return action-specific rules and observable missing prerequisites without dispatching work."""
    return workflow(work_root, workspace).action_requirements(action, context)


def pcw_startup(work_root: str, workspace: str) -> dict:
    return workflow(work_root, workspace).startup()


def pcw_rules_get(work_root: str, workspace: str, action: ActionName | None = None) -> dict:
    return workflow(work_root, workspace).rules_get(action)


def pcw_assignment_prepare(work_root: str, workspace: str, assignment: AssignmentContext,
                           continuation_of: str | None = None, check_id: str | None = None,
                           split_source: SplitSource | None = None,
                           split_sources: list[SplitSource] | None = None) -> dict:
    return workflow(work_root, workspace).assignment_prepare(
        assignment, continuation_of=continuation_of, check_id=check_id,
        split_source=split_source, split_sources=split_sources)


def pcw_result_assess(work_root: str, workspace: str, assignment_id: str,
                       assessment: ResultAssessment) -> dict:
    return workflow(work_root, workspace).result_assess(assignment_id, assessment)


def pcw_transition(work_root: str, workspace: str, checks_due: ChecksDue,
                    mismatch_needs_attention: bool = False, planned_checks_due: bool = False) -> dict:
    return workflow(work_root, workspace).transition(checks_due,
        mismatch_needs_attention=mismatch_needs_attention, planned_checks_due=planned_checks_due)


def pcw_finish(work_root: str, workspace: str, acceptance_checks: AcceptanceChecks,
                mismatch_needs_attention: bool = False, planned_checks_due: bool = False) -> dict:
    return workflow(work_root, workspace).finish(acceptance_checks,
        mismatch_needs_attention=mismatch_needs_attention, planned_checks_due=planned_checks_due)


def _task_receipt(result: dict) -> dict:
    """Mutations acknowledge state; explicit reads recover the full ledger."""
    task = result.get("task")
    if not isinstance(task, dict):
        return result
    return {"task_id": task["id"], "status": task["status"],
            "request_revision": result.get("request_revision")}


def pcw_task_begin(work_root: str, workspace: str, goal: str, constraints: str, completion: str,
                   checkpoint_policy: CheckpointPolicy = "not_authorized", checkpoint_reason: str = "") -> dict:
    return _task_receipt(workflow(work_root, workspace).task_begin(goal, constraints, completion, checkpoint_policy, checkpoint_reason))


def pcw_task_update(work_root: str, workspace: str, expected_request_revision: str, reason: str,
                    goal: str | None = None, constraints: str | None = None,
                    completion: str | None = None, checkpoint_policy: CheckpointPolicy | None = None,
                    checkpoint_reason: str | None = None) -> dict:
    return _task_receipt(workflow(work_root, workspace).task_update(expected_request_revision, reason, goal, constraints,
                                                       completion, checkpoint_policy, checkpoint_reason))


def pcw_task_checks_set(work_root: str, workspace: str, checks: list[PlannedCheck], reason: str) -> dict:
    return _task_receipt(workflow(work_root, workspace).task_checks_set(checks, reason))


def pcw_task_status(work_root: str, workspace: str) -> dict:
    return workflow(work_root, workspace).task_status()


def pcw_service_error(work_root: str, workspace: str, assignment_id: str, executor_session_id: str, error: str) -> dict:
    return workflow(work_root, workspace).service_error(assignment_id, executor_session_id, error)


def pcw_assignment_bind(work_root: str, workspace: str, assignment_id: str, executor_session_id: str) -> dict:
    return workflow(work_root, workspace).assignment_bind(assignment_id, executor_session_id)


def pcw_assignment_cancel(work_root: str, workspace: str, assignment_id: str, reason: str) -> dict:
    return workflow(work_root, workspace).assignment_cancel(assignment_id, reason)


for _tool_name in ("pcw_environment_get", "pcw_environment_check", "pcw_tools_map_get",
                   "pcw_tools_map_publish", "pcw_startup", "pcw_rules_get", "pcw_assignment_prepare",
                   "pcw_result_assess", "pcw_transition", "pcw_finish", "pcw_task_begin", "pcw_task_status",
                   "pcw_assignment_bind", "pcw_assignment_cancel", "pcw_task_update", "pcw_task_checks_set", "pcw_service_error"):
    mcp.tool(name=_tool_name, description=_DESCRIPTIONS[_tool_name.removeprefix("pcw_")])(globals()[_tool_name])

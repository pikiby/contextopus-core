"""Import-safe local stdio MCP server. Workspaces and models are created on demand."""
from __future__ import annotations

import atexit
import inspect
from pathlib import Path
import threading
from typing import get_type_hints

from mcp.server.fastmcp import FastMCP

from .agent_workflow import (ActionContext, ActionName, AgentWorkflow, EnvironmentSnapshot,
                             ToolsMapProfile)
from .runtime import PCWRuntime

mcp = FastMCP("persistent-context-workspace", instructions=(
    "Operate only on an explicitly selected work_root and .pcw workspace. "
    "Create/update saves return pending preparation. Pass pcw_prepare content to a native "
    "semantic-preparation subagent for original semantic parts, then pcw_submit_parts with the same revision. "
    "Semantic knowledge decisions belong to the main agent; assigned subagents apply Current, knowledge and Git changes. "
    "No tool authorizes running the user task or reading source-project files."))
_runtimes: dict[tuple[str, str], PCWRuntime] = {}
_cache_lock = threading.Lock()


def runtime(work_root: str, workspace: str) -> PCWRuntime:
    key = (str(Path(work_root).resolve()), workspace)
    with _cache_lock:
        if key not in _runtimes:
            _runtimes[key] = PCWRuntime(work_root, workspace)
        return _runtimes[key]


def workflow(work_root: str, workspace: str) -> AgentWorkflow:
    """Return workflow state explicitly bound to the selected PCW workspace."""
    return AgentWorkflow(runtime(work_root, workspace))


def close_runtimes():
    for instance in _runtimes.values():
        instance.close()


atexit.register(close_runtimes)

_DESCRIPTIONS = {
    "status": "Open selected workspace; report counts, pending preparation and active embedding/search configuration without loading model weights.",
    "list": "List bounded knowledge metadata; does not return material bodies.",
    "read": "Read the complete original material and exact navigation links by its filename-ID.",
    "create": "Save supplied Markdown as a new material; path is relative to knowledge/. Then prepare and submit original semantic parts.",
    "adopt": "Explicitly add navigation metadata to an existing knowledge Markdown file while preserving its body and other metadata; the filename remains its ID.",
    "update": "Save a supplied final body under the same ID; invalidate stale vectors and return pending preparation. Optional revision prevents overwriting a newer body.",
    "rename": "Move a material inside knowledge/ and update search paths without re-embedding its unchanged body. Change the filename-ID and exact incoming links only when the basename changes; a move with the same basename preserves ID and links.",
    "delete": "Delete exact material after removing incoming navigation IDs. Reports partial applied changes on failure.",
    "links": "Add/remove exact outgoing IDs, deduplicate and avoid self-links. No semantic editing or embedding calls.",
    "reassign": "Rewrite incoming links using explicit old-ID to surviving-ID mapping; does not delete materials or change bodies.",
    "merge": "Apply supplied final target bodies and explicit replacements, union outgoing links unless supplied, rewrite all incoming IDs before deleting old materials. Targets must already exist. Reports partial failure.",
    "prepare": "Return complete original body and revision for a native semantic-preparation subagent. This tool does not split or summarize text.",
    "submit_parts": "Accept original semantic parts for unchanged revision, validate source fidelity, embed and replace the material rows in real LanceDB.",
    "search": "Return bounded nearest material IDs, paths and distances; apply d_max then first median-gap jump before ID deduplication. Pending count is visible; empty results are not proof of absent knowledge.",
    "reconcile": "Reconcile LanceDB with current saved knowledge after external edits/restoration; remove stale rows and queue changed bodies for native semantic preparation. Does not inspect project sources.",
    "switch_embeddings": "Explicitly switch embedding config. Requires separate search settings; lock search/writes, reembed stored original parts into inactive table, atomically activate provider+table, then remove old table. Failure retains old active index.",
    "current_get": "Load compact task focus and current step into the main agent's context, or report existing legacy Current verbatim.",
    "current_set": "Save supplied goal, constraints, completion criterion, step and blocker. Omitted fields stay unchanged; replacing legacy Current requires explicit replace_legacy and full focus fields.",
    "checkpoint": "Explicit local Git checkpoint of exact current.md/knowledge Markdown paths. Initialize separate memory Git if needed. No source-project commits, broad staging, hooks or remote push.",
    "restore": "Explicitly restore selected exact memory paths from local Git commit, invalidate changed search rows and report pending original semantic preparation. This can replace current contents.",
    "migrate_legacy_ids": "Explicitly migrate legacy YAML UUID identities and links to filename IDs without rewriting material bodies or vectors. Opening a workspace never performs this migration.",
    "save_subagent_result": "Persist the raw Markdown returned by a completed subagent with its actual executor session ID. An exact retry is idempotent; a distinct later raw return may replace the same saved raw-result material only with its expected_previous_revision and the same executor. The primary agent initiates this save before reading and making content decisions; the tool does not launch or assess the subagent.",
    "environment_get": "Read the selected workspace environment snapshot and whether its model map is absent, current, or refresh_required.",
    "environment_check": "Record an actual portable environment snapshot and derive canonical environment_revision from version, launchable models, reasoning capabilities and native launch constraints. A changed revision requires a map refresh.",
    "tools_map_get": "Read profiles published by the primary agent and their binding to the current environment revision. This tool never chooses a model.",
    "tools_map_publish": "Publish exact model/reasoning profiles, roles and suitable_when only for the supplied current environment revision. Rejects stale revisions and unavailable model/reasoning combinations.",
    "action_requirements": (
        "Return the packaged instructions for prepare_assignment, process_result, transition or finish "
        "with verified prerequisites and concrete missing data. Instructions remain available when "
        "ready is false; this does not confirm native launch readiness. For prepare_assignment, "
        "resolve missing prerequisites and resubmit the complete assignment until ready is true "
        "before launching. Creating or saving prerequisite data remains available. "
        "It never dispatches agents or gives semantic acceptance."
    ),
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
        return getattr(runtime(work_root, workspace), method_name)(**kwargs)

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


for _tool_name in ("pcw_environment_get", "pcw_environment_check", "pcw_tools_map_get",
                   "pcw_tools_map_publish", "pcw_action_requirements"):
    mcp.tool(name=_tool_name, description=_DESCRIPTIONS[_tool_name.removeprefix("pcw_")])(globals()[_tool_name])

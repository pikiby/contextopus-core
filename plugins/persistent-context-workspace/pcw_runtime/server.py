"""Import-safe local stdio MCP server. Workspaces and models are created on demand."""
from __future__ import annotations

import atexit
import inspect
from pathlib import Path
import threading
from typing import get_type_hints

from mcp.server.fastmcp import FastMCP

from .runtime import PCWRuntime

mcp = FastMCP("persistent-context-workspace", instructions=(
    "Operate only on an explicitly selected work_root and .pcw workspace. "
    "Create/update saves return pending preparation. Pass pcw_prepare content to a native "
    "Codex subagent for original semantic parts, then pcw_submit_parts with the same revision. "
    "Current and all semantic knowledge decisions belong to the main agent. "
    "No tool authorizes running the user task or reading source-project files."))
_runtimes: dict[tuple[str, str], PCWRuntime] = {}
_cache_lock = threading.Lock()


def runtime(work_root: str, workspace: str) -> PCWRuntime:
    key = (str(Path(work_root).resolve()), workspace)
    with _cache_lock:
        if key not in _runtimes:
            _runtimes[key] = PCWRuntime(work_root, workspace)
        return _runtimes[key]


def close_runtimes():
    for instance in _runtimes.values():
        instance.close()


atexit.register(close_runtimes)

_DESCRIPTIONS = {
    "status": "Open selected workspace; report counts, pending preparation and active embedding/search configuration without loading model weights.",
    "list": "List bounded knowledge metadata; does not return material bodies.",
    "read": "Read the complete original material and exact navigation links by stable ID.",
    "create": "Save main-agent-written Markdown as a new UUID material; path is relative to knowledge/. Then prepare and submit original semantic parts.",
    "adopt": "Explicitly add missing id/links metadata to an existing knowledge Markdown file, preserving its body, extra metadata and any existing stable ID.",
    "update": "Save final main-agent-written body under the same ID; invalidate stale vectors and return pending preparation. Optional revision prevents overwriting a newer body.",
    "rename": "Rename a material path inside knowledge/; preserve its ID, body, links and embeddings.",
    "delete": "Delete exact material after removing incoming navigation IDs. Reports partial applied changes on failure.",
    "links": "Add/remove exact outgoing IDs, deduplicate and avoid self-links. No semantic editing or embedding calls.",
    "reassign": "Rewrite incoming links using explicit old-ID to surviving-ID mapping; does not delete materials or change bodies.",
    "merge": "Apply main-agent final target bodies and explicit replacements, union outgoing links unless supplied, rewrite all incoming IDs before deleting old materials. Targets must already exist. Reports partial failure.",
    "prepare": "Return complete original body and revision for a native Codex semantic-preparation subagent. This tool does not split or summarize text.",
    "submit_parts": "Accept original semantic parts for unchanged revision, validate source fidelity, embed and replace the material rows in real LanceDB.",
    "search": "Return bounded nearest material IDs, paths and distances; apply d_max then first median-gap jump before ID deduplication. Pending count is visible; empty results are not proof of absent knowledge.",
    "reconcile": "Reconcile LanceDB with current saved knowledge after external edits/restoration; remove stale rows and queue changed bodies for native semantic preparation. Does not inspect project sources.",
    "switch_embeddings": "Explicitly switch embedding config. Requires separate search settings; lock search/writes, reembed stored original parts into inactive table, atomically activate provider+table, then remove old table. Failure retains old active index.",
    "current_get": "Load compact task focus and current step into the main agent's context, or report existing legacy Current verbatim.",
    "current_set": "Save agent-supplied goal, constraints, completion criterion, step and blocker. Omitted fields stay unchanged; replacing legacy Current requires explicit replace_legacy and full focus fields.",
    "checkpoint": "Explicit local Git checkpoint of exact current.md/knowledge Markdown paths. Initialize separate memory Git if needed. No source-project commits, broad staging, hooks or remote push.",
    "restore": "Explicitly restore selected exact memory paths from local Git commit, invalidate changed search rows and report pending original semantic preparation. This can replace current contents.",
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
    _register(_method, _description)

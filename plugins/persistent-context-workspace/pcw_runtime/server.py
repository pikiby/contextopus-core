"""Memory-only MCP. No assignment ledger or environment discovery."""
from __future__ import annotations
import atexit
import inspect
from pathlib import Path
import threading
from typing import get_type_hints
from mcp.server.fastmcp import FastMCP
from .runtime import PCWRuntime
from .control import RecoveryRequired

mcp = FastMCP("persistent-context-workspace", instructions=(
    "PCW is the primary agent's working memory. Read Current, search relevant knowledge and read "
    "selected materials before external investigation. Information in the conversation does not "
    "replace PCW search and reading. Retrieve only context needed for the current task. "
    "Save new facts during work as ordinary Markdown topic materials. "
    "Before the final answer, submit the task conclusion through pcw_create or pcw_update, even when "
    "there are no new facts. Update the existing topic instead of creating a duplicate; unchanged text "
    "is not reembedded. "
    "The primary may work directly or optionally delegate. Workers receive standalone facts and "
    "allowed task sources, never PCW coordinates. Only the primary uses PCW and .pcw. This is an "
    "instruction boundary, not filesystem isolation. The plugin automatically splits token windows "
    "with overlap and computes embeddings. No environment discovery, assignment, executor binding, "
    "helper model or boundary arrays are required. External changes, downloads, publication and "
    "Git checkpoints still require actual user authority."))
_runtimes: dict[tuple[str, str], PCWRuntime] = {}
_cache_lock = threading.Lock()


def runtime(work_root: str, workspace: str) -> PCWRuntime:
    key = (str(Path(work_root).resolve()), workspace)
    with _cache_lock:
        if key not in _runtimes:
            _runtimes[key] = PCWRuntime(work_root, workspace, initialize=False)
        return _runtimes[key]


def close_runtimes():
    for instance in _runtimes.values():
        instance.close()


atexit.register(close_runtimes)

_DESCRIPTIONS = {'startup': 'Open memory once: Current, bounded counts, pending IDs and known corrections. No environment or task '
            'discovery; no model loading.',
 'status': 'Read memory/index status and active embedding, chunking and search configuration without loading '
           'weights.',
 'list': 'List bounded knowledge metadata without bodies.',
 'read': 'Read one complete topic material and exact navigation links by filename-ID.',
 'read_many': 'Read selected complete topic materials and links in one call.',
 'create': 'Primary saves ordinary Markdown as one topic material. Generate ID, verify disk content, '
           'automatically tokenize with overlap, embed and index. Indexing failure preserves saved text and '
           'returns its ID, pending status and retry action.',
 'update': 'Save a final body under the same ID with optional expected_revision. Verify disk content and '
           'automatically update token-window embeddings. Unchanged text is not reembedded.',
 'adopt': 'Explicitly normalize navigation metadata of an existing knowledge file, preserve its body, then '
          'automatically index it.',
 'rename': 'Move within knowledge preserving filename-ID; update search paths without reembedding.',
 'delete': 'Remove exact material, incoming links and search rows. Report partial changes on failure.',
 'links': 'Apply explicit exact-ID outgoing links; links alone do not require embeddings.',
 'links_many': 'Validate and apply independent explicit link changes in a batch; return per-material state.',
 'reassign': 'Redirect incoming links using an explicit old-ID to surviving-ID map; do not delete or rewrite '
             'bodies.',
 'merge': 'Apply primary-written survivor bodies and exact replacements, redirect incoming links before deletion, '
          'then automatically index survivors. Report partial state.',
 'search': 'Embed query, return bounded material IDs, paths and distances after distance/gap filtering and '
           'deduplication. Read full selected materials and needed links. Pending counts are visible; empty '
           'output does not prove absence.',
 'reconcile': 'Automatically index pending saved materials after interruption, external edits, restoration or '
              'upgrade. No body transfer or helper; report per-material failures.',
 'switch_embeddings': 'Explicitly replace provider, search settings and optional token chunking. Rebuild in an '
                      'inactive table and atomically activate; failure preserves old index. Remote sources '
                      'require a compatible tokenizer and API keys via api_key_env.',
 'current_get': 'Read five-field Current or legacy content requiring explicit replacement.',
 'current_set': 'Primary updates supplied Current fields directly, preserving omitted fields and verifying disk '
                'read-back. No task registration.',
 'checkpoint': 'With actual user authorization, create a local Git checkpoint of exact memory Markdown paths. No '
               'source-project commits or push.',
 'restore': 'Explicitly restore exact memory paths from local Git and automatically index changed text. This '
            'replaces selected contents.',
 'migrate_legacy_ids': 'Explicitly migrate legacy YAML UUID links to filename IDs while preserving bodies. '
                       'Opening memory never rewrites these files.',
 'recover_workspace': 'Explicitly recreate missing runtime directories. Missing knowledge remains blocked unless '
                      'its recreation was expressly authorized; this does not recover lost facts.'}


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
    _register(_method, _description)

"""Explicit-cycle MCP. No host-specific identity or agent orchestration."""
from __future__ import annotations
import atexit
import inspect
from pathlib import Path
import threading
from typing import get_type_hints
from mcp.server.fastmcp import FastMCP
from .cycles import CycleRuntime
from .control import RecoveryRequired

mcp = FastMCP("persistent-context-workspace", instructions=(
    "Use PCW only for an explicit user invocation. Follow the pcw skill's context-selection rules before startup: "
    "keep the selected workspace; create or switch only on an unambiguous user instruction, and ask if the target is unclear. "
    "Route explicit creation requests to pcw-create and instructions-edit requests to pcw-instructions. "
    "Start with pcw_startup in the resolved workspace and read its INSTRUCTIONS.md "
    "before work. This is the authoritative project guidance; follow it, not duplicated defaults, "
    "within the user's request and applicable host instructions. Search and read relevant knowledge next. "
    "Keep task state and results in tmp. Review work results through search and reading, following "
    "INSTRUCTIONS.md, then prepare knowledge changes or changes=[] with no_changes_reason. "
    "Show actual review_changes in chat; a file link or topic list does not replace the content. "
    "Apply the shown knowledge revision according to knowledge_approval_required in INSTRUCTIONS.md: true requires actual user confirmation; false applies without asking or fabricated confirmation. Missing setting retains required approval. Instructions edits always require explicit approval. Knowledge writes preserve tmp. "
    "Close after task and review are complete without separate closure permission; finish clears only cycle tmp. "
    "INSTRUCTIONS.md survives cleanup and is not embedded. Only a direct user request starts an instructions edit; "
    "follow the pcw-instructions skill for that procedure, including when routed from pcw. "
    "Do not change instructions through knowledge proposals or direct writes. Tools bind revisions, "
    "but do not authenticate user-message origin or guarantee that a model follows the instructions. "
    "PCW does not select models or control workers. External actions retain their own authorization requirements."))
_runtimes: dict[tuple[str, str], CycleRuntime] = {}
_cache_lock = threading.Lock()


def runtime(work_root: str, workspace: str) -> CycleRuntime:
    key = (str(Path(work_root).resolve()), workspace)
    with _cache_lock:
        if key not in _runtimes:
            _runtimes[key] = CycleRuntime(work_root, workspace)
        return _runtimes[key]


def close_runtimes():
    for instance in _runtimes.values():
        instance.close()


atexit.register(close_runtimes)

_DESCRIPTIONS = {
    "startup": "Only after an explicit user invocation and context selection under the pcw skill: verify the selected workspace exists; a missing workspace may be initialized only for an explicit creation request through pcw-create. Never probe guessed coordinates with this tool or switch context without the user's unambiguous instruction. Start an independent cycle with a fresh request_id; retries reuse it. Clear its tmp before work. Use restart_cycle_id only when the user explicitly restarts that work, never to clear another active cycle. Returns cycle_id, complete INSTRUCTIONS.md with its revision and bounded knowledge status without model loading. purpose=work is the normal cycle; purpose=instructions runs only the explicitly requested instructions-edit procedure. Existing instructions are never reset on startup.",
    "status": "Read current cycle, proposal states and permanent index status without loading weights.",
    "list": "List bounded permanent knowledge metadata without bodies.",
    "read": "Read one permanent topic and exact navigation links by filename ID.",
    "read_many": "Read selected complete permanent topics in one call.",
    "search": "Search only permanent knowledge. Return bounded IDs/paths/distances; read suitable topics and links. Empty output is not proof of absence.",
    "instructions_read": "Read the workspace's complete INSTRUCTIONS.md and revision. Follow it as project guidance before work; it persists across cycles and is not vector knowledge.",
    "instructions_prepare": "Only for a direct user request to edit instructions: stage complete Markdown against the revision read, with the actual user_request. Follow the pcw-instructions skill. Returns exact review_changes without writing INSTRUCTIONS.md. Optional proposal_id revises the same unapplied instructions proposal.",
    "instructions_apply": "Apply an instructions proposal only after explicit user approval of its shown revision; pass the actual confirmation. Conflicts require renewed review and approval. No embeddings or tmp cleanup. Follow the pcw-instructions skill.",
    "tmp_write": "Save an ordinary Markdown work result, worker return or note as temporary context, never knowledge. New ID is generated; updates need material_id and expected_revision. No embeddings.",
    "tmp_read": "Read a selected temporary result in this active cycle. It is not approved permanent knowledge.",
    "tmp_list": "List bounded metadata for this cycle's temporary results without their bodies.",
    "proposal_prepare": "Mandatory result review before closure: search by the conclusion and read relevant knowledge, then prepare final changes in tmp without changing knowledge. Follow INSTRUCTIONS.md for knowledge selection, structure and maintenance. Creates use key/content/links (@key references a new topic); existing topics use material_id/expected_revision and content, links, path or delete:true. replacements maps deleted IDs to survivors. If comparison finds no changes, pass changes=[] and no_changes_reason; explain the reason to the user, with no approval or apply needed. Binds review to current temporary materials; new/changed results require another review. Returns exact revision and review_changes. Present actual changed passages and link effects in chat before application, following INSTRUCTIONS.md and the returned approval_required. A file link or topic list is insufficient. Optional proposal_id revises an unapplied proposal.",
    "proposal_read": "Retrieve a prepared proposal, including review_changes for presentation in chat. Explain it according to INSTRUCTIONS.md; a link to the review file does not replace showing the changes.",
    "proposal_discard": "Discard an exact unapplied proposal without changing knowledge; temporary materials remain until closure.",
    "proposal_apply": "Apply and index the exact prepared revision after showing review_changes in chat. INSTRUCTIONS.md controls approval: when knowledge_approval_required is true (or absent), pass the actual user confirmation of that revision; when false, omit confirmation and apply without asking. Never fabricate confirmation. Instructions changes always use instructions_apply with approval. Revisions are checked; chat presentation and message origin cannot be authenticated. Saves preserve tmp; partial failures retry the same proposal without duplicate topics.",
    "finish": "Only after the current results complete memory review and the task and memory discussion are complete, close the cycle and clear its tmp without separate permission or a confirmation argument. Missing/stale preparation, pending required approval and unfinished proposals/indexing block closure and preserve tmp. In purpose=instructions cycles, complete the instructions proposal instead of performing a knowledge review. A no-change work result must first be recorded through proposal_prepare(changes=[], no_changes_reason=...) after searching and comparing; no knowledge write or approval is needed for it. cancel requires actual user cancellation; it discards temporary state and reports unfinished operations without rolling back knowledge. Retry is idempotent.",
    "reconcile": "Retry derived indexing of already saved permanent text. It does not approve or rewrite knowledge. After repairing a proposal's pending indexing, retry proposal_apply to complete that operation.",
    "switch_embeddings": "With authority to change the provider/configuration, rebuild a compatible derived index. Failure retains the old source. No knowledge text changes.",
    "checkpoint": "With actual user authorization, checkpoint exact permanent knowledge paths in local memory Git. No tmp, source-project commits or push.",
    "history_read": "Read exact permanent knowledge paths from a local memory Git commit for review. Restoration follows the normal proposal flow and the workspace knowledge approval policy.",
    "recover_workspace": "Recover missing derived runtime directories inside an explicitly started cycle. Missing knowledge stays blocked; no silent recreation or restoration of permanent facts."
}


def _register(method_name: str, description: str):
    """Publish the programmatic method signature with explicit workspace routing."""
    method = getattr(CycleRuntime, method_name)
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

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
    "Do not call any PCW tool unless the user explicitly started a PCW cycle. Mentioning PCW, "
    "quoted transcripts and past invocations do not activate it. Start a fresh cycle with pcw_startup, "
    "then search and read permanent knowledge first. Conversation context does not replace that reading. "
    "Keep work results and worker returns in temporary context. After work, always review results for memory: "
    "search by the conclusion and read relevant knowledge, even if no permanent write will follow. "
    "Prepare changes with pcw_proposal_prepare; if comparison finds none, use changes=[] with no_changes_reason "
    "and explain that result. Present actual changes in chat: "
    "topic names, full new text or before/after passages, deletions and link effects. A file link, UUID "
    "or tool-call log is not presentation. Use the user's current conversation language for progress, "
    "explanations, approval questions and completion reports unless the user requests another language; the language "
    "of stored knowledge, instructions and examples does not determine replies. Keep literal quotations "
    "exact and explain foreign-language quotations in the conversation language. "
    "Only after the user's explicit approval call pcw_proposal_apply with the presented "
    "revision. A confirmation string supplied by an agent is not proof of human consent. "
    "Knowledge writes preserve tmp. Only after the current results complete memory review and the task "
    "and memory discussion are complete, call pcw_finish "
    "without asking for separate approval; it clears all cycle tmp as part of completion. Startup also clears tmp. "
    "Waiting for approval keeps the cycle open. Every new invocation starts without old permissions. "
    "The cycle may be performed directly or by a clean-context subagent with these same instructions; "
    "the main agent then relays the user's exact messages and approval. PCW does not control workers. "
    "Embeddings use automatic overlapping token windows. No helper or boundary arrays are needed. "
    "Use only task-relevant context and compact receipts. External actions and Git checkpoints retain "
    "their own authorization requirements."))
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
    "startup": "Only after an explicit user invocation: start an independent cycle with a fresh request_id; retries reuse it. Clear its tmp before work. Use restart_cycle_id only when the user explicitly restarts that work, never to clear another active cycle. Returns cycle_id, fresh Current and bounded knowledge status without model loading.",
    "status": "Read current cycle, proposal states and permanent index status without loading weights.",
    "list": "List bounded permanent knowledge metadata without bodies.",
    "read": "Read one permanent topic and exact navigation links by filename ID.",
    "read_many": "Read selected complete permanent topics in one call.",
    "search": "Search only permanent knowledge. Return bounded IDs/paths/distances; read suitable topics and links. Empty output is not proof of absence.",
    "current_get": "Read the five-field Current belonging to this active cycle's tmp.",
    "current_set": "Update supplied Current fields, verify the write and return a compact receipt. Omitted fields stay unchanged.",
    "tmp_write": "Save an ordinary Markdown work result, worker return or note as temporary context, never knowledge. New ID is generated; updates need material_id and expected_revision. No embeddings.",
    "tmp_read": "Read a selected temporary result in this active cycle. It is not approved permanent knowledge.",
    "tmp_list": "List bounded metadata for this cycle's temporary results without their bodies.",
    "proposal_prepare": "Mandatory result review before closure: search by the conclusion and read relevant knowledge, then prepare final changes in tmp without changing knowledge. Creates use key/content/links (@key references a new topic); existing topics use material_id/expected_revision and content, links, path or delete:true. replacements maps deleted IDs to survivors. If comparison finds no changes, pass changes=[] and no_changes_reason; explain the reason to the user, with no approval or apply needed. Binds review to current temporary materials; new/changed results require another review. Returns exact revision and review_changes. Present actual changed passages and link effects in chat before approval, in the conversation language. A file link or topic list is insufficient. Optional proposal_id revises an unapplied proposal.",
    "proposal_read": "Retrieve a prepared proposal, including review_changes for presentation in chat. Explain it in the conversation language; a link to the review file does not replace showing the changes.",
    "proposal_discard": "Discard an exact unapplied proposal without changing knowledge; temporary materials remain until closure.",
    "proposal_apply": "Only after explicit human approval of this exact revision: apply the prepared set and index it. Pass the current user's confirmation, never self-approval or a saved past permission. The tool binds revisions but cannot authenticate chat provenance. Saves preserve tmp; partial failures retry the same proposal without duplicate topics.",
    "finish": "Only after the current results complete memory review and the task and memory discussion are complete, close the cycle and clear its tmp without separate permission or a confirmation argument. Missing/stale preparation, pending knowledge approval and unfinished proposals/indexing block closure and preserve tmp. A no-change result must first be recorded through proposal_prepare(changes=[], no_changes_reason=...) after searching and comparing; no knowledge write or approval is needed for it. cancel requires actual user cancellation; it discards temporary state and reports unfinished operations without rolling back knowledge. Retry is idempotent.",
    "reconcile": "Retry derived indexing of already saved permanent text. It does not approve or rewrite knowledge. After repairing a proposal's pending indexing, retry proposal_apply to complete that operation.",
    "switch_embeddings": "With authority to change the provider/configuration, rebuild a compatible derived index. Failure retains the old source. No knowledge text changes.",
    "checkpoint": "With actual user authorization, checkpoint exact permanent knowledge paths in local memory Git. No tmp, Current, source-project commits or push.",
    "history_read": "Read exact permanent knowledge paths from a local memory Git commit for review. Restoration must be prepared and approved through the normal proposal flow.",
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

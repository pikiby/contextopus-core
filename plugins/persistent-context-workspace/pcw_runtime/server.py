"""Independent reads and policy-governed work cycles over host-neutral MCP."""
from __future__ import annotations
import atexit
import inspect
from pathlib import Path
import threading
import time
from typing import get_type_hints
from mcp.server.fastmcp import FastMCP
from .cycles import CycleRuntime
from .control import RecoveryRequired
from .analytics import EventStore

mcp = FastMCP("persistent-context-workspace", instructions=(
    "Keep the context selected by the user; ask if ambiguous. Creation or switching requires clear user direction. "
    "Follow the relevant PCW skill. Read INSTRUCTIONS.md as the authoritative workspace rules, then PROJECT.md "
    "and relevant knowledge. Independent reading needs no cycle; it never creates or migrates a workspace. "
    "Work cycles follow workspace invocation and approval settings. Keep progress in task Current and results in tmp. "
    "Review results, prepare changes or a grounded no-change conclusion, show actual changed passages and links in chat, "
    "apply under the current policy, then finish. Never replace the review with a file link. "
    "Instructions changes always require the user's direct request and approval. Tools bind revisions but cannot "
    "authenticate chat origin. PCW does not control agents; external actions retain their authorization requirements."))
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
    "workspace_inspect": "Read the selected existing workspace format and compatibility, without creating or migrating it.",
    "workspace_create": "Only after an explicit creation request: create the exact context with the INSTRUCTIONS settings and PROJECT text agreed with the user through pcw-create. All four settings must be explicit. A repeated request_id with identical input resumes safely; existing contexts are not replaced.",
    "upgrade_plan": "Preflight the selected existing context, including already-current formats: return compatibility, source revision, technical changes, unfinished work with material titles and proposal states, exact blockers and project_description status. Format compatibility does not imply complete project content or finished work; present text is not a content review. No source changes. Compatible active cycles are preserved, not cancelled. A pending migration returns resume_revision and its retained backup. Use pcw-upgrade.",
    "upgrade_apply": "Apply the reviewed technical migration on explicit user request. Back up the entire workspace including tmp and separate control state; verify preservation before marking the format current. Keep compatible unfinished cycles, draft revisions and approval states unchanged. Never apply or cancel their proposals. Retry the original revision and snapshot after interruption.",
    "startup": "Open an existing compatible context with a fresh request_id; retries reuse it. Never creates or migrates. purpose is work, instructions, audit or rework. invocation=implicit is allowed only for work under allow_implicit_updates. Optional task_id explicitly resumes an existing task. Clear only this cycle's tmp (restart_cycle_id requires an explicit restart request). Returns instructions and project; read them before work.",
    "status": "Read current cycle, proposal states and permanent index status without loading weights.",
    "list": "List bounded permanent knowledge metadata without bodies.",
    "read": "Read one complete permanent topic with revision, title, description and labelled navigation links, without a cycle. Optional from_id validates a declared link traversal; linked bodies are not loaded automatically.",
    "read_many": "Read selected complete permanent topics in one call.",
    "search": "Search only permanent knowledge without a cycle. Return bounded IDs, paths, titles, descriptions and distances; read suitable topics and links. Empty output is not proof of absence. Pending or invalid entries are excluded without implicit repair.",
    "instructions_read": "Read the workspace's complete INSTRUCTIONS.md and revision. Follow it as project guidance before work; it persists across cycles and is not vector knowledge.",
    "project_read": "Read the selected context's project purpose, goals and boundaries without a cycle or vector search.",
    "project_update": "Prepare the user's requested PROJECT change against its exact revision. Returns actual changes for chat presentation; does not write PROJECT. Apply through project_apply under current policy.",
    "project_apply": "Apply the exact presented PROJECT revision under knowledge_approval_required; instructions changes always use their own approval procedure. Existing task states remain unchanged.",
    "current_create": "Create task-specific Current for actual work and bind it to this work/rework cycle. request_id makes retries idempotent. No embeddings.",
    "current_list": "List task IDs, goals, states and revisions. Select by the user's task; ask if ambiguous.",
    "current_read": "Read one task's current state without opening a work cycle. No vector lookup.",
    "current_update": "Update the bound task after a significant result, blocker, next-step or status change. Use the revision read. Current is not an action log and survives cycle closure.",
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
    "history_read": "Read exact knowledge, INSTRUCTIONS or PROJECT paths from a local memory Git commit. Restoration uses the appropriate current proposal procedure; instructions always require explicit approval. Reading a past version does not make it current.",
    "history_list": "List local versions of permanent knowledge, PROJECT and INSTRUCTIONS. History is not vector knowledge.",
    "history_diff": "Compare two local permanent-data versions, optionally selecting exact files. Does not restore them.",
    "history_retry": "Retry pending local commits using their captured exact snapshots; later filesystem edits cannot silently enter an earlier operation. No push.",
    "analytics_query": "Select observed PCW operations by workspace, cycle, task, tool and period, including other agents' cycles. No model/session identity is inferred. Returns bounded metadata and measured totals; tokens/cost stay unknown unless actually measured.",
    "analytics_read": "Read one observed operation's parameters, result, error, file version references and redaction markers. A started record has an unknown outcome, not a demonstrated failure.",
    "analytics_blob_read": "Read a selected retained sanitized body from an analytics record. Not permanent knowledge.",
    "analytics_evaluate": "Store an explicitly requested analytical assessment separately from observed events, with exact evidence IDs. It does not edit knowledge or rewrite the event journal.",
    "analytics_import": "Only on an explicit request: import one selected transcript, including another agent's session, using codex-jsonl or the host-independent pcw-session-v1 format. Preserve source record coordinates and redaction markers. No session discovery or identity/call attribution inferred from timing.",
    "audit": "Read-only structural audit with exact material/file revisions, fragments and observed grounds. Page through the entire selected workspace for an all-material request. Semantic contradictions or unsupported claims require the audit skill's evidence-based assessment; this tool does not establish them by heuristics.",
    "recover_workspace": "Recover missing derived runtime directories inside an explicitly started cycle. Missing knowledge stays blocked; no silent recreation or restoration of permanent facts."
}


def dispatch(work_root: str, workspace: str, method_name: str, kwargs: dict):
    """Automatic observation at the common MCP execution boundary."""
    instance = runtime(work_root, workspace)
    events = EventStore(instance.engine.work_root)
    with instance.control.guard():
        snapshot_error = None
        try:
            before = events.snapshot(instance)
        except Exception as exc:
            before, snapshot_error = None, exc
        cycle = instance._records()["cycles"].get(kwargs.get("cycle_id"), {})
        mode = kwargs.get("purpose", cycle.get("purpose", "read"))
        started = time.monotonic()
        operation = events.begin(workspace, method_name, kwargs, mode, cycle.get("task_id"), before)
        try:
            if snapshot_error is not None:
                raise snapshot_error
            try:
                result = getattr(instance, method_name)(**kwargs)
            except RecoveryRequired as exc:
                result = exc.details
        except Exception as exc:
            try:
                after = events.snapshot(instance) if snapshot_error is None else None
                events.end(operation, workspace, started, before or {}, after, error=str(exc))
            except Exception:
                pass  # The start remains unresolved; never invent a successful completion.
            raise
        try:
            events.end(operation, workspace, started, before, events.snapshot(instance), result=result)
            return {**result, "analytics": {"event_id": operation, "status": "recorded"}}
        except Exception:
            return {**result, "analytics": {"event_id": operation, "status": "completion_unrecorded",
                                            "reason": "Result recording failed; inspect file revisions before retrying the action"}}


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
        return dispatch(work_root, workspace, method_name, kwargs)

    tool.__name__ = "pcw_" + method_name
    tool.__doc__ = description
    tool.__signature__ = inspect.Signature(parameters, return_annotation=dict)
    tool.__annotations__ = {p.name: p.annotation for p in parameters if p.annotation is not inspect.Parameter.empty}
    tool.__annotations__["return"] = dict
    mcp.tool(name=tool.__name__, description=description)(tool)


for _method, _description in _DESCRIPTIONS.items():
    _register(_method, _description)

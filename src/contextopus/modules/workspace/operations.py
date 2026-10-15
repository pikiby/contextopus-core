"""Workspace operation metadata is the canonical interface contract."""

import inspect
from typing import get_type_hints
from pydantic import ConfigDict, create_model
from .cycles import CycleRuntime

_DESCRIPTIONS = {
    "workspace_inspect": "Read the selected existing workspace format and compatibility, without creating or migrating it.",
    "workspace_create": "Only after an explicit creation request: create the exact context with the INSTRUCTIONS settings and PROJECT text agreed with the user through pcw-create. All five settings, including create_required_sources, must be explicit for a new request. A repeated request_id with identical input resumes safely, including accepted older requests; existing contexts are not replaced.",
    "upgrade_plan": "Preflight the selected existing context, including already-current formats: return compatibility, source revision, technical changes, unfinished work with material titles and proposal states, exact blockers and project_description status. Format compatibility does not imply complete project content or finished work; present text is not a content review. No source changes. Compatible active cycles are preserved, not cancelled. A pending migration returns resume_revision and its retained backup. Use pcw-upgrade.",
    "upgrade_apply": "Apply the reviewed technical migration on direct request, or automatic=true when the skill detects format incompatibility. Preserve workspace/control snapshots; migrate cards, source declarations and shared category index together. Keep unfinished cycles and immutable proposal approvals; adapt technical paths without applying old work. Complete only after successful indexing. Retry the original revision after interruption; never fabricate a user request.",
    "startup": "Open an existing compatible context with a fresh request_id; retries reuse it. Never creates or migrates. purpose is work, instructions, audit or rework. invocation=implicit is allowed only for work under allow_implicit_updates. Optional task_id explicitly resumes an existing task. Clear only this cycle's tmp (restart_cycle_id requires an explicit restart request). Returns instructions and project; read them before work.",
    "status": "Read current cycle, proposal states and permanent index status without loading weights.",
    "list": "List bounded permanent knowledge metadata without bodies.",
    "read": "Read a complete permanent topic by YAML ID across compatible categories, without a cycle. Returns its owning workspace, descriptive path and labelled links; never changes the active context's instructions. from_id validates link traversal. On every receipt obtain each sources reference according to its instruction; this tool returns declarations and does not execute them.",
    "read_many": "Read selected whole topics by YAML ID, including other categories, without changing active rules. For every returned sources block, freshly obtain each reference according to its instruction, even on repeated reads. Returns bodies and source declarations, not fetched evidence.",
    "search": "Search permanent knowledge in the shared RAG without a cycle. Defaults to selected workspace; categories selects several, all_categories expands to all compatible contexts. Category filtering precedes nearest top-N. Return IDs, owning workspaces, descriptive paths, titles and distances. Cross-category retrieval never switches active instructions or write destination. Pending/invalid rows are excluded; empty output is not proof of absence.",
    "instructions_read": "Read the workspace's complete INSTRUCTIONS.md and revision. Follow it as project guidance before work; it persists across cycles and is not vector knowledge.",
    "project_read": "Read the selected context's project purpose, goals and boundaries without a cycle or vector search.",
    "project_update": "Prepare the user's requested PROJECT change against its exact revision. Returns actual changes for chat presentation; does not write PROJECT. Apply through project_apply under current policy.",
    "project_apply": "Apply the exact presented PROJECT revision under knowledge_approval_required; instructions changes always use their own approval procedure. Existing task states remain unchanged.",
    "current_create": "Create task-specific Current for actual work and bind it to this work/rework cycle. request_id makes retries idempotent. No embeddings.",
    "current_list": "List task IDs, goals, states and revisions. Select by the user's task; ask if ambiguous.",
    "current_read": "Read one task's current state without opening a work cycle. No vector lookup.",
    "current_update": "Update the bound task after a significant result, blocker, next-step or status change. Use the revision read. Current is not an action log and survives cycle closure.",
    "instructions_prepare": "Only for a direct user request to edit instructions: stage complete Markdown against the revision read, with the actual user_request. Follow the pcw-edit-instructions skill. Returns exact review_changes without writing INSTRUCTIONS.md. Optional proposal_id revises the same unapplied instructions proposal.",
    "instructions_apply": "Apply an instructions proposal only after explicit user approval of its shown revision; pass the actual confirmation. Conflicts require renewed review and approval. No embeddings or tmp cleanup. Follow the pcw-edit-instructions skill.",
    "tmp_write": "Save an ordinary Markdown work result, worker return or note as temporary context, never knowledge. New ID is generated; updates need material_id and expected_revision. No embeddings.",
    "tmp_read": "Read a selected temporary result in this active cycle. It is not approved permanent knowledge.",
    "tmp_list": "List bounded metadata for this cycle's temporary results without their bodies.",
    "proposal_prepare": "Mandatory result review before closure: search by the conclusion and read relevant knowledge, then prepare final changes in tmp without changing knowledge. Follow INSTRUCTIONS.md for knowledge selection, structure and maintenance. Creates use key/content/links (@key references a new topic); existing topics use material_id/expected_revision and content, links, path or delete:true. replacements maps deleted IDs to survivors. If comparison finds no changes, pass changes=[] and no_changes_reason; explain the reason to the user, with no approval or apply needed. Binds review to current temporary materials; new/changed results require another review. Returns exact revision and review_changes. Present actual changed passages and link effects in chat before application, following INSTRUCTIONS.md and the returned approval_required. A file link or topic list is insufficient. Optional proposal_id revises an unapplied proposal.",
    "proposal_read": "Retrieve a prepared proposal, including review_changes for presentation in chat. Explain it according to INSTRUCTIONS.md; a link to the review file does not replace showing the changes.",
    "proposal_discard": "Discard an exact unapplied proposal without changing knowledge; temporary materials remain until closure.",
    "proposal_apply": "Apply and index the exact prepared revision after showing review_changes in chat. INSTRUCTIONS.md controls approval: when knowledge_approval_required is true (or absent), pass the actual user confirmation of that revision; when false, omit confirmation and apply without asking. Never fabricate confirmation. Instructions changes always use instructions_apply with approval. Revisions are checked; chat presentation and message origin cannot be authenticated. Saves preserve tmp; partial failures retry the same proposal without duplicate topics.",
    "finish": "Only after the current results complete memory review and the task and memory discussion are complete, close the cycle and clear its tmp without separate permission or a confirmation argument. Missing/stale preparation, pending required approval and unfinished proposals/indexing block closure and preserve tmp. In purpose=instructions cycles, complete the instructions proposal instead of performing a knowledge review. A no-change work result must first be recorded through proposal_prepare(changes=[], no_changes_reason=...) after searching and comparing; no knowledge write or approval is needed for it. cancel requires actual user cancellation; it discards temporary state and reports unfinished operations without rolling back knowledge. Retry is idempotent.",
    "reconcile": "Retry derived indexing of already saved permanent text. It does not approve or rewrite knowledge. After repairing a proposal's pending indexing, retry proposal_apply to complete that operation.",
    "switch_embeddings": "With authority to change the common memory root's provider/configuration, rebuild the shared derived index for all compatible categories. Failure retains the old profile/table. No knowledge text changes; this setting is root-wide, not per-context.",
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
    "recover_workspace": "Recover missing derived runtime directories inside an explicitly started cycle. Missing knowledge stays blocked; no silent recreation or restoration of permanent facts.",
}


_QUERY_OPERATIONS = frozenset(
    {
        "workspace_inspect",
        "upgrade_plan",
        "status",
        "list",
        "read",
        "read_many",
        "search",
        "instructions_read",
        "project_read",
        "current_list",
        "current_read",
        "tmp_read",
        "tmp_list",
        "proposal_read",
        "history_read",
        "history_list",
        "history_diff",
        "analytics_query",
        "analytics_read",
        "analytics_blob_read",
        "audit",
    }
)
_EXECUTE_OPERATIONS = frozenset(
    {
        "workspace_create",
        "upgrade_apply",
        "startup",
        "project_update",
        "project_apply",
        "current_create",
        "current_update",
        "instructions_prepare",
        "instructions_apply",
        "tmp_write",
        "proposal_prepare",
        "proposal_discard",
        "proposal_apply",
        "finish",
        "reconcile",
        "switch_embeddings",
        "checkpoint",
        "history_retry",
        "analytics_evaluate",
        "analytics_import",
        "recover_workspace",
    }
)
if (
    _QUERY_OPERATIONS & _EXECUTE_OPERATIONS
    or _QUERY_OPERATIONS | _EXECUTE_OPERATIONS != _DESCRIPTIONS.keys()
):
    raise RuntimeError("Every PCW operation must have exactly one entrypoint")


def _argument_model(name: str):
    """Use the existing method contract for both validation and on-demand help."""
    method = getattr(CycleRuntime, name)
    annotations = get_type_hints(method)
    fields = {
        p.name: (
            annotations[p.name],
            ... if p.default is inspect.Parameter.empty else p.default,
        )
        for p in inspect.signature(method).parameters.values()
        if p.name != "self"
    }
    return create_model(
        name + "_arguments",
        __config__=ConfigDict(extra="forbid", strict=True),
        **fields,
    )


_ARGUMENT_MODELS = {name: _argument_model(name) for name in _DESCRIPTIONS}
_DESCRIBE_MODEL = create_model(
    "describe_arguments",
    operation=(str | None, None),
    __config__=ConfigDict(extra="forbid", strict=True),
)


def register_operations(registry, provider_factory=None):
    from contextopus.core.operations import OperationSpec

    def handler(name):
        def call(context, **arguments):
            if context is None or not context.workspace:
                raise ValueError("An explicit Workspace context is required")
            from .server import dispatch

            return dispatch(
                str(context.root),
                context.workspace,
                name,
                arguments,
                **({"provider_factory": provider_factory} if provider_factory else {}),
            )

        return call

    for name, description in _DESCRIPTIONS.items():
        registry.register(
            OperationSpec(
                "workspace." + name,
                "query" if name in _QUERY_OPERATIONS else "execute",
                _ARGUMENT_MODELS[name],
                handler(name),
                description,
            )
        )

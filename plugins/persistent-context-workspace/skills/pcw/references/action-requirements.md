# Action requirements

This file is loaded by `pcw_action_requirements`. The primary asks for exactly one action immediately before it acts. The returned instructions do not dispatch agents or replace the user's authority.

## prepare_assignment

First open/resume the actual request with `pcw_task_begin`; use `pcw_task_status` to retain outstanding assignments. A ready preparation registers the complete assignment and allocates its return ID. Send the returned `handoff.launch_message` without dropping its context, then bind the actual native session with `pcw_assignment_bind`. The executor must obtain that same full assignment with `pcw_assignment_get` before acting. Cancel an unused, unlaunched preparation with `pcw_assignment_cancel` and a reason. Launched assignments require a real return, including failures.

For a follow-up, supply `continuation_of` with the prior processed assignment ID and a fresh complete assignment. This retains that executor and return ID without reusing obsolete task context. State any known current status explicitly and require fresh observation before reporting it. A bounded recovery assignment uses `purpose: "recovery"`; model-map validation still applies, while unavailable memory is not required to prepare its empty-memory context. Write the five Current fields after recovery when they can actually be saved.

You may omit context to retrieve instructions while preparing the assignment; this does not confirm launch readiness. Before every native launch, call this action with the complete assignment and an exact profile ID from the current tools map. If `ready` is false, resolve every reported missing prerequisite and repeat the call with corrected context. Launch only after it returns `ready: true`. Profile IDs in examples are illustrative; replace them with an exact published profile ID. A successful readiness check verifies the supplied data, not the semantic suitability of the task or the user's authority.

Confirm the user outcome, scope, authority, Current and relevant knowledge supplied through MCP. The primary itself uses native environment tools, descriptors, and necessary environment configuration to establish current model/reasoning combinations, then calls `pcw_environment_check`. When a tools map is absent or stale, the primary itself gathers the available model information, compares it with roles, chooses profiles, and publishes a map for the current environment revision before choosing a profile. This limited capability work is not delegated real-source research. Select a profile that fits the prepared task; explain any choice of greater capability or reasoning depth. The native assignment must state outcome, authorized roots or objects, constraints, non-goals, relevant material filename-IDs, acceptance or check criteria, and what the worker must return. The primary launches the agent directly with the chosen model and supported reasoning settings.

For the first normal assignment of this request, the primary determines Goal, Constraints, Completion, Current step, and Blocker from the registered user task and includes saving all five through `pcw_current_set` in that assignment, including bounded research. If startup recovery is required first, write Current immediately after memory becomes available. Reading existing Current does not defer this write. Read the saved Current through MCP; later updates follow changes in the task decision or obstacle, not every return.

If status establishes that knowledge is empty, do not search that empty memory. Prepare the needed bounded source research from the user's task and supplied context. Search and navigation become useful after relevant knowledge exists.

Before an implementation assignment, assess whether the supplied knowledge is sufficient for that exact change. If necessary interfaces, component interactions, change conditions, or verification details are still unknown, first assign bounded research to establish them. Passing only source paths and the overall user request does not supply those missing facts. Use the saved research to prepare the later implementation assignment. When planning the work, also choose and explain the intermediate or final factual checks that its complexity requires, their objects, and observable conformity criteria; do not leave those decisions to a worker or schedule checks automatically after every return.

For a simple local change, a final check can suffice. For several interacting components, plan an intermediate check of their interaction and a final check of the complete result. If later changes depend on research conclusions, plan a check of those key conclusions before the dependent implementation. Choose the concrete moments for this task and revise the remaining plan when new facts require it.

Pass a complete, structured assignment. `material_ids` may be empty when no relevant knowledge exists; its `summary` still supplies the prepared user context. `constraints: []` explicitly declares no constraints. `launch_parameters` is optional and may contain only parameters actually declared by the current native environment.

Establish how the native host supplies the individual executor's identifier before launch. If the launch response omits it, give the worker a first step to read its own identifier from native metadata before opening task materials, retain that exact value, and include it unchanged in the return; see [Native assignments](native-assignments.md). Do not use a shared parent/session-tree ID or invent an identifier for the later primary save.

```json
{
  "assignment": {
    "goal": "Investigate the selected source",
    "expected_result": "Return observations and a blocker if any",
    "boundaries": "Read only the authorized source",
    "context": {"summary": "The user requested a bounded investigation.", "material_ids": []},
    "constraints": [],
    "acceptance_criteria": ["Observed result is recorded"],
    "knowledge_to_return": "Facts, sources, conditions, and blocker",
    "profile": "prepared-change",
    "selection_reason": "This current map profile fits the prepared scope"
  }
}
```

## process_result

The primary receives the worker's raw return and actual executor session identifier. Before interpreting it, call `pcw_save_subagent_result` with the registered `assignment_id`, raw Markdown, and `executor_session_id`. A confirmed save returns the MCP-generated ID and `saved_at`; call `pcw_read` with that material ID and the same assignment ID. Then declare `assessment: {"status": "accepted", "reason": "observed basis"}` or `needs_attention`. A missing session identifier, failed save, or unreadable result is a concrete blocker. Saving is not acceptance and does not prove that a source change or check succeeded.

The expected session identifier is required and is compared with the saved metadata. Use the individual ID established for this executor from native metadata. If the return contains a different ID, a new executor reports another executor's individual ID, or no actual ID was obtained, clarify the executor identity before saving; do not substitute an ID from a source material or an earlier worker. A same-executor follow-up retains its original ID.

A new raw return from the same executor may use its existing raw-result filename with `expected_previous_revision` from the previously read record; see [Memory operations](memory-operations.md). Pass the new text unchanged, then read the saved version. A different body without this guarded revision is a conflict. After reading, check that returns for memory or Git operations include the actually affected material IDs and status; request a correction when they are missing or stale.

```json
{"result": {"assignment_id": "returned-assignment-id", "material_name": "returned-material-id.md", "executor_session_id": "actual-worker-session"}, "assessment": {"status": "accepted", "reason": "The saved observations address this assignment."}}
```

## transition

The primary selects factual checks from task complexity at planned intermediate or final moments. It also schedules one if the saved return shows a mismatch requiring attention. It does not schedule a check merely because any result arrived. A checker gets the original requirement, object under check, expected observation, concrete signs of conformity, allowed scope, and relevant material filename-IDs. The checker reproduces behavior or verifies real sources, including for no-change research, and returns observations, method, mismatch, uncertainty, and blocker. Its raw result is saved and read by the `process_result` order. A stored check result is a prerequisite record; the primary still evaluates it.

For an existing output, have the checker observe its current state before any authorized regeneration or replacement, and distinguish that observation from a later reproduction. Rebuilding first can hide the very mismatch the check must detect; see [Native assignments](native-assignments.md).

Declare either the saved coordinates of a check that is due, or that none is due. Omitted data does not mean no check is due. The `none_due` branch is available only when no planned check is due and no mismatch needs attention; it is not an acceptance decision.

```json
{"checks_due": {"status": "none_due", "reason": "No planned stage or mismatch requires a check."}}
```

```json
{"checks_due": {"status": "assigned", "checks": [{"material_name": "check-result.md", "executor_session_id": "checker-session-4"}]}}
```

## finish

This action checks the active task ledger and actual durable state. Every registered, uncancelled assignment needs a saved, read and assessed return. A `needs_attention` assessment remains unresolved until an accepted clarification/check supplies its ID in `assessment.resolves`. A later omitted or false mismatch flag does not clear it. New/changed retained materials must have current search parts; changed durable paths must match the memory checkpoint unless the user prohibited it in the recorded task policy. MCP reports specific remaining steps with `ready: false`.

Read the saved outputs and the factual-check results selected for this task. Compare actual observations with the user's requested outcome, constraints, and completion condition. Confirm that scheduled checks have material results where required, that known mismatches are addressed or reported, and that any Current update reflects the chosen next step or blocker. The primary accepts, continues, or reports the concrete gap. A passing static test, a saved file, an MCP readiness response, or a worker success claim alone is not proof of live behavior.

Complete the memory work required by this request before declaring the PCW workflow finished: decide the final content and links, have a worker apply that decision and any necessary Current update, have a separate small native helper prepare retained new or changed materials for search, and have a worker checkpoint the exact changed durable memory paths unless the user forbids it. This includes newly saved check results. Inspect the final MCP status for the affected materials; pending preparation or an unfinished checkpoint remains unfinished work. Follow [Memory operations](memory-operations.md) and [Prepare search](prepare-search.md). A successful `finish` confirms its observable conditions; the primary still evaluates semantic conformity and any real-world checks.

A temporary PCW work location still uses Current and knowledge with the required consolidation and local history; it does not by itself prohibit those memory operations. A prohibition of, or lack of authority for, a source-project commit does not prohibit the separate local memory checkpoint. Apply the user's actual restrictions on PCW memory; do not invent a checkpoint or consolidation ban from the location of the workspace.

Pending preparation or a missing checkpoint is remaining work, not by itself a blocker. Continue the authorized workflow while it can proceed. End with unfinished work only when a concrete obstacle requires the user's decision or authority; state that obstacle and the actual unfinished step. Merely mentioning that memory work is unfinished does not replace completing it.

Save and read service returns too. Use the fixed-scope closeout in [Memory operations](memory-operations.md#finite-service-closeout): the same preparation/checkpoint executors obtain verified deterministic `pcw_service_receipt` text, then the primary saves and reads it unchanged under each continuation's reserved return ID. After each first body change, prepare/checkpoint that body; an exact repeat does not create another pending copy. Volatile commit hashes remain in operation evidence. Every new mismatch or substantive observation must still be returned honestly and resolved before finishing.

Declare the whole acceptance scope and every factual check assigned for that task, including ones completed at earlier stages. `none_assigned` means no factual check was assigned for the scope; it must not stand for “the checks were already completed”.

The primary declares the full set of factual checks. MCP also checks all explicitly registered assignments, including diagnostic and service assignments, for saved/read/assessed returns. It cannot discover an unregistered native launch or decide semantic conformity from metadata.

```json
{"acceptance_checks": {"status": "none_assigned", "scope": "whole requested task", "reason": "No factual check was assigned."}}
```

```json
{"acceptance_checks": {"status": "assigned", "scope": "whole requested task", "checks": [{"material_name": "check-result.md", "executor_session_id": "checker-session-4"}]}}
```

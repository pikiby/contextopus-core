# Action requirements

The primary obtains one action immediately before performing it. This protocol records state and supplies instructions; it does not launch agents or grant authority. All PCW calls and memory changes belong to the primary. Workers receive only prepared task text.

## prepare_assignment

Open/resume the user request with `pcw_task_begin` and `pcw_task_status`. Set Current yourself with `pcw_current_set(step=..., blocker="")`; registered goal/constraints/completion are supplied automatically. Correct task meaning only through `pcw_task_update` with actual authority and the current request revision.

Discover available native models and reasoning yourself, record the actual environment, gather model information, compare capabilities with roles and publish a current tools map. Do not launch a bootstrap worker for map construction. Choose a sufficient profile with an explicit selection reason. Environment changes invalidate the old map.

Supply the complete assignment with an exact published profile ID. If `ready` is false, resolve every missing prerequisite and repeat the call with corrected context. Launch only after it returns `ready: true`. Readiness checks supplied data, not semantic suitability or user authority. Instructions remain available without a complete assignment.

The primary reads relevant knowledge and supplies the necessary facts as text. Do not forward memory paths, material IDs, Current or PCW state. Include the allowed real source objects, constraints, expected result, criteria and what to return. If implementation facts are missing, first assign bounded research; an overall goal and source paths alone do not fill that gap. Empty knowledge needs source research, not a search of empty memory.

Send only `handoff.launch_message` to a native agent in a separate context without the primary conversation or PCW instructions. Select model/reasoning explicitly at launch. The message prohibits PCW calls and any discovery, reading or modification of `.pcw` via files, shell or scripts. Only explicitly authorized actions are permitted. These are assignment restrictions, not a technical sandbox. Bind the actual executor session with `pcw_assignment_bind` after sending the message. Workers do not retrieve assignments through MCP. See [Native assignments](native-assignments.md).

For a continuation, provide `continuation_of` and a complete fresh assignment. It can retain the executor but receives a separate substantive return ID. Cancel an unused, unlaunched preparation explicitly. A launched worker must return findings or a blocker.

Choose factual-check timing and scope according to complexity; persist the plan with `pcw_task_checks_set`. Use purpose `check` for a checker. For the narrowly scoped boundary helper use purpose `semantic_split` and a primary-only `split_source` outside the assignment; see [Prepare search](prepare-search.md). Recovery of PCW, Current, compaction, links and checkpoints are primary operations, not worker assignments.

```json
{"assignment": {
  "goal": "Investigate the authorized source",
  "expected_result": "Return actual observations and any blocker",
  "boundaries": "Read only the source objects authorized in this task",
  "context": {"summary": "Necessary facts selected by the primary."},
  "constraints": ["Do not change sources"],
  "acceptance_criteria": ["Conclusions have observed factual support"],
  "knowledge_to_return": "Findings, method, conditions and uncertainty",
  "profile": "exact-published-profile",
  "selection_reason": "This current profile fits the prepared scope",
  "purpose": "work"
}}
```

## process_result

For a substantive work/check return, the primary calls `pcw_save_subagent_result` with assignment ID, actual executor session ID and unmodified Markdown. MCP generates the filename-ID and UTC `saved_at`. Read it using `pcw_read(material_id, assignment_id)` before assessment. Each substantive assignment gets its own material; a repeated delivery of the identical result is idempotent.

An unexpected different body is a conflict. Do not accept a different stored report merely because it exists. Resolve the actual returned text explicitly; a deliberate correction of that assignment's raw record requires `expected_previous_revision`. A different assignment must not overwrite it. A missing executor identity or failed save/read is a concrete blocker.

Declare `accepted` or `needs_attention` with a reason. An accepted clarification/check resolves a prior discrepancy by naming it in `assessment.resolves`; omission or a later false flag does not clear it. Reading/saving is not factual proof or acceptance. Technical MCP statuses and boundary-helper results remain in control state; do not send them through this substantive-material route.

```json
{"result": {"assignment_id": "registered-assignment", "material_name": "MCP-returned-ID.md", "executor_session_id": "actual-executor"}, "assessment": {"status": "accepted", "reason": "The saved observations address the assignment."}}
```

## transition

Choose checks at planned intermediate/final moments or when an observed mismatch needs attention, not automatically after every return. Give the checker necessary facts as text, the original requirements, allowed real objects and observable criteria. It inspects actual sources or reproduces behavior, including for research without changes. Inspect an existing artifact before regenerating it; distinguish that observation from later reproduction. Save, read and assess the substantive check result.

The primary records planned checks with timing, scope and criteria through `pcw_task_checks_set`, and associates each with its purpose=check assignment. Revise the plan explicitly with a reason when the task changes. State whether any check is currently due. A previously declared due check is retained across compaction until results are supplied; omitting flags does not resolve it.

```json
{"checks_due": {"status": "none_due", "reason": "No planned moment or mismatch requires a check now."}}
```

```json
{"checks_due": {"status": "assigned", "checks": [{"assignment_id": "check-assignment", "material_name": "MCP-returned-ID.md", "executor_session_id": "actual-checker"}]}}
```

## finish

Read the registered task, saved substantive results, check plan and actual memory state. Compare observed results with the user's outcome, constraints and completion condition. Planned checks need accepted results; known discrepancies and conflicting returns remain outstanding until resolved. A worker's success claim, saved file, passing static test or `ready` response alone does not prove actual conformity.

The primary applies needed compaction, links and Current updates. Prepare retained new/changed content with the narrow semantic helper; its boundaries and indexing status are service state, never a new knowledge material. There is no report-about-preparation loop. Inspect actual preparation state. All registered work must be accounted for, but no helper is launched merely to update Current or checkpoint memory.

Checkpoint exact affected durable paths only when the registered policy is `required` with actual authority. Default `not_authorized` and an explicit `forbidden` policy do not require a commit and do not permit one. Do not infer authorization from the workspace location or absence of a prohibition. Respect user and applicable repository instructions. See [Memory operations](memory-operations.md).

Call finish with the whole acceptance scope and results of all factual checks assigned for it. `none_assigned` means none were assigned, not that earlier checks have finished. A missing required preparation/checkpoint remains work to complete; report a concrete blocker when authorized continuation is impossible. A successful finish records the observable conditions; the primary still makes the semantic acceptance decision.

```json
{"acceptance_checks": {"status": "none_assigned", "scope": "whole requested task", "reason": "No separate factual check was assigned for this task."}}
```

```json
{"acceptance_checks": {"status": "assigned", "scope": "whole requested task", "checks": [{"assignment_id": "check-assignment", "material_name": "MCP-returned-ID.md", "executor_session_id": "actual-checker"}]}}
```

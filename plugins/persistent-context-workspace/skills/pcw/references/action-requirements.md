# Action requirements

Read this reference or call `pcw_rules_get` when the relevant rule is needed. Rule retrieval does not prepare assignments, assess results, register checks or finish tasks. Do not fetch these instructions before every operation. All PCW operations belong to the primary; workers receive only complete prepared task text.

## prepare_assignment

Use `pcw_startup` once to restore state. Open a new request through `pcw_task_begin` only when needed. Set Current's step and blocker yourself; goal, constraints and completion come from the registered request. An authorized request correction uses `pcw_task_update` with the current request revision and reason.

The primary discovers actual available native models and reasoning, records the environment and publishes a tools map. Reuse the map while those capabilities remain unchanged. Keep the actual version separate from warning output and session identity. Choose a sufficient published profile and state why it fits. Do not launch a worker to build the map.

Call `pcw_assignment_prepare` with a complete assignment and the exact profile. Resolve missing prerequisites before launching; only `ready: true` permits the prepared launch. Readiness validates supplied state, not semantic suitability or user authority.

Read relevant knowledge and supply needed facts as text. Do not forward memory paths, material IDs, Current or ledger state. Include allowed real source objects, constraints, expected result, observable criteria and what to return. Missing implementation facts call for bounded research; an overall goal and source paths alone do not supply them. Empty knowledge needs source research, not a search of empty memory.

Send only `handoff.launch_message` in a separate native context without the primary conversation or PCW instructions. Select supported model/reasoning explicitly. The handoff prohibits PCW and discovery, reading or modification of `.pcw` via any tool, shell or script. This is an assignment restriction, not a technical sandbox. Bind the actual session with `pcw_assignment_bind`. See [Native assignments](native-assignments.md).

A continuation uses `continuation_of` and a complete fresh assignment, even in the same worker session. It has separate return accounting. Use a new clean session when old context is inappropriate. Cancel an unused unlaunched preparation explicitly; a launched worker must return findings or its blocker.

Record planned checks through `pcw_task_checks_set`; pass their `check_id` when preparing purpose `check` assignments so binding does not require rewriting the plan. For purpose `semantic_split`, supply primary-only `split_source` or `split_sources` outside the assignment; see [Prepare search](prepare-search.md). PCW recovery, Current, consolidation, links and memory checkpoints are primary operations.

Assignment example; shared `work_root` and `workspace` arguments are omitted:

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

Immediately divide each substantive work/check return into large, independently meaningful knowledge materials. The primary makes these topic decisions, preserves actual facts, conditions, details, tables, code and uncertainty, and links related materials. Do not split mechanically by headings or size. No additional unmodified monolithic return is required.

For incomplete/error returns, call `pcw_return_record` with actual content, reason and missing requirements, then prepare a continuation. No knowledge file or false acceptance is needed. Completed operational verification without new reusable facts also uses control storage and explicit assessment. Resolve an incomplete return by naming it in the accepted continuation's `assessment.resolves`.

For substantive knowledge, call `pcw_result_store` with the assignment ID, actual executor identity, topic `blocks` and explicit `links`. MCP generates IDs, saves bodies and links, verifies disk read-back and returns observed bodies plus `split_sources`. Inspect this single response and call `pcw_result_assess`. Do not repeat read/link/prepare for the same state. Store useful new facts, without a monolithic artifact copy or operational status embedded in knowledge.

An identical retry is idempotent. Different content conflicts rather than silently replacing a saved return. An explicit correction of the same registered blocks uses their `expected_previous_revisions`; repartitioning existing knowledge is consolidation, not a retry. A different assignment never overwrites a prior return. Missing actual executor identity or failed save/read remains a concrete blocker.

Declare `accepted` or `needs_attention` with a reason. For `needs_attention`, `assessment.affected_material_ids` identifies incorrect active knowledge; omission selects all saved blocks of this return. The assessment captures their body state. An accepted clarification/check names earlier assignment IDs in `assessment.resolves`; every captured body must have been corrected or replaced before resolution. A link-only change leaves the wrong body unchanged. Saving, reading and a worker success claim do not establish factual acceptance.

Technical receipts and helper boundaries stay in control state. The later boundary helper does not decide the topic materials and does not produce another knowledge report.

Obtain executor identity from native launch/metadata evidence, never inherited shell variables. Repair a proven wrong binding through `pcw_assignment_rebind`; identity conflicts remain blocking even when later calls reuse the old ID. See [Native assignments](native-assignments.md).

```json
{"assignment_id": "registered-assignment", "assessment": {
  "status": "accepted",
  "reason": "The saved and read observations satisfy the assignment."
}}
```

## transition

Call `pcw_transition` with the applicable check state. Choose factual checks at planned intermediate/final moments or when an observed mismatch needs attention, not automatically after each return. Give the checker the original requirement, necessary facts, allowed real objects and observable criteria. It checks actual sources or reproduces behavior, including research without changes.

Inspect existing artifacts before regenerating them and distinguish observations from later reproduction. Save, read and assess substantive findings. Bind a planned checker using `check_id` during preparation; revise the saved plan with a reason only when its timing, scope or criteria change.

State whether a check is due. An already declared due check remains outstanding across compaction; omitted flags do not clear it.

```json
{"checks_due": {"status": "none_due", "reason": "No planned moment or observed mismatch requires a check now."}}
```

For an assigned check, use its actual saved result coordinates returned by MCP, including the assignment and executor session. All blocks must have been read and assessed; one coordinate is not a substitute for processing the whole return.

## finish

Compare the registered request and actual observations with the user's whole outcome, constraints and completion condition. Reuse known state and refresh what changed; do not repeat the startup sequence. Planned checks need accepted results. Known discrepancies, conflicting returns and unfinished assignments remain outstanding until addressed.

The primary corrects inaccurate active knowledge, applies needed consolidation and links, and updates Current. Prepare retained changed bodies with the narrow helper and verify actual preparation state. Its arrays and indexing receipts remain service state; there is no report-about-preparation loop.

Checkpoint exact affected durable paths only when policy is `required` with actual authority. Default `not_authorized` and explicit `forbidden` do not require or permit a commit. See [Memory operations](memory-operations.md).

Call `pcw_finish` with the whole acceptance scope and results of its factual checks. `none_assigned` means none were assigned, not that earlier checks have finished. A `ready` response, saved file, static test or worker success claim alone is not factual completion. Continue remaining authorized work until the requested outcome is achieved; if that is impossible, report the concrete blocker and unfinished step.

```json
{"acceptance_checks": {"status": "none_assigned", "scope": "whole requested task", "reason": "No separate factual check was assigned for this task."}}
```

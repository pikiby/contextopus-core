# Persistent Context Workspace

Version 0.7.2 defines one `$pcw` skill and a persistent local MCP server. This plan records the adopted design and acceptance boundaries; it is not a claim that live-host validation has passed.

## Responsibilities and workflow

The primary alone reads and changes knowledge, Current, links and task state, chooses models and authorized memory checkpoints. Workers receive complete standalone tasks with necessary facts and explicitly allowed real sources. They must not use PCW or discover/read/change `.pcw` through tools, shell or scripts. This is an assignment-level prohibition, not OS isolation.

Only `handoff.launch_message` goes to a clean native context without the primary conversation, memory paths/IDs, Current or ledger. The primary binds the actual executor session. Every follow-up is a fresh complete registered assignment, even when a suitable existing worker session is reused. PCW does not dispatch agents, intercept completion or require worker-side assignment retrieval.

## Compact control operations

One `pcw_startup` read restores task, Current, memory status and saved environment/map state. The primary reuses the tools map while actual model/reasoning capabilities are unchanged. Environment version excludes warning output and session identity.

`pcw_rules_get` supplies instructions on demand without operation side effects. `pcw_assignment_prepare`, `pcw_result_assess`, `pcw_transition` and `pcw_finish` perform their operations and return compact relevant state. Do not fetch rules before every call. Bind a planned checker with `check_id` during preparation rather than repeating `pcw_task_checks_set`. Batch independent saving, reading, linking, preparing and boundary submission without removing explicit reads, assessments or factual checks.

## Topic materials and embedding parts

Immediately after a substantive return, the primary divides its text into large, independently meaningful knowledge materials and links related topics. Preserve actual facts, conditions, implementation details, uncertainty, code and tables. Do not split mechanically by headings or fixed sizes and do not require an extra unmodified monolithic return.

`pcw_result_store` generates IDs, saves topic bodies and explicit links, and verifies their actual disk read-back in one call. Inspect the returned bodies, assess explicitly and reuse `split_sources` for the boundary helper. Exact retries are idempotent; conflicting payloads need explicit revision-checked correction. Lower-level save/read/link operations remain available. Later consolidation does not require preserving source attribution or provenance metadata in resulting knowledge.

Only then does a cheap suitable semantic helper choose embedding boundaries within the saved topic materials. Assignment preparation supplies literal numbered text from the saved revisions; `pcw_prepare_many` is needed only when current bodies/revisions are not available. The helper returns arrays without tools. `pcw_submit_boundaries_many` checks coverage and revisions and uses the existing provider/indexing path. Helper boundaries and technical receipts remain service state. Search still addresses whole topic files and their links; this is not a change to snippet-search architecture.

## Operational returns and native identity

`pcw_return_record` retains incomplete/error returns and completed operational evidence in control, without a knowledge material. Missing deliverables permit a continuation without false acceptance. A completed control return requires explicit assessment; an accepted clarification resolves earlier incomplete work. The primary saves only useful new knowledge, divided by topic and linked, and consolidates genuine duplication. Full artifact copies and unfinished task reminders are not mandatory memory.

Startup returns outstanding work and reusable profiles, not completed assignment history. Explicit task_status retains the latter. Current writes verify disk read-back internally. Workers check required deliverables before returning and verify preservation against the actual pre-task artifact. Native notifications or bounded waits replace short polling loops.

Executor identity comes from native launch/metadata evidence, never inherited shell variables. An explicit rebind corrects exact assignments and saved provenance with history and resumable failure state; known conflicts block finish. PCW records the primary's evidence, it does not authenticate host metadata. Direct prepared-message forwarding is a host capability. A text-only launcher cannot avoid transferring text; PCW must not become a launcher or invent unsupported reference parameters.

## Corrections and factual completion

A discrepancy assessment identifies affected knowledge. Incorrect active bodies must be updated or replaced before an accepted clarification/check resolves the discrepancy. Adding a clarification link and closing the ledger is insufficient. Uncorrected invalidated bodies are excluded from active search; direct reads warn. Corrected contents require preparation as usual.

The independent control store retains the request, outstanding assignments, return blocks, check plan and discrepancies across compaction or index loss. `pcw_task_update` requires the request revision and an authorized reason and preserves outstanding work. Default checkpoint policy is `not_authorized`.

The primary schedules intermediate/final factual checks for task complexity and adds checks for observed mismatches. A return alone does not trigger a checker. Checks inspect real sources or behavior, including no-change research. `pcw_finish` validates recorded prerequisites, while the primary verifies the whole requested outcome. Readiness, saved files or passing static tests alone are not completion; continue authorized unfinished work.

## Validation boundaries

Verify block content/metadata/accounting, idempotency/conflicts, explicit read/assessment, correction of active knowledge, compact APIs, batch operations, helper boundaries, task recovery, check binding and checkpoint authority in temporary state. Check MCP schema/stdio separately. Bounded native runs can demonstrate handoff and return behavior; instruction compliance does not prove OS isolation.

Existing search/provider mechanics and the [search assessment](docs/search-assessment.md) remain unchanged. Historical reports about worker memory writes or monolithic returns describe earlier designs. Existing user knowledge is not migrated or cleaned by this update. Release, installation and publication remain separate from local implementation work.

Measure complete real tasks separately: elapsed time, native model response counts/tokens, tool counts/durations, approval/transport delays when observable, and verified factual outcomes. A shorter receipt, fewer protocol calls or passing fixture is not proof of lower autonomous native latency.

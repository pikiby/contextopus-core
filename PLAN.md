# Persistent Context Workspace

Version 0.7.1 defines one `$pcw` skill and a persistent local MCP server. This plan records the adopted design and acceptance boundaries; it is not a claim that live-host validation has passed.

## Responsibilities and workflow

The primary alone reads and changes knowledge, Current, links and task state, chooses models and authorized memory checkpoints. Workers receive complete standalone tasks with necessary facts and explicitly allowed real sources. They must not use PCW or discover/read/change `.pcw` through tools, shell or scripts. This is an assignment-level prohibition, not OS isolation.

Only `handoff.launch_message` goes to a clean native context without the primary conversation, memory paths/IDs, Current or ledger. The primary binds the actual executor session. Every follow-up is a fresh complete registered assignment, even when a suitable existing worker session is reused. PCW does not dispatch agents, intercept completion or require worker-side assignment retrieval.

## Compact control operations

One `pcw_startup` read restores task, Current, memory status and saved environment/map state. The primary reuses the tools map while actual model/reasoning capabilities are unchanged. Environment version excludes warning output and session identity.

`pcw_rules_get` supplies instructions on demand without operation side effects. `pcw_assignment_prepare`, `pcw_result_assess`, `pcw_transition` and `pcw_finish` perform their operations and return compact relevant state. Do not fetch rules before every call. Bind a planned checker with `check_id` during preparation rather than repeating `pcw_task_checks_set`. Batch independent saving, reading, linking, preparing and boundary submission without removing explicit reads, assessments or factual checks.

## Topic materials and embedding parts

Immediately after a substantive return, the primary divides its text into large, independently meaningful knowledge materials and links related topics. Preserve actual facts, conditions, implementation details, uncertainty, code and tables. Do not split mechanically by headings or fixed sizes and do not require an extra unmodified monolithic return.

`pcw_save_result_blocks` generates IDs and records each block's assignment, actual executor session and UTC save time. Read all blocks with `pcw_read_many`, link with `pcw_links_many` and assess explicitly. Exact retries are idempotent; conflicting payloads need explicit revision-checked correction. Later consolidation does not require preserving source attribution or provenance metadata in resulting knowledge.

Only then does a cheap suitable semantic helper choose embedding boundaries within the saved topic materials. `pcw_prepare_many` supplies literal numbered text; the helper returns arrays without tools. `pcw_submit_boundaries_many` checks coverage and revisions and uses the existing provider/indexing path. Helper boundaries and technical receipts remain service state. Search still addresses whole topic files and their links; this is not a change to snippet-search architecture.

## Corrections and factual completion

A discrepancy assessment identifies affected knowledge. Incorrect active bodies must be updated or replaced before an accepted clarification/check resolves the discrepancy. Adding a clarification link and closing the ledger is insufficient. Uncorrected invalidated bodies are excluded from active search; direct reads warn. Corrected contents require preparation as usual.

The independent control store retains the request, outstanding assignments, return blocks, check plan and discrepancies across compaction or index loss. `pcw_task_update` requires the request revision and an authorized reason and preserves outstanding work. Default checkpoint policy is `not_authorized`.

The primary schedules intermediate/final factual checks for task complexity and adds checks for observed mismatches. A return alone does not trigger a checker. Checks inspect real sources or behavior, including no-change research. `pcw_finish` validates recorded prerequisites, while the primary verifies the whole requested outcome. Readiness, saved files or passing static tests alone are not completion; continue authorized unfinished work.

## Validation boundaries

Verify block content/metadata/accounting, idempotency/conflicts, explicit read/assessment, correction of active knowledge, compact APIs, batch operations, helper boundaries, task recovery, check binding and checkpoint authority in temporary state. Check MCP schema/stdio separately. Bounded native runs can demonstrate handoff and return behavior; instruction compliance does not prove OS isolation.

Existing search/provider mechanics and the [search assessment](docs/search-assessment.md) remain unchanged. Historical reports about worker memory writes or monolithic returns describe earlier designs. Existing user knowledge is not migrated or cleaned by this update. Release, installation and publication remain separate from local implementation work.

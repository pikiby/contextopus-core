# Changelog

## 0.8.2 — 2026-09-17

- Require the primary to submit the task conclusion to PCW before the final answer, including when there are no new facts. Update an existing topic without creating a duplicate; unchanged text remains a no-op for embeddings.
- Align the governing document, installed skill, README and MCP instructions with this requirement.
- Add a real model-turn regression to the opt-in Codex host tests: the agent must discover a new fact and save it through PCW before answering; the harness does not save the answer for it.

## 0.8.1 — 2026-09-17

- Remove the exception that allowed conversation context to replace searching PCW and reading selected knowledge materials.
- Align the governing document, skill, README and MCP instructions: retrieve only the context needed for the current task.

## 0.8.0 — 2026-09-17

- Replace mandatory native-agent workflow with primary-owned memory: direct work and optional delegation.
- Remove environment/model maps, task/assignment/executor tools, manual boundary submission and semantic-split helpers. Current is editable without a ledger.
- Automatically index ordinary Markdown saves with configurable overlapping token windows (512/64 by default), Qwen local embeddings, or an explicitly configured local/API source and matching tokenizer.
- Preserve saved text on indexing failure; retry pending work without resubmission. Rebuild legacy indexes and changed model/chunk profiles without rewriting knowledge.
- Retain exact-ID links, compaction, revision checks, storage-loss detection and authorized local memory checkpoints. Preserve warnings for known incorrect legacy revisions.

## 0.7.2

- Add control-only incomplete/error and operational returns; continuations no longer require technical knowledge files or premature acceptance.
- Add result_store: topic bodies, explicit links and verified disk read-back in one operation, with revisions ready for semantic boundary preparation.
- Require native launch/metadata evidence at MCP binding; retain conflicts and support explicit resumable correction of assignments and result provenance.
- Omit completed assignment history from startup, compact map publication receipts, verify Current writes internally and return current recovery operation names.
- Require full requested deliverables in worker returns; document topic consolidation, native notification waits and the text-only launcher's transfer limitation.
- Add whole-cycle trace measurement and regression coverage. See [verification and limitations](docs/return-cycle-assessment.md).

Upgrade the marketplace, reinstall and start a new thread. `pcw_assignment_bind` now requires `evidence` with source, reference and matching executor_session_id. Existing knowledge and history are not migrated or cleaned on upgrade. The published 0.7.1 release remains unchanged.

## 0.7.1

- Save primary-selected coherent topic blocks as distinct generated-ID materials before within-file embedding segmentation; no duplicate full-return file.
- Separate read-only rules from operational assignment, assessment, transition and finish commands; add compact startup and operation responses.
- Add batch save/read/link/preparation/boundary operations and direct planned-check binding.
- Require actual knowledge correction before resolving discrepancies; keep uncorrected findings out of ordinary search.
- Normalize legacy search IDs to readable filename IDs without implicit migration or re-embedding.
- Reuse current tools maps and derive supported launch parameters from recorded capabilities without duplicate declarations.

### Upgrade and verification

Refresh the marketplace, reinstall and start a new thread. The MCP surface replaces `pcw_action_requirements` with separate rules/assignment/assessment/transition/finish tools, and `pcw_save_subagent_result` with `pcw_save_result_blocks`. Existing user knowledge is not automatically split, migrated or deleted.

The suite passed 171 tests and 73 subtests with six opt-in skips. A native-agent cycle saved two linked topic files, corrected an observed wording error and completed indexing without technical knowledge files. Four equivalent workflow response bodies decreased from 12,072 to 1,770 bytes; this is not an end-to-end speed measurement. See the [0.7.1 assessment](docs/compact-memory-assessment.md) for evidence and limits.

## 0.7.0

- Make PCW the primary agent's memory: the primary reads and changes knowledge, Current, links, compaction and authorized memory history.
- Generate standalone worker assignments with inline facts and explicit prohibitions on PCW tools and `.pcw` access. This is an assignment-level restriction, not a filesystem or tool sandbox.
- Replace worker-side assignment retrieval and service receipts with primary delivery and semantic block-boundary submission. Technical results remain in control state and do not generate knowledge materials.
- Allocate a separate MCP-generated return ID for every substantive assignment, including continuations; retain exact raw text, UTC save time and actual executor session identity.
- Block acceptance of conflicting returns; persist factual-check plans, due checks and unresolved discrepancies.
- Keep Current aligned with the registered task; support revision-checked task updates without losing outstanding assignments. Distinguish an unauthorized checkpoint from an explicitly forbidden one.

### Upgrade

Refresh the Git marketplace and reinstall using [the update commands](README.md#update-the-codex-plugin), then start a new Codex thread. The MCP API removes `pcw_assignment_get` and `pcw_service_receipt`; new operations include `pcw_submit_boundaries`, `pcw_service_error`, `pcw_task_update` and `pcw_task_checks_set`. `pcw_task_begin` defaults to `checkpoint_policy=not_authorized`. Existing knowledge is not migrated or cleaned automatically.

### Verification records

The complete test suite passed 147 tests and 73 subtests, with six opt-in skips. A bounded native-agent cycle using the real MCP server and test vectors produced one indexed substantive material and no technical knowledge files. The semantic helper returned only `[3,7]` without tool calls. The author made an extra progress-only tool call; this limitation and the distinction from technical isolation are recorded in the [primary-memory assessment](docs/primary-memory-assessment.md).

## 0.6.0

- Generate material IDs and filenames in MCP; keep the ID unchanged when moving a material.
- Register tasks and complete assignments, bind actual executor sessions, and track delivery, raw-result saving, reading, assessment, and unresolved discrepancies.
- Check actual task-owned files, search preparation, Current, and local memory checkpoints before allowing completion.
- Keep model maps, instructions, and assignment state outside the derived runtime so recovery remains available when runtime storage disappears.
- Close preparation and checkpoint returns through verified, stable service receipts and idempotent repeat delivery.
- Preserve the primary agent's explicit native launches and MCP calls; no environment completion hooks are introduced.

### Upgrade

Refresh the Git marketplace and reinstall using the commands in [README](README.md#update-the-codex-plugin), then start a new Codex thread.

The MCP API changes: `pcw_create` accepts content and optional links without a filename; `pcw_save_subagent_result` requires a registered `assignment_id` instead of an agent-chosen `material_name`. Open a task with `pcw_task_begin`, prepare and bind assignments, and deliver the full assignment before saving returns. Existing knowledge remains readable and is not renamed automatically.

### Verification records

The complete test suite passed 131 tests and 73 subtests, with six opt-in skips and seven warnings. The tests include actual MCP stdio calls, LanceDB, temporary Git checkpoints, recovery, and finite service closeout with injected test vectors. These results do not constitute a new real-model or native-agent workflow check. See the [implementation assessment](docs/implementation-assessment.md).

## 0.5.0

- Add MCP instructions and prerequisite checks for preparing assignments, processing returns, moving between stages, and finishing work.
- Store the primary agent's environment-specific model and reasoning map; require its refresh when the recorded environment changes.
- Save unmodified subagent returns through MCP with UTC timestamps and executor session IDs. Support guarded replacement by revision and idempotent repeat delivery.
- Use filenames as knowledge IDs, with explicit legacy migration and link-preserving rename, move, merge, and deletion operations.
- Keep Current readable in five Markdown sections, including when values contain headings, code, or trailing newlines.
- Define planned and mismatch-triggered factual checks, literal preparation by a separate small model, and completion of memory checkpoints.
- Limit local embedding batches to one text while reusing the loaded Qwen model.
- Add runtime, host, and native-workflow verification, plus separate implementation, regulation, coverage, and search assessments.

### Upgrade

Refresh the configured Git marketplace and reinstall the plugin using the commands in [README](README.md#update-the-codex-plugin). Start a new Codex thread afterward.

UUID-addressed knowledge is migrated only through an explicit `pcw_migrate_legacy_ids` request. Installation preserves existing memory without silently converting it.

### Verification records

Release validation: the plugin manifest validator passed; the test suite passed 121 tests and 73 subtests, with six opt-in skips. All four fresh Codex/MCP checks then passed with the installed 0.5.0 package and cached offline Qwen. Earlier independently assessed native workflows cover the unchanged runtime and agent instructions.

The published assessments describe the checks and their limits. Detailed local traces and snapshots referenced under `.pcw/project-update/.pcw-runtime/verification/` are local evidence, not part of the distributed plugin.

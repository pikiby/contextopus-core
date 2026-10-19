# Changelog

## 1.5.0 — 2026-10-18

- Separate Core from optional Workspace and Session Search modules; Core ships shared infrastructure and the `m` skill.
- Add fresh Core-only and full starter installers using the same verified bundle machinery, with explicit module subsets, CPU model setup and selected native clients.
- Install trusted built module folders or ZIPs through `modules install ID --source PATH`; preview checked paths, identity and compatibility with `--plan`, preserve source revisions and refuse existing targets.
- Document independent module services, storage and migration lifecycles, retained failure state and platform acceptance limits. See [release notes](docs/releases/1.5.0.md).

## 1.3.3 — 2026-10-17

- Handle upgrade previews for legacy contexts that have no initial INSTRUCTIONS and retain pending proposals. An absent previous instruction body is not hashed as text; revision overlays for existing rules retain their checks.
- Preserve the requirement to review and approve initial rules through the existing migration procedure. Migration does not approve, cancel or rewrite the original reviewed pending work.


## 0.14.0 — unreleased

- Share one RAG/profile and analytical database across context folders under a selected memory root. Search defaults to the active category; explicit category lists and all-category retrieval preserve its instructions and write destination.
- Introduce workspace format 2 with stable YAML IDs, descriptive filenames, cross-context links and unchanged-body vector reuse across path/category moves.
- Generalize required sources to `reference` and `instruction`, covering files, records, queries and knowledge fragments as well as URLs. Skills require fresh bounded retrieval on every receipt.
- Automatically route detected incompatibility to upgrade. Migrate cards and shared index together, retain workspace/control backups, custom instructions and unfinished proposals, and resume after file/index failures.

## 0.13.0 — 2026-10-07

- Ask separately whether new contexts should author required external source links. Store the explicit choice in INSTRUCTIONS; preserve existing settings and retries of older accepted creation requests.
- Define body-level required-source blocks with a URL and bounded extraction question. Skills require a fresh check on every receipt, independently of the authoring setting; ordinary citations remain ordinary citations. Fetching is an agent procedure, not an automatic runtime operation.
- Rename `pcw-instructions` to `pcw-edit-instructions` for action-based naming and add `pcw-analyze` for scoped, evidence-based analysis of PCW reads, link traversals, changes and errors, optionally using another agent's selected transcript.

## 0.12.2 — 2026-10-05

- Restore the material-size question at context creation. Offer 1024 tokens first as the recommended choice, then a custom limit or no limit. Ask for a number only for a custom choice and wait for the user's selection.

## 0.12.1 — 2026-10-05

- Use a standard 1024-token knowledge-body limit for new contexts. Creation takes it from the instructions template without asking the user to choose a number; explicit overrides and disabling remain supported.
- Preserve existing context settings and the legacy no-limit fallback. Explain the default in terms of full-material retrieval size rather than an unmeasured semantic optimum.

## 0.12.0 — 2026-10-05

- Replace 42 per-operation MCP tools with `pcw_query` and `pcw_execute`; keep existing operations behind explicit read/change allowlists and strict parameter validation.
- Describe one operation's contract on demand, or list operation names, without accessing workspace storage or loading all schemas into the model context.
- Preserve operation-level analytics, workspace selection, cycle, revision and approval checks. Workspace format remains 1; clients must reload the new MCP interface.
- Update all seven skills and host/protocol checks for the two entrypoints. Diagnose server registration, host connection and model-visible tools separately; do not substitute internal runtime calls for missing MCP tools.

## 0.11.2 — 2026-10-02

- Inspect unfinished work and damaged proposals even when a workspace already uses the current format.
- Report missing, empty or placeholder PROJECT descriptions separately from format compatibility, including after migration; presence alone is not a content review.
- Make the upgrade procedure report remaining content work and route requested PROJECT completion through the existing reviewed update procedure.

## 0.11.1 — 2026-10-02

- Include compatibility, concrete unfinished work and blockers in the migration plan; the upgrade skill needs only this preflight call.
- Preserve compatible active cycles, temporary results, prepared proposals and already-applied proposal states during format migration. Migration neither approves proposals nor closes old work.
- Back up the entire workspace and its separate control state, including cycle records and material-ID reservations. Bind review to temporary and control changes and verify both snapshots before recording the new format.
- Resume interrupted snapshots and migrations using the original revision and backup, without overwriting retained files. Report incompatible work before application.

## 0.11.0 — 2026-09-30

- Separate explicit workspace creation, existing-context opening and independent reading; add format inspection and recoverable migration of recognized legacy contexts.
- Add PROJECT and independent per-task Current with revision checks, alongside separate implicit-update and approval policies.
- Add saved link descriptions, validated link traversal and an optional token limit for final semantic materials.
- Capture local permanent-data Git history with exact snapshots for retry; expose version listing, comparison and reading.
- Record dispatched MCP calls and observed file revisions in SQLite, with sanitized bodies, explicit transcript imports and separate assessments.
- Add search, upgrade, audit and rework mini-skills and natural-language routing. Preserve exact chat review and mandatory approval for instruction changes.
- Fix retrieving link labels from a prepared proposal after a fresh process starts.

### Upgrade

Refresh the configured marketplace, reinstall PCW and start a new Codex session. Existing workspaces are preserved; use `pcw-upgrade` explicitly for their format transition before opening work cycles. Installation does not migrate memories or reset their instructions. Missing legacy settings retain restricted defaults. See [contracts and compatibility](https://github.com/pikiby/contextopus-workspace/blob/v1.5.0/docs/archive/context-workspace-v3-contracts.md) and [verification](https://github.com/pikiby/contextopus-workspace/blob/v1.5.0/docs/archive/context-workspace-v3-verification.md).

## 0.10.0 — 2026-09-23

- Add pcw-create for user-requested context creation with placement and task selection. Route functional requests through pcw; require explicit creation/switching instructions and clarification of an unknown context before startup.
- Configure knowledge approval through INSTRUCTIONS.md frontmatter (`knowledge_approval_required`), initially false. Always show changes; always require approval for instruction edits. Existing files without the setting retain required approval.

- Replace fixed-field Current with persistent, free-form workspace INSTRUCTIONS.md, returned in full at startup.
- Bootstrap new instructions from one packaged template; preserve user edits across cycles and keep project rules out of duplicate skill/MCP guidance.
- Add the explicit pcw-instructions mini-skill and reviewed instructions read/prepare/apply tools. The main skill routes direct edit requests to this one procedure.
- Keep task state in tmp; isolate instructions-only cycles from knowledge work. Detect stale approvals and changed rules without indexing instructions.


## 0.9.3 — 2026-09-22

- Make result review mandatory after work: search by the conclusion, compare with permanent knowledge, then prepare and present proposed changes for approval.
- Block normal closure when preparation is missing or does not cover the current temporary materials. Preserve tmp while review, approval or application is incomplete; keep closure free of a separate permission request.
- Support `pcw_proposal_prepare(changes=[], no_changes_reason=...)` for a reviewed no-change outcome without writing knowledge, indexing or requesting approval. New or changed temporary results require another review; Current updates do not.
- Align the governing document, skill, MCP instructions and runtime checks; add regression coverage for skipped preparation, changed results, no-change outcomes and cancellation, and require result-driven search in the opt-in agent test.

## 0.9.2 — 2026-09-22

- Remove the separate approval requirement for closing a completed PCW cycle. The agent calls `pcw_finish` and clears tmp as part of completion, without another permission question.
- Remove the `confirmation` argument from `pcw_finish`; preserve explicit approval for permanent knowledge changes.
- Align the governing document, skill, MCP instructions and tests. Pending knowledge approval and unfinished writes/indexing still keep the cycle open; cleanup remains isolated and retry-safe.

## 0.9.1 — 2026-09-22

- Require proposal contents in chat before approval: topic names, full new text or before/after passages, deletions and link effects. File links and topic lists alone do not constitute presentation.
- Return exact `review_changes` from preparation and retrieval, including readable topic names and automatic link effects, without repeating unchanged bodies. Keep existing prepared-proposal files compatible.
- Use the current conversation language for progress, explanations and approval questions regardless of the language of instructions or stored materials.
- Explicitly explain deletion of all cycle temporary notes, returns and proposals when requesting closure; approval of a write alone does not authorize cleanup.
- Add regression coverage for complete review content, bounded changes, navigation effects and MCP transport.

## 0.9.0 — 2026-09-18

- Replace immediate permanent writes with explicit cycles, temporary results and revision-bound proposals approved by the human.
- Clear cycle tmp at startup and explicit closure; intermediate knowledge writes preserve work in progress.
- Separate preparation, readable review, application and rejection; include incoming link changes and support create/update/move/delete/merge/split in one reviewed set.
- Support restart-safe application, pending indexing, parallel cycle isolation and a clean-context agent performing the complete cycle.
- Remove direct mutation MCP entrypoints and the mandatory permanent-write-before-every-answer rule. Preserve token-window embeddings, exact topic IDs and independently authorized memory checkpoints.


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
- Add whole-cycle trace measurement and regression coverage. See [verification and limitations](https://github.com/pikiby/contextopus-workspace/blob/v1.5.0/docs/archive/return-cycle-assessment.md).

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

The suite passed 171 tests and 73 subtests with six opt-in skips. A native-agent cycle saved two linked topic files, corrected an observed wording error and completed indexing without technical knowledge files. Four equivalent workflow response bodies decreased from 12,072 to 1,770 bytes; this is not an end-to-end speed measurement. See the [0.7.1 assessment](https://github.com/pikiby/contextopus-workspace/blob/v1.5.0/docs/archive/compact-memory-assessment.md) for evidence and limits.

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

The complete test suite passed 147 tests and 73 subtests, with six opt-in skips. A bounded native-agent cycle using the real MCP server and test vectors produced one indexed substantive material and no technical knowledge files. The semantic helper returned only `[3,7]` without tool calls. The author made an extra progress-only tool call; this limitation and the distinction from technical isolation are recorded in the [primary-memory assessment](https://github.com/pikiby/contextopus-workspace/blob/v1.5.0/docs/archive/primary-memory-assessment.md).

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

The complete test suite passed 131 tests and 73 subtests, with six opt-in skips and seven warnings. The tests include actual MCP stdio calls, LanceDB, temporary Git checkpoints, recovery, and finite service closeout with injected test vectors. These results do not constitute a new real-model or native-agent workflow check. See the [implementation assessment](https://github.com/pikiby/contextopus-workspace/blob/v1.5.0/docs/archive/implementation-assessment.md).

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

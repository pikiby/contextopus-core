# Memory operations

Read this reference through the PCW action loop before selecting a workspace, changing durable memory, or recovering it. All MCP calls receive an existing absolute `work_root` and one semantic `workspace`; durable storage is `<work-root>/.pcw/<workspace>/`.

## Read before deciding

The primary calls `pcw_status`, `pcw_current_get`, `pcw_search`, `pcw_read`, and `pcw_list` to obtain PCW context. It reads Current on start or recovery and opens only relevant full materials. Search returns a bounded selection; an empty result does not prove that knowledge is absent or fresh. The primary does not inspect real project sources, diffs, logs, or external services itself while the skill is active. Native capability descriptors and the necessary environment configuration used to build the tools map are a limited primary responsibility, not project-source research.

Knowledge bodies are free Markdown. They can contain prose, sources, conditions, uncertainty, tables, and code. `links` is a directional list of filename-IDs for navigation; it has no required relation type, explanation, or mirror edge. The body, not a link, carries claims and conditions.

## Filename IDs and legacy memory

MCP generates a unique ID and uses it as the filename (`<generated-id>.md`). `pcw_create` accepts content and optional links, not a chosen filename. Assignment preparation reserves a generated ID for its future raw return. Store the IDs returned by MCP and use them in reads, updates, links and preparation. The ID is also the filename; there is no second identity hidden in YAML. Existing descriptive filenames remain readable until an explicitly requested migration.

`pcw_rename` moves a material to another directory while preserving its generated basename and links. It updates search paths without preparing unchanged text and rejects a different basename or occupied destination.

Migration is explicit. For a legacy UUID-addressed material, first establish its filename mapping, rewrite exact legacy links to filename-IDs, preserve body text, metadata, tables, code, sources, and meaningful relation prose, and reconcile search addresses. Do not re-embed an unchanged body merely because its filename or links changed. Do not adopt, normalize, or replace legacy memory merely because it was encountered during ordinary work.

## Save and apply

An investigating or checking worker writes its own raw result. The primary first calls:

```text
pcw_save_subagent_result(work_root, workspace, assignment_id, result, executor_session_id)
```

`assignment_id` selects the registered assignment and MCP-allocated return ID. `result` is unmodified raw Markdown. `executor_session_id` is the actual bound worker session, never a generated substitute. MCP assigns `saved_at` in ISO 8601 UTC and saves it with the executor metadata. An exact repeat retains the original body and timestamp. The primary calls `pcw_read(material_id, assignment_id)` and then `process_result` with the saved coordinates and an explicit assessment.

For a continuation registered with `continuation_of`, use its retained executor/return ID and pass `expected_previous_revision` from the previously read material. Replacement preserves links, assigns new save metadata and invalidates old search rows. Another executor or an ordinary material cannot be overwritten through this route. An exact repeat returns `already_saved` without invalidating preparation, even if its retry carries an older expected revision.

This operation saves the worker's new raw text unchanged. Register a separate assignment without reusing the return ID when earlier findings must remain independently available. Memory/Git returns identify affected IDs or paths and actual status. Register a discrepancy through `process_result` instead of silently changing the raw text; resolve it with a saved/read clarification whose accepted assessment names the prior assignment in `resolves`.

For every other durable mutation, a subagent acts on the primary's prepared decision. It can call `pcw_create`, `pcw_update`, `pcw_links`, `pcw_merge`, `pcw_reassign`, `pcw_rename`, `pcw_delete`, `pcw_current_set`, `pcw_checkpoint`, or `pcw_restore` inside its authorized assignment. The primary chooses final content, consolidation, links, and replacement mappings; PCW does not infer them from similarity.

Content writes are readable immediately and are `pending_preparation` until literal semantic parts are accepted. Links-only changes and renames do not prepare or embed text. A failed preparation or embedding leaves the material readable and honestly pending.

## Consolidation and deletion

Consolidate actual duplicate content rather than adding a summary beside it. Preserve useful implementation details, conditions, exceptions, uncertainty, tables, and code. Compaction does not require retaining source attribution or provenance metadata.

For a replacement, the primary explicitly chooses the final target content and every old filename-ID to new filename-ID mapping. The worker ensures targets exist, then uses `pcw_merge` to save targets, preserve or explicitly set outgoing links, rewrite incoming links, remove duplicates and self-links, and only then remove replaced materials and their current search rows. `pcw_reassign` changes exact navigation only; partial extraction is not a global redirect. `pcw_delete` removes incoming links, material, and current search rows, not linked targets or their prose. Report any `partial` response with applied effects.

## Current and checkpoint

Current is readable Markdown with exactly these task sections: `# Goal`, `# Constraints`, `# Completion`, `# Current step`, and `# Blocker`. `pcw_current_set` preserves unspecified values. A worker writes it from the primary's decision; PCW does not decide the goal or next action. Update step or blocker when the primary changes the next action or an obstacle changes. Goal, constraints, and completion change only when the user's request changes. Do not turn Current into a return log or rewrite it after every worker result.

Each section written by PCW includes an HTML comment `<!-- pcw-current-length: N -->` recording the number of characters in its value. The value remains visible Markdown; the marker preserves exact text when a value itself contains section headings, code, or trailing newlines. Use `pcw_current_set` to keep these lengths consistent.

An exact repeat of `pcw_checkpoint` for already committed, unchanged paths returns the existing commit with `already_checkpointed: true`; it does not create another commit or report an error merely because nothing changed.

Unless the user forbids a local memory commit, a worker calls `pcw_checkpoint` for exactly the durable Current and knowledge paths changed by the request. A prohibition of, or lack of authority for, a source-project commit does not prohibit this separate local memory checkpoint. A temporary PCW work location still uses Current and knowledge with their required consolidation and local history; the location is not a user prohibition of those operations. Include both old and new paths for a rename and affected navigation files. Preserve unrelated changes. A memory checkpoint is not authority for source commits, pushes, or external changes. `pcw_restore` needs an explicit authorized target and exact paths; `pcw_reconcile` makes derived search state match externally restored or edited knowledge.

## Finite service closeout

After the preparation helper and memory/checkpoint worker have each returned once and their raw returns are saved/read/assessed, freeze the full retained set of material IDs and exact checkpoint paths, including those two return IDs. Reuse these executors with complete registered continuations; do not create a fresh receipt filename or a fresh executor for every pass.

1. The preparation helper prepares every current pending body in that set, then calls `pcw_service_receipt(kind="preparation", material_ids=[...])`. It returns the verified `result` verbatim. The primary saves, reads and assesses it. If that first stable body differs, repeat preparation for the changed return; the next identical receipt is saved idempotently.
2. The checkpoint worker checkpoints the exact durable set, then calls `pcw_service_receipt(kind="checkpoint", paths=[...])` and returns the verified `result` verbatim. The primary saves, reads and assesses it. The first stable checkpoint return can change its own material once.
3. The same helper prepares that changed body and returns the same verified fixed-scope receipt. The same checkpoint worker checkpoints the changed receipt and returns its same verified fixed-scope receipt. Exact repeats preserve both indexing and checkpoint state. `finish` checks the actual result.

Receipts name every affected object and its observed operation status. They omit volatile hashes and timestamps from the Markdown; those remain available in MCP operation evidence, Git history and raw-save metadata. Errors, changed scope or substantive new findings must be returned honestly, never suppressed to force an identical body. Reassess and freeze the new scope after those are resolved. If checkpoint is explicitly forbidden, record that prohibition when opening the task and close only the permitted preparation work.

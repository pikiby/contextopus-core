# Memory operations

Read this reference through the PCW action loop before selecting a workspace, changing durable memory, or recovering it. All MCP calls receive an existing absolute `work_root` and one semantic `workspace`; durable storage is `<work-root>/.pcw/<workspace>/`.

## Read before deciding

The primary calls `pcw_status`, `pcw_current_get`, `pcw_search`, `pcw_read`, and `pcw_list` to obtain PCW context. It reads Current on start or recovery and opens only relevant full materials. Search returns a bounded selection; an empty result does not prove that knowledge is absent or fresh. The primary does not inspect real project sources, diffs, logs, or external services itself while the skill is active. Native capability descriptors and the necessary environment configuration used to build the tools map are a limited primary responsibility, not project-source research.

Knowledge bodies are free Markdown. They can contain prose, sources, conditions, uncertainty, tables, and code. `links` is a directional list of filename-IDs for navigation; it has no required relation type, explanation, or mirror edge. The body, not a link, carries claims and conditions.

## Filename IDs and legacy memory

MCP generates a unique ID and uses it as the filename (`<generated-id>.md`). `pcw_create` accepts content and optional links, not a chosen filename. Substantive assignment preparation reserves a generated ID for its raw return. Semantic service assignments reserve no knowledge ID. Store the IDs returned by MCP and use them in reads, updates, links and preparation. The ID is also the filename; there is no second identity hidden in YAML. Existing descriptive filenames remain readable until an explicitly requested migration.

`pcw_rename` moves a material to another directory while preserving its generated basename and links. It updates search paths without preparing unchanged text and rejects a different basename or occupied destination.

Migration is explicit. For a legacy UUID-addressed material, first establish its filename mapping, rewrite exact legacy links to filename-IDs, preserve body text, metadata, tables, code, sources, and meaningful relation prose, and reconcile search addresses. Do not re-embed an unchanged body merely because its filename or links changed. Do not adopt, normalize, or replace legacy memory merely because it was encountered during ordinary work.

## Save and apply

An investigating or checking worker writes its own raw result. The primary first calls:

```text
pcw_save_subagent_result(work_root, workspace, assignment_id, result, executor_session_id)
```

`assignment_id` selects the registered assignment and MCP-allocated return ID. `result` is unmodified raw Markdown. `executor_session_id` is the actual bound worker session, never a generated substitute. MCP assigns `saved_at` in ISO 8601 UTC and saves it with the executor metadata. An exact repeat retains the original body and timestamp. The primary calls `pcw_read(material_id, assignment_id)` and then `process_result` with the saved coordinates and an explicit assessment.

Each new substantive assignment, including a continuation, receives a new return ID. Retaining a worker session does not authorize overwriting an earlier result. Retry the same unchanged return idempotently. For an explicit correction of that same assignment's recorded raw return, pass `expected_previous_revision` from the previously read material; a conflict remains unresolved until the actual return is saved and read. Never accept another text in its place. Register factual discrepancies as `needs_attention`; resolve them through an accepted saved/read clarification whose assessment names the earlier assignment in `resolves`.

The primary alone calls `pcw_create`, `pcw_update`, `pcw_links`, `pcw_merge`, `pcw_reassign`, `pcw_rename`, `pcw_delete`, `pcw_current_set`, authorized `pcw_checkpoint` and `pcw_restore`. Workers have no memory-operation assignment. The primary chooses and applies content, consolidation, links and mappings; PCW does not infer them from similarity. Raw substantive findings belong in knowledge, while Current/indexing/checkpoint receipts stay outside it.

Content writes are readable immediately and are `pending_preparation` until literal semantic parts are accepted. Links-only changes and renames do not prepare or embed text. A failed preparation or embedding leaves the material readable and honestly pending.

## Consolidation and deletion

Consolidate actual duplicate content rather than adding a summary beside it. Preserve useful implementation details, conditions, exceptions, uncertainty, tables, and code. Compaction does not require retaining source attribution or provenance metadata.

For a replacement, the primary explicitly chooses the final target content and every old filename-ID to new filename-ID mapping. The primary ensures targets exist, then uses `pcw_merge` to save targets, preserve or explicitly set outgoing links, rewrite incoming links, remove duplicates and self-links, and only then remove replaced materials and their current search rows. `pcw_reassign` changes exact navigation only; partial extraction is not a global redirect. `pcw_delete` removes incoming links, material, and current search rows, not linked targets or their prose. Report any `partial` response with applied effects.

## Current and checkpoint

Current is readable Markdown with exactly these task sections: `# Goal`, `# Constraints`, `# Completion`, `# Current step`, and `# Blocker`. `pcw_current_set` is called by the primary. With an active task it takes goal, constraints and completion from the registered request. Omitted step/blocker stay unchanged. Use an empty blocker string for no blocker; do not write "None.". For a user-authorized change to the request use `pcw_task_update` with its revision and reason, then synchronize Current. PCW does not decide task meaning or the next action. Update step or blocker when the primary changes the next action or an obstacle changes. Goal, constraints, and completion change only when the user's request changes. Do not turn Current into a return log or rewrite it after every worker result.

Each section written by PCW includes an HTML comment `<!-- pcw-current-length: N -->` recording the number of characters in its value. The value remains visible Markdown; the marker preserves exact text when a value itself contains section headings, code, or trailing newlines. Use `pcw_current_set` to keep these lengths consistent.

An exact repeat of `pcw_checkpoint` for already committed, unchanged paths returns the existing commit with `already_checkpointed: true`; it does not create another commit or report an error merely because nothing changed.

The primary calls `pcw_checkpoint` only with actual authority recorded as policy `required` and its reason. The default is `not_authorized`; use `forbidden` for an actual prohibition. Respect an applicable instruction requiring explicit permission for commits. A context request alone must not override such a requirement. Lack of authority is not a user prohibition and does not create an unfinished required checkpoint. Include only exact request-owned durable paths, old and new paths for a move, and affected navigation files. Preserve unrelated changes. A memory checkpoint does not authorize source commits or push.

`pcw_restore` requires an authorized target and exact paths. `pcw_reconcile` makes derived search state match restored or externally edited memory. Existing memory is not migrated, deleted or cleaned merely because the plugin was upgraded.

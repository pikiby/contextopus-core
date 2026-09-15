# Memory operations

Read this reference through the PCW action loop before selecting a workspace, changing durable memory, or recovering it. All MCP calls receive an existing absolute `work_root` and one semantic `workspace`; durable storage is `<work-root>/.pcw/<workspace>/`.

## Read before deciding

The primary calls `pcw_status`, `pcw_current_get`, `pcw_search`, `pcw_read`, and `pcw_list` to obtain PCW context. It reads Current on start or recovery and opens only relevant full materials. Search returns a bounded selection; an empty result does not prove that knowledge is absent or fresh. The primary does not inspect real project sources, diffs, logs, or external services itself while the skill is active. Native capability descriptors and the necessary environment configuration used to build the tools map are a limited primary responsibility, not project-source research.

Knowledge bodies are free Markdown. They can contain prose, sources, conditions, uncertainty, tables, and code. `links` is a directional list of filename-IDs for navigation; it has no required relation type, explanation, or mirror edge. The body, not a link, carries claims and conditions.

## Filename IDs and legacy memory

A filename such as `architecture.md` is the material's unique ID within `knowledge`; its workspace-relative path is a separate address. There is no separate UUID identity. New materials are addressed by the filename-ID in `pcw_create`, `pcw_read`, `pcw_update`, `pcw_links`, `pcw_merge`, `pcw_reassign`, `pcw_delete`, and preparation operations.

`pcw_rename` changes the path and updates search-row addresses without preparing or embedding an unchanged body again. If the basename changes, it also changes the filename-ID and rewrites exact incoming links. A move such as `a.md` to `nested/a.md` keeps the ID and links unchanged. It must reject a duplicate destination. It does not retain a redirect, create a replacement material, or infer semantic relationships.

Migration is explicit. For a legacy UUID-addressed material, first establish its filename mapping, rewrite exact legacy links to filename-IDs, preserve body text, metadata, tables, code, sources, and meaningful relation prose, and reconcile search addresses. Do not re-embed an unchanged body merely because its filename or links changed. Do not adopt, normalize, or replace legacy memory merely because it was encountered during ordinary work.

## Save and apply

An investigating or checking worker writes its own raw result. The primary first calls:

```text
pcw_save_subagent_result(work_root, workspace, material_name, result, executor_session_id)
```

`material_name` is the exact filename-ID and `result` is the unmodified raw Markdown return. `executor_session_id` is the actual worker-session identifier, never a generated substitute or primary-session identifier. The MCP assigns `saved_at` in ISO 8601 UTC with an explicit timezone designator, persists both metadata fields with the text, returns them only after a real save, and rejects a missing session identifier. On a repeat delivery of the same material, raw result, and session, it keeps the original saved record and timestamp instead of duplicating it. The primary then calls `pcw_read` and only then makes a content or acceptance decision.

For a new raw return from the same executor, the primary may reuse that executor's raw-result filename by passing `expected_previous_revision` from the previously read material. MCP replaces the body only if this is an existing raw-result material with the same executor and the expected revision still matches. It preserves links, assigns a new `saved_at`, removes the old search rows, and returns `updated` with preparation pending. Without that explicit revision, a different return at an occupied name remains a conflict. A stale revision, another executor, or an ordinary knowledge material cannot be overwritten by this route; read the current record and resolve the actual conflict. An exact repeat of an already saved body and executor returns `already_saved` with its original timestamp even if a retry carries an older expected revision.

This operation saves the worker's new raw text unchanged; it does not authorize the primary to edit or compact the text. Choose a separate filename when earlier findings need to remain independently available. For memory and Git work, every raw return must include the affected filename-IDs, the Current path when affected, and the actual status. A generic completion sentence or an old list of affected materials does not satisfy that return contract.

For every other durable mutation, a subagent acts on the primary's prepared decision. It can call `pcw_create`, `pcw_update`, `pcw_links`, `pcw_merge`, `pcw_reassign`, `pcw_rename`, `pcw_delete`, `pcw_current_set`, `pcw_checkpoint`, or `pcw_restore` inside its authorized assignment. The primary chooses final content, consolidation, links, and replacement mappings; PCW does not infer them from similarity.

Content writes are readable immediately and are `pending_preparation` until literal semantic parts are accepted. Links-only changes and renames do not prepare or embed text. A failed preparation or embedding leaves the material readable and honestly pending.

## Consolidation and deletion

Consolidate actual duplicate content rather than adding a summary beside it. Preserve useful implementation details, conditions, exceptions, uncertainty, tables, and code. Compaction does not require retaining source attribution or provenance metadata.

For a replacement, the primary explicitly chooses the final target content and every old filename-ID to new filename-ID mapping. The worker ensures targets exist, then uses `pcw_merge` to save targets, preserve or explicitly set outgoing links, rewrite incoming links, remove duplicates and self-links, and only then remove replaced materials and their current search rows. `pcw_reassign` changes exact navigation only; partial extraction is not a global redirect. `pcw_delete` removes incoming links, material, and current search rows, not linked targets or their prose. Report any `partial` response with applied effects.

## Current and checkpoint

Current is readable Markdown with exactly these task sections: `# Goal`, `# Constraints`, `# Completion`, `# Current step`, and `# Blocker`. `pcw_current_set` preserves unspecified values. A worker writes it from the primary's decision; PCW does not decide the goal or next action. Update step or blocker when the primary changes the next action or an obstacle changes. Goal, constraints, and completion change only when the user's request changes. Do not turn Current into a return log or rewrite it after every worker result.

Each section written by PCW includes an HTML comment `<!-- pcw-current-length: N -->` recording the number of characters in its value. The value remains visible Markdown; the marker preserves exact text when a value itself contains section headings, code, or trailing newlines. Use `pcw_current_set` to keep these lengths consistent.

Unless the user forbids a local memory commit, a worker calls `pcw_checkpoint` for exactly the durable Current and knowledge paths changed by the request. A prohibition of, or lack of authority for, a source-project commit does not prohibit this separate local memory checkpoint. A temporary PCW work location still uses Current and knowledge with their required consolidation and local history; the location is not a user prohibition of those operations. Include both old and new paths for a rename and affected navigation files. Preserve unrelated changes. A memory checkpoint is not authority for source commits, pushes, or external changes. `pcw_restore` needs an explicit authorized target and exact paths; `pcw_reconcile` makes derived search state match externally restored or edited knowledge.

# Memory operations

Consult this reference when its rules are needed; do not retrieve it before each operation. All MCP calls receive an existing absolute `work_root` and semantic `workspace`; durable storage is `<work-root>/.pcw/<workspace>/`. The primary alone owns memory operations.

## Read before deciding

Use `pcw_startup` once at start or recovery for the current request, outstanding work, pending IDs, Current and reusable profiles. Completed assignment history is available separately through `pcw_task_status`; do not load it unless needed. Search relevant knowledge, read full selected materials with `pcw_read_many` or `pcw_read`, and navigate links. Use `pcw_list` when useful. Empty search output does not prove knowledge is absent or fresh. Refresh specific state when it changes instead of repeating startup calls or retrieving the same profiles again.

The primary does not inspect real project sources, diffs, logs or external services itself while the skill is active. Native capability descriptors and necessary environment configuration used to build the tools map are a limited primary responsibility, not project-source research.

Knowledge is free Markdown: prose, conditions, uncertainty, tables and code are all valid. `links` is a directional list of exact filename-IDs. Preserve meaningful navigation without inventing relation types, explanatory metadata or mandatory mirror edges. The body carries claims and conditions. Batch independent link changes through `pcw_links_many(changes=[{source_id, add, remove}, ...])`.

## Filename IDs and legacy memory

MCP generates each new filename-ID (`<generated-id>.md`). Creation accepts content, not an agent-chosen filename. The filename is the material ID; its path is separate. A substantive return can have several independently meaningful materials, all accounted for under its assignment. Semantic helper assignments create no knowledge IDs.

Store returned IDs for reading, updates, links and preparation. Existing descriptive filenames remain readable until explicitly requested migration. `pcw_rename` moves a material while preserving its basename and links; it updates search paths without preparing unchanged text and rejects a different basename or occupied destination.

Migration is explicit. Establish the filename mapping, rewrite exact legacy links, preserve body text and useful metadata, tables, code and relation prose, and reconcile search addresses. Do not re-embed unchanged content for a filename or link change. Do not migrate or normalize legacy knowledge merely because ordinary work encounters it.

## Save substantive returns

On a worker's substantive work/check return, the primary immediately divides its text into large, independently useful topic materials and links the related materials. Preserve actual facts, conditions, implementation detail, uncertainty, code and tables. Choose boundaries by meaning, not mechanically by heading or fixed size. A short coherent return may stay one material. Do not require an additional giant unmodified raw file.

Save the primary's chosen blocks together:

```text
pcw_result_store(work_root, workspace, assignment_id, executor_session_id, blocks, links)
```

`blocks` is an array of Markdown bodies. MCP generates the filenames and UTC `saved_at` metadata for every block. Use the actual bound executor session, never an invented substitute. Control state records all blocks and their assignment/session/time so the whole substantive return remains accountable.

`links` contains primary-chosen sets such as `[{"block": 1, "to_blocks": [2], "to_materials": ["existing-id.md"]}]`. Block numbers start at 1; existing targets must exist. Bodies, link additions and actual disk read-back are one operation. Inspect the returned `materials` and `read_back_verified`, then explicitly assess with `pcw_result_assess`. A partial response is unfinished and must be repaired. Reuse returned `split_sources`; no extra read/link/prepare calls are necessary for this unchanged state. The lower-level `pcw_save_result_blocks`, `pcw_read_many` and `pcw_links_many` remain available for recovery or individual operations. Saving and read-back do not prove factual correctness.

An exact repeated save is idempotent. A different payload conflicts rather than silently replacing recorded content. For an explicit correction of the same assignment's same-count blocks, pass `expected_previous_revisions` from the previous read. Repartitioning stored topics is a primary consolidation operation, not a save retry. An unresolved conflict or failed save/read blocks acceptance.

Incomplete/error returns, task-status reports and operational verification belong to `pcw_return_record`, not knowledge. Supply the actual return, its status, why it belongs in control and its `missing` list. For incomplete/error status, list concrete outstanding requirements; prepare a continuation without accepting the incomplete work. When its complete result is accepted, name the earlier assignment in `assessment.resolves`. A completed control return has an empty missing list and still needs explicit assessment. A control-only factual check is referenced at finish by assignment and executor, without material_name. Control returns are immutable; corrections use a continuation. A return with reusable new facts instead uses topic storage; do not duplicate the entire artifact and verification history merely for accounting.

The primary alone calls `pcw_create`, `pcw_update`, `pcw_links`, `pcw_links_many`, `pcw_merge`, `pcw_reassign`, `pcw_rename`, `pcw_delete`, `pcw_current_set`, authorized `pcw_checkpoint` and `pcw_restore`. PCW does not infer consolidation decisions from similarity.

Saved bodies remain readable while `pending_preparation`. After topic division, reuse returned `split_sources`, or obtain current revisions with `pcw_prepare_many` if needed, and use a narrow helper for embedding boundaries within each material; see [Prepare search](prepare-search.md). Failed preparation leaves honest pending state. Links-only changes and moves do not prepare or embed text.

## Incorrect knowledge and consolidation

Record factual discrepancies through a `needs_attention` assessment. Use `affected_material_ids` for the incorrect active materials; omission captures all saved blocks of that return. Known incorrect active knowledge must be updated or replaced, not merely accompanied by a linked clarification. An accepted clarification/check names earlier assignment IDs in `resolves`; the discrepancy remains until every captured body is corrected or replaced. Invalidated, uncorrected bodies are excluded from active search; a direct read warns about their state. Exclusion prevents reuse while correction is outstanding; it does not complete the task.

Consolidate actual duplicate content rather than adding a summary beside it. Preserve useful implementation details, conditions, exceptions, uncertainty, tables and code. Initial return accounting includes assignment, executor and save time; later consolidation does not require preserving source attribution or provenance metadata in the resulting bodies.

For replacement, explicitly choose final target content and every old-to-new filename-ID mapping. Ensure targets exist, then use `pcw_merge` to save targets, preserve or explicitly set outgoing links, rewrite incoming links, remove duplicates/self-links and remove replaced materials and their active search rows. `pcw_reassign` changes exact navigation only; partial extraction is not a global redirect. `pcw_delete` removes incoming links, the material and current search rows, not linked targets or their prose. Inspect and report any `partial` response and its applied effects.

## Current and checkpoint

Current is readable Markdown with exactly these task sections: `# Goal`, `# Constraints`, `# Completion`, `# Current step`, and `# Blocker`. `pcw_current_set` is called by the primary. With an active task it takes goal, constraints and completion from the registered request. Omitted step/blocker stay unchanged. Use an empty blocker string for no blocker; do not write "None.". For a user-authorized change to the request use `pcw_task_update` with its revision and reason, then synchronize Current. PCW does not decide task meaning or the next action. Update step or blocker when the primary changes the next action or an obstacle changes. Goal, constraints, and completion change only when the user's request changes. Do not turn Current into a return log or rewrite it after every worker result.

Each section written by PCW includes an HTML comment `<!-- pcw-current-length: N -->` recording the number of characters in its value. The value remains visible Markdown; the marker preserves exact text when a value itself contains section headings, code, or trailing newlines. Use `pcw_current_set` to keep these lengths consistent.

`pcw_current_set` reads back the actual written file and checks all fields before returning them. Do not immediately call `pcw_current_get` to repeat that verification.

An exact repeat of `pcw_checkpoint` for already committed, unchanged paths returns the existing commit with `already_checkpointed: true`; it does not create another commit or report an error merely because nothing changed.

The primary calls `pcw_checkpoint` only with actual authority recorded as policy `required` and its reason. The default is `not_authorized`; use `forbidden` for an actual prohibition. Respect an applicable instruction requiring explicit permission for commits. A context request alone must not override such a requirement. Lack of authority is not a user prohibition and does not create an unfinished required checkpoint. Include only exact request-owned durable paths, old and new paths for a move, and affected navigation files. Preserve unrelated changes. A memory checkpoint does not authorize source commits or push.

`pcw_restore` requires an authorized target and exact paths. `pcw_reconcile` makes derived search state match restored or externally edited memory. Existing memory is not migrated, deleted or cleaned merely because the plugin was upgraded.

# Memory operations

Read for workspace selection, durable changes, or recovery. All MCP tools receive `work_root` as an existing absolute project directory and `workspace` as one semantic directory name. Their storage is confined to `<work-root>/.pcw/<workspace>/`. Tool schemas give the full argument types.

## Select and open

Select the exact workspace named by the user, or the only existing candidate unambiguously matching the request. Inspect memory coordinates only inside the chosen project's `.pcw/`; do not search the home directory or select from a stale next action. Ask only when the remaining ambiguity changes the workspace or task.

`pcw_status` opens the workspace and initializes missing knowledge and local runtime directories. Call it for a missing workspace only when creation is authorized. It returns material count, `pending_preparation`, unregistered legacy files, and active connection, table, and search settings. It does not load the embedding model or create a Git commit. The first checkpoint initializes a separate memory Git repository. Keep the parent's `.pcw/` outside source Git; if its ignore rule is missing, delegate only that setup change under the context-creation request.

`pcw_current_get` returns the saved task fields. Read them into the primary's active context. `pcw_list(offset=0, limit=50)` returns paginated material metadata and pending status without loading every material body; its maximum page size is 100. Use listing for exact ID/path resolution or migration, not as an instruction to read all knowledge. Status, search, and reconciliation bound their pending-ID lists and include counts; a returned list may not enumerate all pending materials.

## Read and search

`pcw_search(query)` returns selected IDs, current workspace-relative paths, distances, and pending or unregistered materials. Its optional `N`, `d_max`, `min_jump`, and `multiplier` override one query's cutoff. Defaults are `20`, `0.8`, `0.02`, and `3` with cosine distance: engineering starting points, not calibrated relevance guarantees. Search settings and calibration status appear in results.

`pcw_read(material_id)` returns the full body, exact ID, path, `links`, and revision. Read useful linked IDs directly without another vector query. Unknown IDs produce an error, not a nearest-match substitution. Vector similarity and navigation do not establish factual freshness or semantic equivalence.

## Save materials

- `pcw_create(path, content, links=[])` creates a new material and allocates its permanent ID. Here `path` is relative to `knowledge/`, such as `architecture.md`. Supply body text without frontmatter. Existing targets are not overwritten.
- `pcw_update(material_id, content, expected_revision)` replaces the primary-authored body while preserving its ID and navigation. Pass the revision already returned by the read when available; a stale revision reports a conflict.
- `pcw_rename(material_id, path)` changes the file address without changing the ID or re-embedding its unchanged body. The destination must be absent.

Content writes become visible as saved knowledge immediately. Changed nonempty bodies are `pending_preparation`; their old search rows are removed. Complete [Prepare search](prepare-search.md) before claiming the material is indexed. New or changed material remains readable when preparation or embedding fails. Do not overwrite it with a fabricated successful result.

The runtime stores `id` and `links` in YAML frontmatter and preserves other existing metadata. Bodies may freely contain prose, tables, and code. The primary chooses their meaning and organization; there is no obligatory object/fact schema or subagent report template.

## Navigation, merge, and deletion

`pcw_links(source_id, add=[], remove=[])` edits only exact navigation IDs. It preserves other links, removes duplicates, prevents self-links, and rejects unknown added IDs. Navigation is directional; no mirror link, relation type, or description is required. Links-only edits do not prepare or embed content.

For full replacement, the primary writes the final content and explicitly chooses every old-ID to target-ID mapping:

1. Ensure each target already exists; use `pcw_create` first for a new target.
2. Call `pcw_merge(materials, replacements)`. `materials` contains one `{id, content}` entry for each target; optional `links` supplies an explicit final list. `replacements` maps each removed ID to its target ID.
3. The tool saves final targets, unions outgoing links when no final list was supplied, rewrites incoming links, deduplicates and removes self-links, and then deletes replaced files and search rows. Finish preparation for changed target bodies.

`pcw_reassign(mapping)` performs only exact navigation replacement; it does not merge content or delete materials. Use it when navigation needs changing independently. Partial extraction while the original material remains does not imply global reassignment. If different incoming links need different targets, edit their source lists explicitly; do not ask the runtime to infer a destination.

`pcw_delete(material_id)` removes incoming links, then the material and its search rows. It does not delete linked targets or rewrite their prose. A deletion request includes removal of pointers to that material; deciding to discard knowledge remains the primary's responsibility. Retired IDs are not reused, and persistent redirect files are not created.

These multi-file operations report `partial` with applied changes when interrupted by an error. Account for those effects before continuing. Do not report an entire merge or deletion as complete when the tool reports partial failure. Link maintenance is mechanical and does not trigger a semantic review of all neighbors.

## Current

`pcw_current_set` accepts strings `goal`, `constraints`, `completion`, `step`, and `blocker`. Unspecified fields preserve their previous values. Goal, constraints, and completion express the user's task; supporting facts do not expand them. The primary updates step/blocker when its chosen next action or obstacle changes, not for every tool call.

Keep Current compact and load it at task start or recovery. It is neither the complete plan history nor a copy of knowledge. A knowledge-only request does not replace the current task. The runtime saves the primary's fields; it does not determine the next action.

## Checkpoint and restore

Unless the user forbids the local memory commit, call `pcw_checkpoint(paths, message)` for exactly the durable files changed by this request. These paths are relative to the workspace, such as `current.md` or `knowledge/architecture.md`; include both addresses for a rename and all affected navigation files. Resolve IDs to paths with existing metadata or `pcw_list` without rereading bodies for acceptance. Preserve unrelated staged and unstaged work. Never use broad staging or put runtime state, model caches, or credentials into Git.

A checkpoint concerns the selected memory repository only. Source commits and every push require the user's corresponding authority. Report actual checkpoint errors and uncommitted changes; do not introduce a routine review or validation phase.

For an authorized rollback, call `pcw_restore(commit, paths)` with the exact selected durable paths after accounting for uncommitted work that the restore would replace. It restores those worktree files and reconciles derived search data. It does not roll back source changes or external side effects. `pcw_reconcile` also reconciles externally restored or edited knowledge, removing stale rows and updating paths. Complete preparation for the returned pending IDs; no old vector table is treated as a history archive.

## Legacy memory

`pcw_status` and `pcw_list` identify files lacking recognized metadata as unregistered. Under an explicit import or migration request, `pcw_adopt(path)` preserves existing IDs and provenance or allocates an ID when missing, then adds/normalizes the navigation list. It does not infer links from wiki syntax or rewrite old relation prose. The primary deliberately converts useful filename-based links to target IDs and preserves any meaningful claims, conditions, and sources in the body. An old `index.md` is an ordinary material if adopted, not a mandatory global reading entrypoint.

For a legacy Current, `pcw_current_get` returns `legacy_content` and `requires_explicit_replacement`. Read that content and preserve its still-applicable user constraints. Replacement requires explicitly supplying goal, constraints, completion, and `replace_legacy: true`; normal step updates cannot silently erase the legacy task.

Missing preparation after migration or restoration is visible state. It is not evidence that the underlying knowledge was deleted, and it does not authorize re-executing the saved source task.

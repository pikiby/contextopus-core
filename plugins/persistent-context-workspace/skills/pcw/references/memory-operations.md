# Memory operations

Knowledge files are ordinary Markdown topic materials. The primary owns their meaning and all PCW changes. MCP chooses new filename-IDs; preserve them when updating a topic. Include useful source coordinates and verification limits in the body. Own observations and optional worker findings use the same save operations without an executor ID.

- `pcw_create(content, links)`: save a complete topic body and automatically index it.
- `pcw_update(material_id, content, expected_revision)`: replace its complete body with revision protection.
- `pcw_read` / `pcw_read_many`: obtain selected complete bodies and exact navigation links.
- `pcw_links` / `pcw_links_many`: apply explicitly chosen directed links. No mandatory reciprocal links or embedding calls.
- `pcw_rename`: move inside knowledge while preserving the filename-ID.
- `pcw_merge`: provide final surviving bodies and exact old-to-survivor replacements. It redirects all incoming links before deleting replaced files and automatically indexes changed survivors.
- `pcw_delete`: remove the selected material and incoming navigation links; neighbors remain.
- `pcw_reassign`: apply an explicit link replacement without changing bodies or deleting files.

Consolidate when useful duplication is observed. Preserve exceptions, conditions, versions and uncertainty. Do not impose a fixed file size or one file per sentence. Token windows are derived search representations, not replacements for topic organization.

A write receipt verifies disk content and distinguishes saved text from completed indexing. If indexing fails, retain the returned ID and use `pcw_reconcile`; do not create a duplicate. For partial merge/link/delete operations inspect applied changes and retry only unfinished work. No technical result report belongs in knowledge.

Current has Goal, Constraints, Completion, Current step and Blocker. The primary updates supplied fields directly; old assignment ledgers do not constrain it. Legacy unrecognized Current content requires an explicit replacement after reading it.

`pcw_checkpoint` and `pcw_restore` affect only explicitly listed memory Markdown paths in a separate local Git repository. They require actual authorization. Restore automatically reindexes changed content. Source repositories and remote publication are outside these operations.

## Existing workspaces

Opening an older workspace preserves knowledge, links, Current and historical control files. The derived pre-0.8 search table is replaced with a token-window table and existing materials become pending. Call `pcw_reconcile` once to index them. Local Qwen inherits default chunking; a legacy remote configuration requires an explicitly compatible tokenizer via `pcw_switch_embeddings`.

Known incorrect revisions recorded by an old ledger remain warned and excluded from search until their bodies are corrected. The old task, environment and assignment workflow is not resumed.

Legacy YAML UUID links remain readable through filename identity translation; `pcw_migrate_legacy_ids` changes those files only when explicitly requested. Missing runtime storage needs `pcw_recover_workspace`; missing knowledge requires restoring it or explicit authorization to recreate an empty directory.

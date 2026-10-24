# Shared instruction documents

Core owns instruction sources in `root/core/instructions/`. Each UTF-8 Markdown
file has YAML metadata followed by the complete instruction body:

```markdown
---
id: workspace.project-update
type: instruction
title: Project update
description: Rules for updating project records
config:
  approval: explicit
instructions:
  common: '[[common]]'
---
Read the current project record before updating it.
```

`id` is stable across moves; `type` is `instruction`. `title` and `description`
are optional text fields. Technical settings belong in YAML (`config` is a
mapping). The body is free-form instruction text and is returned without
rewriting. A body can itself contain Markdown front matter. Ordinary body links
do not add dependencies: only the YAML `instructions` mapping does.

Root and module documents select these files with a role-to-wikilink mapping,
for example `instructions: {workspace: '[[workspace.project-update]]'}` in a
Workspace `Context.md`. Core does not infer roles or generate instruction bodies.

## Operations

All interfaces use the same Core operation registry:

| Operation | Kind | Arguments | Result |
| --- | --- | --- | --- |
| `core.instructions_list` | query | none | `instructions`: compact ID, type, title, description, path, revision records |
| `core.instructions_read` | query | `reference` | one full record |
| `core.instructions_resolve` | query | `references: string[]` | `instructions`: full records in dependency order; aggregate `revision` |
| `core.instructions_save` | execute | `path`, `metadata`, `content`, optional `expected_revision` | full saved record and `index` status |
| `core.instructions_reconcile` | execute | none | index reconciliation counts and status |
| `core.instructions_search` | query | `query`, optional `limit`, `selection`, `output` | standard shared RAG result restricted to `core/instructions` |

A full record has `id`, `type`, `title`, `description`, `path`, `content`,
`revision`, and `metadata`. `path` is relative to `core/instructions`.
`content` is the exact body; `revision` is SHA-256 of the complete file, including
YAML. `read` accepts a stable ID, exact relative path, unique filename stem,
or a wikilink with an optional display label. Missing reads raise
`FileNotFoundError`; ambiguous references, duplicate IDs, invalid YAML, and
dependency cycles fail closed. Resolution returns every dependency once,
before its dependants. It uses exact references and never semantic similarity.

`expected_revision: null` creates a new file only. Replacing an existing file
requires its current full-file revision, so concurrent YAML changes conflict
as well as body changes. Writes use a flushed temporary file and atomic rename
under the root guard. Paths must be relative Markdown paths; hidden files,
traversal, symlinks, and duplicate identities are rejected.

Saving Markdown does not require an embedding model. The result includes
`index: {status: pending}` if no index is configured or indexing fails, with
`error` when available. The source remains saved and readable; an explicit
reconcile retries the derived index. Saving and reconciling require an explicitly
configured embedding profile before indexing; they never select or download a
default model. A complete validated scan is required
before reconciliation can remove stale index entries. Search excludes deleted
instruction sources; unchanged metadata does not require re-embedding.

Python callers use
`contextopus.core.documents.instructions.InstructionLibrary(layout, index=None)`
with the same method arguments. Constructing the library, reading, listing, and
resolving do not create source directories or source files. Source files are
authoritative; search is discovery, while executing required rules uses `resolve`.
Public operations retain the common operation journal, which may write analytics
records. Reconciliation refuses a missing source directory rather than treating
it as an empty collection; delete individual source files inside an existing
directory to make intentional removals eligible for reconciliation.

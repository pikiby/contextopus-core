# Shared file documents — local implementation

The `contextopus.core.documents` Python API is the common foundation for
file-backed module records. Core exposes it to child modules through
`core.documents` and stores shared instruction sources through
`core.instructions`. Agents uses Markdown profiles and teams; Workspace uses
root `Context.md` with links to shared instructions. Existing installations need
their explicit module migrations before using these formats.

## Source contract

`scan_markdown(root, module=..., collection=..., validate=...)` reads one declared
directory. Markdown bodies become indexed text; YAML remains metadata. Every
document requires a stable text `id` and `type`. A module validator checks its
own configuration. Hidden directories are excluded. Duplicate identities,
malformed YAML, unreadable directories, symlinks and observed concurrent changes
abort the scan. A missing directory is an error, not an empty collection.

`SourceSnapshot` also accepts documents from non-Markdown adapters. Its default
`complete=False` allows bounded incremental updates without inferring deletions.
Only a successful complete snapshot can identify removed objects. Explicit scan
errors invalidate the entire plan. Module/collection boundaries are checked.

`plan(snapshot, previous)` returns upserts, metadata/path refreshes, deletions and
unchanged identities. SQL adapters can apply these effects to their derived
catalog. `reconcile_index(index, snapshot)` applies them to the shared RAG;
metadata changes and moves do not recompute embeddings. Additions and updates
run before deletions. Failed writes are retried against a fresh snapshot; there
is no claimed atomic transaction across the module SQL database and RAG.

The source owner must serialize capture and application with its own writes.
External editors cannot be locked by this API. Revalidate source state before
applying destructive effects. A scan is not authorization to delete source
files, rewrite incoming links or remove native agent definitions.

## Instruction links

The accepted connection format is a YAML mapping:

```yaml
instructions:
  workspace: "[[project-work-rules]]"
  agents: "[[development-agent-rules]]"
```

`resolve_required(documents, references)` resolves these explicit wikilinks by
stable ID, relative path or unique file stem, including optional display labels.
Targets must have `type: instruction`. It returns whole documents once each,
dependencies first, and rejects missing/ambiguous targets or cycles. It expands
only an instruction document's `instructions` mapping, not ordinary `links`.
Workspace evidence-source retrieval remains its existing separate procedure.

## Module access

Child modules use `core.documents.prepare`, `scan`, `write`, `delete`, and `plan`.
Paths are relative to their own `modules/<id>/data/`; access cannot escape that
directory. Writes and deletions require the current full-file revision. Creation
requires an absent file. Short per-module locks serialize managed writes;
external edits are detected by revision checks, not prevented by an OS sandbox.

The shared reconciliation plan does not write SQL or RAG itself. The module
applies its derived catalog changes and calls Core RAG operations.
`core.rag.update_document` refreshes metadata and location only when the indexed
text revision matches; changed text needs normal indexing. Instruction library
operations and dependency resolution are described in
[Shared instruction documents](../instruction-library.md).

Session Search retains its durable incremental ingestion. The common document
contract does not require a full transcript scan at startup. Local source tests
do not establish that an installed root has been migrated; verify installation
and migration separately.

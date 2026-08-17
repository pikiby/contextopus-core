---
name: pcw-resolve-workspace
description: Resolve the exact .pcw memory workspace for one semantic subproject without changing files. Internal subskill; use only when loaded by persistent-context-workspace at the start of a cycle or after the user changes project scope.
---

# Resolve workspace

Select exactly one memory path without writing anything.

## Preconditions

- The active `persistent-context-workspace` contract loaded this file.
- A work path, current request, and optional subproject name are available.

## Inputs

- An absolute or resolvable `work_root` path.
- The verbatim current user request.
- An optional `subproject_hint`.
- Existing `<work-root>/.pcw/*/current.md` candidates, if already discovered.

## Procedure

1. Canonicalize `work_root` read-only and verify that it exists.
2. Search for `.pcw/` only inside that root; never scan the entire home directory for memory.
3. If the user named a subproject, normalize it to a safe slug and select only that slug.
4. If no name was provided:
   - select the only existing candidate that clearly belongs to the current project;
   - return `ambiguous_workspace` when multiple candidates remain possible;
   - when no candidate exists, propose a slug from the stable semantic purpose and return `exists: false`.
5. Resolve links and require the final path to remain inside `<work-root>/.pcw/`.
6. Do not create `.pcw`, directories, files, or a Git repository.

Never select a workspace from an old next action or incidental word similarity in chat history.

## Output

Return the standard envelope plus:

```yaml
resolved:
  work_root: <absolute-path>
  subproject: <slug>
  workspace: <absolute-path>/.pcw/<slug>
  exists: true | false
  basis: explicit | unique_existing | proposed_new
```

Set `output_state` to `workspace_resolved`.

## Blockers

- `work_root_missing`
- `ambiguous_workspace`
- `path_escapes_work_root`
- `insufficient_scope`

## Idempotency

Return the same path for identical inputs. Never rename an existing subproject or create a variant slug.

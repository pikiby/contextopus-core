# Resolve workspace

Select one memory path without writing files.

## Inputs

The current user request, an absolute or resolvable work root, and any explicit subproject identity.

## Procedure

1. Resolve the work root and look for memory only inside its `.pcw/` directory, never across the home directory.
2. An explicit workspace or subproject selects that exact target. Otherwise select the only existing candidate belonging unambiguously to this project and request.
3. When several candidates remain possible, return `ambiguous_workspace`. When none exists, propose a stable semantic slug and return `exists: false`.
4. The selected canonical workspace belongs inside `<work-root>/.pcw/`. A missing root or escaping path returns `work_root_missing` or `path_escapes_work_root`.
5. Do not create, rename, or replace any directory. The context-editing entrypoint owns authorized creation.

Do not select a workspace from an old next action or incidental similarity in conversation.

## Output

Return the shared operation result with `output_state: workspace_resolved` and:

```yaml
resolved:
  work_root: <absolute-path>
  subproject: <slug>
  workspace: <absolute-path>/.pcw/<slug>
  exists: true | false
  basis: explicit | unique_existing | proposed_new
```

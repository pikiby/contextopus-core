---
name: pcw-open-cycle
description: Create or recover one Persistent Context Workspace cycle after its workspace path has been resolved. Internal subskill; use only when loaded by persistent-context-workspace after pcw-resolve-workspace or while resuming an interrupted cycle.
---

# Open cycle

Create the minimal structure for new memory or recover exactly one unfinished cycle.

## Preconditions

- A successful `pcw-resolve-workspace` receipt is available.
- The path is inside the resolved `<work-root>/.pcw/`.
- No other agent is writing to this workspace concurrently.

## Inputs

- The `resolved` object from the previous operation.
- The verbatim user request.
- Source roots.
- An optional `cycle_id` for recovery.
- A `current.md` budget, defaulting to 3,000 tokens.

## Procedure

1. If the workspace does not exist:
   - create `<work-root>/.pcw/.gitignore` that ignores everything except itself;
   - create `current.md` with only `# Current`, `# Pinned`, and `# References`;
   - create `knowledge/index.md`, `tmp/`, and a workspace `.gitignore` containing `tmp/`;
   - initialize local Git inside the workspace without committing.
2. Inspect existing `tmp/<cycle-id>/manifest.md` files.
3. If exactly one cycle is not `closed` and has `absorbed: false`, do not create another; return `recovery_required` with its id.
4. If multiple unfinished cycles exist, return `multiple_open_cycles`.
5. Otherwise create `tmp/<cycle-id>/` with `findings/`, `work/`, `receipts/`, and a canonical manifest.
6. Use a UTC id shaped as `YYYYMMDDTHHMMSSZ-<request-slug>`; recover an existing exact id rather than overwriting it.
7. Do not change existing `current.md` or `knowledge/` content.

## Output

For a new or resumed working cycle, return `output_state: cycle_open`. For unabsorbed earlier work, return:

```yaml
status: ok
output_state: recovery_required
recovery_cycle_id: <id>
```

List every created artifact.

## Blockers

- `multiple_open_cycles`
- `workspace_shape_invalid`
- `concurrent_writer_detected`
- `path_escapes_workspace`
- `git_initialization_failed`

## Idempotency

A repeated call must not create a second cycle, reset a manifest, or overwrite memory. Treat an existing valid structure as a successful no-op.

# Open cycle

Create the minimal structure for new memory or recover exactly one unfinished transaction.

## Preconditions

- A successful `pcw-resolve-workspace` receipt is available.
- The path is inside the resolved `<work-root>/.pcw/`.
- No other agent is writing to this workspace concurrently.
- `entry_skill` is exactly `pcw` or `pcw-run`.

## Inputs

- The resolved workspace object.
- `entry_skill` and the verbatim user request.
- Source roots and optional recovery `cycle_id`.
- A `current.md` budget, defaulting to 3,000 tokens.

## Procedure

1. If the workspace does not exist, require `entry_skill: pcw` and explicit creation meaning in the request.
2. For permitted creation:
   - create `<work-root>/.pcw/.gitignore` that ignores everything except itself;
   - create `current.md` containing `# Current`, `Task: None`, `Status: closed`, and `# References`;
   - create `knowledge/index.md`, `tmp/`, and a workspace `.gitignore` containing `tmp/`;
   - initialize local Git inside the workspace without committing.
3. Inspect existing `tmp/<cycle-id>/manifest.md` files.
4. If exactly one cycle is not `closed` and has `absorbed: false`, return `recovery_required` with its id instead of creating another.
5. If multiple unfinished cycles exist, return `multiple_open_cycles`.
6. Otherwise create `tmp/<cycle-id>/` with `findings/`, `work/`, `receipts/`, and a canonical manifest including `entry_skill`.
7. Use a UTC id shaped as `YYYYMMDDTHHMMSSZ-<request-slug>`; recover an existing exact id rather than overwriting it.
8. Do not change existing `current.md` or `knowledge/` content.

## Output

For a new transaction, return `output_state: cycle_open`. For unabsorbed earlier work, return `output_state: recovery_required`, its cycle id, and every existing artifact.

## Blockers

- `creation_not_authorized`
- `multiple_open_cycles`
- `workspace_shape_invalid`
- `concurrent_writer_detected`
- `path_escapes_workspace`
- `git_initialization_failed`

## Idempotency

A repeated call must not create a second cycle, reset a manifest, or overwrite memory. Treat an existing valid structure as a successful no-op.

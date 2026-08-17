---
name: pcw-prune-tmp
description: Remove only the exact cycle tmp directory proven absorbed by a verified local memory checkpoint. Internal destructive subskill; use only when loaded by persistent-context-workspace with a successful pcw-checkpoint-memory receipt.
---

# Prune tmp

Remove one absorbed temporary cycle by exact path after a verifiable checkpoint.

## Preconditions

- The receipt contains `checkpoint_status: created` and an actual commit id.
- That commit is the current memory HEAD.
- The receipt matches the same `workspace` and `cycle_id`.
- Validation covered every result in the removable cycle.

## Inputs

- The checkpoint receipt.
- The absolute workspace.
- Exactly one `cycle_id`.
- The exact `<workspace>/tmp/<cycle-id>` path.

## Procedure

1. Canonicalize the workspace and cycle path.
2. Require the cycle path to be a direct child of `<workspace>/tmp/`, not a symlink, and free of `..`.
3. Cross-check the manifest, promotion manifest, and checkpoint receipt.
4. Verify that no unpromoted `result_id`, conflict, or partial material remains.
5. Without requesting separate permission, remove only that exact cycle directory unless the user explicitly forbade the transaction; never use a wildcard, recursive parent path, or general-purpose environment variable.
6. Verify that `current.md`, `knowledge/`, and other cycle directories did not change.
7. If the exact directory is already absent, treat the operation as a successful no-op only when the checkpoint receipt matches.

## Output

Return `output_state: cycle_closed`, the exact removed path, commit id, and `pruned: true | already_absent`.

## Blockers

- `checkpoint_missing`
- `checkpoint_not_head`
- `cycle_mismatch`
- `path_not_exact_child`
- `unabsorbed_material`
- `unresolved_conflict`
- `user_forbidden`

## Idempotency

After removal, a repeated call with the same checkpoint receipt returns `already_absent`. Never touch a different directory with a similar name.

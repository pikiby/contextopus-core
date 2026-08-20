# Checkpoint memory

Commit only validated durable memory and never include `tmp/`.

## Preconditions

- A fresh `status: ok`, `output_state: validated` result exists for the same workspace and cycle.
- That validation confirms the Task lock, requirement provenance, and, for a run, semantic acceptance of the complete target.
- No writes occurred between validation and this operation.
- The workspace is its own local Git repository.

## Inputs

- The validation result.
- `workspace` and `cycle_id`.
- Any explicit user prohibition of the local memory transaction.
- A concise semantic description of the memory change.

## Procedure

1. Reject any blocked validation, mismatched cycle, missing semantic-acceptance check, or result without `output_state: validated`.
2. Read Git status again and compare it with the validation result.
3. Show a diff limited to `current.md`, `knowledge/`, and the permitted `.gitignore`.
4. Only when the user explicitly forbade this local memory transaction, stage nothing and return `user_forbidden`.
5. Otherwise stage only explicitly validated paths. Never use a broad glob and never stage `tmp/`.
6. Check the staged diff for secrets, conflict markers, and whitespace errors.
7. Create one local commit describing the semantic memory change.
8. Read the actual commit id and confirm that `tmp/` remains untracked.
9. Never push.

## Output

When explicitly forbidden, return:

```yaml
status: blocked
output_state: validated
reason: user_forbidden
```

After commit, return `output_state: checkpointed`, `checkpoint_status: created`, the commit id, and the exact committed paths.

## Blockers

- `user_forbidden`
- `validation_failed`
- `semantic_acceptance_missing`
- `cycle_mismatch`
- `validation_stale`
- `unexpected_diff`
- `tmp_staged`
- `secret_detected`
- `commit_failed`

## Idempotency

If the same validated tree is already HEAD, return its commit id and do not create an empty commit. Never create a second checkpoint for the same state.

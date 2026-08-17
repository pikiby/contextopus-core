---
name: pcw-checkpoint-memory
description: Prepare a reviewable memory diff and create a local Git checkpoint only after successful validation and explicit commit authorization. Internal subskill; use only when loaded by persistent-context-workspace for a validated cycle. Never push.
---

# Checkpoint memory

Commit only validated durable memory and never include `tmp/`.

## Preconditions

- A fresh successful `pcw-validate-memory` result exists.
- No writes occurred between validation and this operation.
- The workspace is its own local Git repository.

## Inputs

- The validation result.
- `workspace` and `cycle_id`.
- An explicit response authorizing or withholding commit.
- A concise semantic description of the memory change.

## Procedure

1. Read Git status again and compare it with the validation result.
2. Show a diff limited to `current.md`, `knowledge/`, and the permitted `.gitignore`.
3. Without explicit commit authorization:
   - stage nothing;
   - return `authorization_required`;
   - leave `tmp/` and the working tree otherwise unchanged.
4. With authorization, stage only explicitly validated paths. Never use a broad glob and never stage `tmp/`.
5. Check the staged diff for secrets, conflict markers, and whitespace errors.
6. Create one local commit describing the semantic memory change.
7. Read the actual commit id and confirm that `tmp/` remains untracked.
8. Never push.

## Output

Without authorization, return:

```yaml
status: blocked
output_state: authorization_required
reason: commit_authorization_required
```

After commit, return `output_state: checkpointed`, `checkpoint_status: created`, the commit id, and the exact committed paths.

## Blockers

- `commit_authorization_required`
- `validation_stale`
- `unexpected_diff`
- `tmp_staged`
- `secret_detected`
- `commit_failed`

## Idempotency

If the same validated tree is already HEAD, return its commit id and do not create an empty commit. Never create a second checkpoint for the same state.

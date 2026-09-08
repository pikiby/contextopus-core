# Checkpoint memory

Save this request's durable memory changes as a local Git commit.

## Inputs

The selected memory repository, exact durable paths changed by this request, a concise description, and any explicit prohibition of the local memory commit.

## Procedure

1. If the user forbids the local memory commit, leave the edits uncommitted and return `checkpoint_status: user_forbidden`.
2. Stage only the exact request-owned paths under Current, knowledge, and the permitted workspace ignore file. Do not use broad staging, include unrelated staged changes, or overwrite pre-existing edits. If ownership is unclear, return `needs_input`.
3. Commit those paths locally. If this request produced no change, create no empty commit.
4. Return the commit id reported by Git, or the actual error when the command fails. Do not add a rereading, diff-review, comparison, test, or acceptance phase before or after the commit.
5. Never push through this operation. Source commits and pushes remain separate user-authorized actions.

## Output

Return `output_state: checkpointed` with `checkpoint_status: created | unchanged`, the committed paths, and the commit id when available. A user-forbidden commit returns `output_state: memory_updated` with `checkpoint_status: user_forbidden`; the edits remain uncommitted. A failed commit returns `status: blocked` and its error.

# State machine

## Transition invariants

- Execute one transition at a time.
- On `blocked`, preserve the input state and every input artifact.
- Repeating an operation with identical inputs must be a no-op or return the same semantic result.
- An internal subskill never selects the following transition.

## Transitions

| Input state | Internal subskill | Postcondition |
|---|---|---|
| `unresolved` | `pcw-resolve-workspace` | `workspace_resolved` |
| `workspace_resolved` | `pcw-open-cycle` | `cycle_open` or `recovery_required` |
| `cycle_open` | `pcw-inspect-source` | `source_inspected` |
| `source_inspected` with `decision: map` | `pcw-map-source` | `source_mapped` |
| `source_inspected` with `decision: direct` | agent work | `working` |
| `source_mapped` | Reader or Worker activity | `working` |
| `working` | `pcw-record-result` | `working` with one new accepted result |
| `cycle_open` or `working` | `pcw-promote-knowledge` | `knowledge_promoted` |
| `knowledge_promoted` | `pcw-compact-current` | `current_compacted` |
| `current_compacted` | `pcw-validate-memory` | `validated` or the same state with `blocked` |
| `validated` | `pcw-checkpoint-memory` | `checkpointed` or `authorization_required` |
| `checkpointed` | `pcw-prune-tmp` | `cycle_closed` |

`recovery_required` reuses the existing cycle and resumes at `pcw-promote-knowledge`. Do not create a new cycle before reaching `cycle_closed`.

## Repeated calls

- `pcw-resolve-workspace`: return the same resolved path.
- `pcw-open-cycle`: recover the existing `cycle_id`; never create a second cycle.
- `pcw-record-result`: same id and content is a no-op; different content is `blocked`.
- `pcw-promote-knowledge`: do not create duplicate records, relations, or manifest entries.
- `pcw-compact-current`: identical snapshot and promotion manifest produce identical text.
- `pcw-validate-memory`: never change the file system.
- `pcw-checkpoint-memory`: return an existing checkpoint for the same validated tree.
- `pcw-prune-tmp`: an already absent exact cycle directory is a successful no-op.

## Recovery

Derive the last completed operation from files, Git, and the manifest, never from chat history. If the manifest and actual artifacts disagree, return `blocked: state_mismatch` and preserve both for diagnosis.

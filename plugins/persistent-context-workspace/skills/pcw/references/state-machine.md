# State machine

## Entry skills

- `pcw` creates or updates durable knowledge and the persistent task-specific `current.md`; it never executes the source task.
- `pcw-run` executes an existing prepared `current.md` through a clean Controller and persists verified results; it never replans independently.

Both accept natural-language requests. Ask only when unresolved ambiguity would select a materially different workspace, context change, or execution target.

## Transition invariants

- Execute one internal operation at a time and read its exact reference first.
- On `blocked`, preserve the input state and every input artifact.
- Repeating an operation with identical inputs must be a no-op or return the same semantic result.
- An internal operation never selects the following transition.
- `pcw-run` never falls back from a clean Controller to the primary agent.

## Transitions

| Entry | Input state | Internal operation or activity | Postcondition |
|---|---|---|---|
| both | `unresolved` | `pcw-resolve-workspace` | `workspace_resolved` |
| `pcw` | `workspace_resolved` with existing memory | `pcw-query-context` | `context_selected` |
| `pcw` | `workspace_resolved` for new memory, or `context_selected` | `pcw-open-cycle` | `cycle_open` or `recovery_required` |
| `pcw` | `cycle_open` with source evidence scope | `pcw-inspect-source` | `source_inspected` |
| `pcw` | `source_inspected` with `decision: map` | `pcw-map-source` | `source_mapped` |
| `pcw` | `cycle_open`, `source_inspected`, or `source_mapped` | Reader or context-building activity | `working` |
| `pcw-run` | `workspace_resolved` with valid Current | `pcw-open-cycle` | `cycle_open` or `recovery_required` |
| `pcw-run` | `cycle_open` | clean Controller activity | `working` or `blocked` |
| both | `cycle_open` or `working` | `pcw-record-result` | `working` with one accepted result |
| both | `cycle_open` or `working` | `pcw-promote-knowledge` | `knowledge_promoted` |
| both | `knowledge_promoted` | `pcw-compact-current` | `current_compacted` |
| both | `current_compacted` | `pcw-validate-memory` | `validated` or the same state with `blocked` |
| both | `validated` | `pcw-checkpoint-memory` | `checkpointed` or `blocked` by explicit user prohibition |
| both | `checkpointed` | `pcw-prune-tmp` | `cycle_closed` |

`recovery_required` reuses the existing cycle and resumes from the last evidenced state. A blocked validation also remains in that cycle and returns to the earliest faulty operation; it never creates a correction request or cycle. Do not create a new cycle before reaching `cycle_closed`.

## Run isolation

The primary agent passes the clean Controller only the exact current run request, workspace and source roots, complete `current.md`, its knowledge links, referenced source coordinates, and current authority. The Controller reads Current first. It may ask Readers bounded questions that start from those links and follow relevant knowledge relations or primary coordinates, but retrieved detail cannot change the prepared task, scope, authority, user constraints, or plan. `context_insufficient`, `needs_input`, or broader authority returns control to the primary agent without execution beyond the supported boundary.

## Repeated calls

- `pcw-resolve-workspace`: return the same resolved path.
- `pcw-query-context`: remain read-only and select the same knowledge for equivalent inputs.
- `pcw-open-cycle`: recover the existing `cycle_id`; never create a second cycle.
- `pcw-record-result`: same id and content is a no-op; different content is `blocked`.
- `pcw-promote-knowledge`: do not duplicate objects, facts, relations, or manifest entries.
- `pcw-compact-current`: identical snapshot, user meaning, and promotion manifest produce identical Current.
- `pcw-validate-memory`: never change the file system; a failure stays `current_compacted` in the same cycle.
- `pcw-checkpoint-memory`: return an existing checkpoint for the same validated tree.
- `pcw-prune-tmp`: an already absent exact cycle directory is a successful no-op.

## Recovery

Derive the last completed operation from `tmp/`, durable files, Git, and receipts, never from chat history. If the manifest and actual artifacts disagree, return `blocked: state_mismatch` and preserve both for diagnosis.

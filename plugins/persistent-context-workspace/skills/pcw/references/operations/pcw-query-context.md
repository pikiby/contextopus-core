# Query context

Select the exact existing memory needed to create or refine one task-specific `current.md` without changing files.

## Preconditions

- `$pcw` loaded the shared contract and this operation.
- A successful workspace receipt identifies an existing workspace.
- One exact natural-language context request is available.

## Inputs

- The resolved workspace and subproject.
- The verbatim context request.
- Existing `current.md`, `knowledge/index.md`, and targeted search capability.
- A selection budget, defaulting to 2,000 tokens.

## Procedure

1. Remain read-only. Do not create or recover a cycle and do not change Git state.
2. Read existing `current.md` completely so explicit refinements can preserve or replace it correctly.
3. Extract the requested task identity, outcome, scope, objects, rules, constraints, blockers, paths, and relations.
4. Use the knowledge index, current references, filenames, relations, and targeted full-text search to find candidate records.
5. Read every record that materially affects the requested task context and no unrelated record. Follow links only when their meaning can change the task, plan, constraint, blocker, or required evidence.
6. Prefer active supported meanings over superseded records. Keep contradictions and attribution explicit.
7. Preserve relevant user constraints verbatim. Do not turn an unrelated durable rule into task context.
8. Return a bounded selection with stable coordinates without rewriting Current.

## Output

Return `output_state: context_selected`, `cycle_id: null`, `artifacts: []`, the selected knowledge records, relevant existing Current meanings, evidence coordinates, conflicts, and the selection basis.

## Blockers

- `workspace_missing`
- `request_missing`
- `current_unreadable`
- `knowledge_index_unreadable`
- `relevant_reference_missing`
- `budget_requires_constraint_loss`

## Idempotency

Remain strictly read-only. Identical memory, request, and budget produce the same selected records and semantically equivalent selection.

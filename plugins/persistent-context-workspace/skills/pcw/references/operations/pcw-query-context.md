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
3. Extract the verbatim request and any requested task identity, outcome, explicit scope and exclusions, objects, rules, constraints, authority, blockers, paths, and relations. Keep unstated material unstated; do not treat a knowledge-only request as a task replacement.
4. Use the knowledge index, current references, filenames, relations, and targeted full-text search to find candidate records.
5. Read every record that materially affects the requested task context and no unrelated record. Follow links only when their meaning can change the task, plan, constraint, blocker, or required evidence.
6. Prefer active supported meanings over superseded records. Keep contradictions and attribution explicit.
7. Preserve relevant user constraints verbatim. Classify selected material as `user`, `fact`, or `unresolved`; do not turn an unrelated durable rule, Reader finding, or inferred best practice into task context.
8. Identify a `derived` candidate only when primary evidence proves it necessary to an explicit requested outcome inside the existing scope. Return its evidence and exact outcome mapping; do not use it to create a new subject, deliverable, audience, lifecycle phase, or quality rule.
9. Return a bounded selection with stable coordinates and explicit `out_of_scope` findings without rewriting Current.

## Output

Return `output_state: context_selected`, `cycle_id: null`, `artifacts: []`, the selected knowledge records, provenance and relevance classifications, relevant existing Current meanings, evidence coordinates, out-of-scope findings, conflicts, and the selection basis.

## Blockers

- `workspace_missing`
- `request_missing`
- `current_unreadable`
- `knowledge_index_unreadable`
- `relevant_reference_missing`
- `budget_requires_constraint_loss`
- `task_meaning_ambiguous`

## Idempotency

Remain strictly read-only. Identical memory, request, and budget produce the same selected records and semantically equivalent selection.

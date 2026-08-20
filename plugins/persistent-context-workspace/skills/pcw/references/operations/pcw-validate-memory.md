# Validate memory

Validate durable knowledge and the new task-specific Current without modifying anything.

## Preconditions

- Promotion and Current compaction receipts exist for the same cycle.
- No writes occurred after compaction.

## Inputs

- Workspace, cycle id, manifest entry skill, and current budget.
- `current.before.md`, new `current.md`, promotion manifest, changed knowledge, every accepted result, and Git status.

## Procedure

1. Do not write, stage, commit, or repair anything.
2. Verify exactly one `# Current` followed by exactly one `# References`.
3. Verify that every accepted result id appears in promotion exactly once.
4. Resolve every local link and inspect every external evidence coordinate.
5. Verify every knowledge claim against accepted results, existing supported knowledge, explicit user meaning, or primary evidence.
6. Verify that Current contains the task identity, scope, relevant rules, constraints, blockers, execution logic, and references needed by a clean Controller, with no unrelated knowledge or history.
7. Preserve every relevant user constraint verbatim and keep conflicts explicit.
8. For `entry_skill: pcw`, require user support for creating, refining, replacing, or closing the task context-plan.
9. For `entry_skill: pcw-run`, compare the snapshot and reject any independent change to task identity, scope, constraints, or plan; permit only evidenced execution state and status.
10. Enforce the budget without dropping relevant task context.
11. Verify that Git tracks nothing under `tmp/` and that the durable diff is limited to Current, knowledge, and the permitted `.gitignore`.
12. Return every check and failure without repairing the target.

## Output

On success return `output_state: validated`, passed checks, warnings, failures, validated paths, and exact Git status. On failure return `status: blocked` and retain `output_state: current_compacted`.

## Blockers

- `current_shape_invalid`
- `result_not_classified`
- `broken_reference`
- `unsupported_claim`
- `hidden_conflict`
- `relevant_context_omitted`
- `unrelated_context_included`
- `run_attempted_replan`
- `budget_exceeded`
- `tmp_tracked`
- `unexpected_diff`

## Idempotency

Remain strictly read-only. Return an equivalent validation result for the same file state.

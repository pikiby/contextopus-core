---
name: pcw-validate-memory
description: Validate one compacted Persistent Context Workspace state without modifying files, the Git index, or external systems. Internal read-only subskill; use only when loaded by pcw immediately after pcw-compact-current.
---

# Validate memory

Validate the new state independently of writing operations and return only a validation envelope.

## Preconditions

- `pcw-promote-knowledge` and `pcw-compact-current` receipts exist for the same cycle.
- No writes occurred after compaction.

## Inputs

- `workspace` and `cycle_id`.
- `current.before.md`, the new `current.md`, and the promotion manifest.
- Changed knowledge records.
- Every accepted cycle result.
- Current Git status and budget.

## Procedure

1. Do not write, stage, commit, or repair anything.
2. Verify the presence and order of `# Current`, `# Pinned`, and `# References`.
3. Compare old and new `Pinned`:
   - retained items must match verbatim;
   - additions and removals must have explicit user evidence in the promotion manifest.
4. Verify that every accepted `result_id` appears in the promotion manifest exactly once.
5. Resolve every local knowledge link and inspect every external evidence coordinate.
6. Verify that each Current claim comes from promotion, knowledge, or explicit user input.
7. Verify that conflicts remain explicit and were not collapsed into a false fact.
8. Verify the absence of an assumed next action, imposed plan, and detailed journal. When Current retains authorized unfinished work, verify its target, scope, and execution state against explicit user or accepted-result evidence and require declarative state rather than an instruction or forecast.
9. Evaluate the `current.md` budget; treat an overrun caused only by verbatim `Pinned` as a warning and any other overrun as failure.
10. Verify that Git tracks nothing under `tmp/`.
11. Verify that the memory diff is limited to `current.md`, `knowledge/`, and the workspace `.gitignore`.
12. Return every check and failure without repairing the target.

## Output

On success, return `output_state: validated` and:

```yaml
validation:
  checks_passed: []
  warnings: []
  failures: []
  validated_paths: []
  git_status: <exact porcelain summary>
```

On any failure, return `status: blocked` and keep `output_state: current_compacted`.

## Blockers

- `pinned_changed`
- `result_not_classified`
- `broken_reference`
- `unsupported_claim`
- `hidden_conflict`
- `budget_exceeded`
- `tmp_tracked`
- `unexpected_diff`

## Idempotency

Remain strictly read-only. Return an equivalent validation result for the same file state.

# Compact current

Rebuild the persistent task-specific `current.md` from the promotion manifest without changing knowledge.

## Preconditions

- A successful promotion receipt exists for the same workspace and cycle.
- Every referenced knowledge object already exists or is explicitly external.
- The old `current.md` exists.

## Inputs

- The old Current and one immutable `current.before.md` snapshot.
- Promotion manifest and `entry_skill`.
- Only knowledge records selected by promotion.
- The configured Current budget.

## Procedure

1. Copy the exact old content to `tmp/<cycle-id>/current.before.md` if the snapshot does not already exist.
2. Use only classifications from promotion; never revisit raw results to reclassify them.
3. For `entry_skill: pcw`, build the complete active task context-plan requested by the user:
   - preserve or change task identity, outcome, scope, constraints, blockers, and plan exactly as supported by current user meaning;
   - include every selected fact or rule that materially affects execution;
   - omit all unrelated knowledge and history;
   - mark an explicitly closed task as `Status: closed` without deleting Current.
4. For `entry_skill: pcw-run`, preserve task identity, outcome, scope, constraints, and plan from the snapshot. Update only evidenced factual execution state and status.
5. Replace detailed durable meaning with stable knowledge links while keeping Current self-contained enough for a clean Controller to execute without searching `knowledge/`.
6. Keep conflicts and blockers visible. Preserve relevant user constraints verbatim.
7. Compact by removing duplicates, merging equivalent wording, replacing evidence detail with coordinates, and dropping transient operational noise.
8. Produce exactly `# Current` followed by `# References` and replace the file only after the full candidate exists.
9. Do not change knowledge, cycle results, or the Git index.

## Output

Return `output_state: current_compacted`, snapshot path, entry skill, sizes before and after, used references, and any budget warning.

## Blockers

- `promotion_incomplete`
- `task_change_unjustified`
- `run_attempted_replan`
- `relevant_context_omitted`
- `unrelated_context_included`
- `reference_missing`
- `budget_requires_semantic_loss`
- `current_shape_invalid`

## Idempotency

The same snapshot, promotion manifest, and entry skill produce identical `current.md`. Never overwrite the cycle snapshot on a repeated call.

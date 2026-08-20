# Validate memory

Validate durable knowledge and the new task-specific Current without modifying anything.

## Preconditions

- Promotion and Current compaction receipts exist for the same cycle.
- For `entry_skill: pcw-run`, the accepted final Controller result includes semantic acceptance against the same Current snapshot.
- No writes occurred after compaction.

## Inputs

- Workspace, cycle id, manifest entry skill, verbatim opening request, and current budget.
- `current.before.md`, new `current.md`, promotion manifest, compaction receipt, changed knowledge, every accepted result, and Git status.

## Procedure

1. Do not write, stage, commit, or repair anything.
2. Verify exactly one `# Current` followed by exactly one `# References`, exactly one `Task:`, and exactly one `Status:` whose value is one of `draft`, `ready`, `running`, `blocked`, `complete`, or `closed`.
3. Verify that the manifest opening request exactly matches the verbatim request captured when this cycle opened. Reject an agent-authored correction request or a replacement manifest request.
4. Verify that every accepted result id appears in promotion exactly once.
5. Resolve every local link. For external evidence, require an existing addressable object and valid line, range, revision, or object coordinate whose content supports the associated claim; reread primary evidence when it is unverified, changed, involved in a conflict, or only its path existence was checked.
6. Verify every knowledge claim against accepted results, existing supported knowledge, explicit user meaning, or primary evidence.
7. Verify that Current contains the complete Task lock, including the verbatim request, required outcome, scope, exclusions, user constraints, authority, and open questions, plus supported blockers and execution logic. Require relevant knowledge and evidence entry points with no unrelated history.
8. Verify provenance for every task-defining statement. Only exact user meaning may define a new outcome, scope boundary, exclusion, audience, deliverable, authority, or quality criterion. Require evidence and an exact outcome mapping for every `derived` step. Reject unresolved inference presented as a requirement.
9. Preserve every relevant user constraint verbatim and keep conflicts explicit. Reject agent-owned style metrics, best practices, adjacent defects, and surrounding-system prerequisites when they were promoted as requirements without support under step 8.
10. For `entry_skill: pcw`, require user support for creating, refining, replacing, or closing the task context-plan and verify every Current change semantically against the manifest request. When the request changes knowledge but not the task, require the existing Task lock to remain unchanged.
11. For `entry_skill: pcw-run`, verify the final Controller result's requirement mapping and passed primary semantic acceptance against the same snapshot. Compare the snapshot and reject any independent change to task identity, outcome, scope, exclusions, constraints, authority, audience, deliverables, quality criteria, or plan; permit only evidenced execution state and status.
12. Recompute the snapshot and Current UTF-8 byte sizes and require an exact match with the compaction receipt.
13. Enforce the budget without dropping relevant task context.
14. Verify that Git tracks nothing under `tmp/` and that the durable diff is limited to Current, knowledge, and the permitted `.gitignore`.
15. Return every check and failure without repairing the target. On failure, keep the same cycle at `current_compacted`; never checkpoint, prune, report completion, or open a correction cycle.

## Output

On success return `output_state: validated`, passed checks, warnings, failures, validated paths, and exact Git status. On failure return `status: blocked` and retain `output_state: current_compacted`.

## Blockers

- `current_shape_invalid`
- `task_lock_invalid`
- `current_status_invalid`
- `manifest_request_mismatch`
- `receipt_mismatch`
- `result_not_classified`
- `broken_reference`
- `evidence_coordinate_invalid`
- `unsupported_claim`
- `invented_requirement`
- `derived_step_unmapped`
- `semantic_acceptance_missing`
- `hidden_conflict`
- `relevant_context_omitted`
- `unrelated_context_included`
- `run_attempted_replan`
- `budget_exceeded`
- `tmp_tracked`
- `unexpected_diff`

## Idempotency

Remain strictly read-only. Return an equivalent validation result for the same file state. Repair a failure by rerunning the earliest faulty operation in the same cycle, not by changing the request or opening another cycle.

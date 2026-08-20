# Promote knowledge

Classify every accepted raw meaning, update durable linked knowledge, and prepare the complete Current change input.

## Preconditions

- Exactly one open or recovering cycle exists.
- Every accepted Reader, Controller, Worker, or user result is recorded canonically.
- `current.md` and `knowledge/` are readable.

## Inputs

- Workspace, cycle id, and manifest `entry_skill`.
- Existing Current and every unpromoted result.
- Relevant knowledge records and verbatim user messages stored in cycle material.

## Procedure

1. Build a complete result-id inventory and skip none.
2. Split distinct meanings into `knowledge_changes`, `current_changes`, `ephemeral`, or `conflicts`.
3. For durable knowledge, classify each coherent meaning as an object, fact, rule, constraint, blocker, decision, or relation.
4. Preserve active user constraints verbatim. Keep user claims about external state attributed until primary evidence verifies them.
5. Update a matching knowledge object instead of duplicating it. Use status and `supersedes` for explicit corrections, revocations, and replacements.
6. For `entry_skill: pcw`, accept Current changes only when supported by the current user request and selected relevant knowledge. They may create, refine, replace, or close the task context-plan.
7. For `entry_skill: pcw-run`, accept Current changes only for evidenced execution status, completed work, failures, and blockers. Reject independent changes to task identity, scope, constraints, or plan.
8. Classify intermediate commands, repeated tool output, raw maps, and detail already recoverable through a durable reference as ephemeral.
9. Keep incompatible supported meanings in `conflicts`; never choose one silently.
10. Write knowledge changes first, then the complete `tmp/<cycle-id>/promotion.md`. Do not change Current.

## Output

Return `output_state: knowledge_promoted`, the promotion path, changed knowledge objects, permitted Current changes, conflicts, and category counts. The processed result count must match the accepted result count.

## Blockers

- `unrecorded_result`
- `evidence_missing`
- `knowledge_identity_ambiguous`
- `unrepresentable_conflict`
- `constraint_source_missing`
- `run_attempted_replan`
- `partial_promotion`

## Idempotency

With identical inputs, never duplicate records, relations, or promotion entries. The same result id with different content blocks promotion.

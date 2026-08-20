# Promote knowledge

Classify every accepted raw meaning, update durable linked knowledge, and prepare the complete Current change input.

## Preconditions

- Exactly one open or recovering cycle exists.
- Every accepted Reader, Controller, Worker, or user result is recorded canonically.
- Every final Controller result has a complete requirement mapping and passed semantic acceptance against the same Current snapshot.
- `current.md` and `knowledge/` are readable.

## Inputs

- Workspace, cycle id, and manifest `entry_skill`.
- Existing Current and every unpromoted result.
- Relevant knowledge records and verbatim user messages stored in cycle material.

## Procedure

1. Build a complete result-id inventory and skip none.
2. Split distinct meanings into `knowledge_changes`, `current_changes`, `ephemeral`, or `conflicts`.
3. For durable knowledge, classify each coherent meaning as an object, fact, rule, constraint, blocker, decision, or relation.
4. Preserve active user constraints verbatim. Keep user claims about external state attributed until primary evidence verifies them. Never classify agent-authored text as user meaning.
5. Update a matching knowledge object instead of duplicating it. Use status and `supersedes` for explicit corrections, revocations, and replacements.
6. For `entry_skill: pcw`, accept task-defining Current changes only from exact current user meaning. Accept a `derived` execution step only with primary evidence and a mapping proving it necessary inside an existing `user` outcome. Knowledge and evidence may support the task but cannot expand it.
7. For `entry_skill: pcw-run`, accept Current changes only for evidenced execution status, completed work, failures, and blockers. Reject independent changes to task identity, outcome, scope, exclusions, constraints, authority, audience, deliverables, quality criteria, or plan.
8. Classify every `out_of_scope`, merely adjacent, or unmapped finding as ephemeral unless it independently belongs in durable knowledge; never place it in Current or use it to justify a source change.
9. Classify intermediate commands, repeated tool output, raw maps, recursive child Reader reports already represented by an accepted compact parent result, and detail already recoverable through a durable reference as ephemeral.
10. Keep incompatible supported meanings in `conflicts`; never choose one silently.
11. Write knowledge changes first, then the complete `tmp/<cycle-id>/promotion.md`. Do not change Current.

## Output

Return `output_state: knowledge_promoted`, the promotion path, changed knowledge objects, permitted Current changes, conflicts, and category counts. The processed result count must match the accepted result count.

## Blockers

- `unrecorded_result`
- `evidence_missing`
- `knowledge_identity_ambiguous`
- `unrepresentable_conflict`
- `constraint_source_missing`
- `invented_requirement`
- `derived_step_unmapped`
- `semantic_acceptance_missing`
- `run_attempted_replan`
- `partial_promotion`

## Idempotency

With identical inputs, never duplicate records, relations, or promotion entries. The same result id with different content blocks promotion.

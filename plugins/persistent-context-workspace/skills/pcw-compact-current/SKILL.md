---
name: pcw-compact-current
description: Rebuild and progressively compact current.md from the existing current file and a completed promotion manifest while preserving active pinned constraints verbatim. Internal subskill; use only when loaded by pcw after pcw-promote-knowledge succeeds.
---

# Compact current

Rebuild the current fingerprint as a whole. Never reclassify raw results or update knowledge.

## Preconditions

- A successful `pcw-promote-knowledge` receipt exists for the same workspace and cycle.
- Every promotion link already exists or is explicitly external.
- The old `current.md` exists.

## Inputs

- The old `current.md`.
- `tmp/<cycle-id>/promotion.md`.
- Only knowledge records referenced by the promotion manifest.
- The current budget from the cycle manifest.

## Procedure

1. Copy the exact old content to `tmp/<cycle-id>/current.before.md` if the snapshot does not already exist.
2. Use classification only from the promotion manifest; never revisit raw results to reclassify them.
3. Preserve active `Pinned` text verbatim and in its existing order.
4. Add `pinned_additions` verbatim. Remove an item only when `pinned_removals` includes explicit user revocation evidence.
5. Rebuild `Current` as a coherent fingerprint of factually active state.
6. Compact in this order:
   - remove exact duplicates;
   - merge equivalent meanings;
   - replace detailed evidence with stable references;
   - replace promoted durable detail with knowledge links;
   - remove resolved operational noise;
   - shorten wording without losing constraints or decision rationale.
7. Build `References` only from existing knowledge, `blocked_by`, and evidence links.
8. Never add a next action, execution plan, full Completed/Open work history, or guess about the next request. Preserve an explicitly authorized unfinished operation classified by promotion only as a declarative factual state with its evidenced target, scope, and execution state; update or remove it when completed, revoked, replaced, paused, or materially rescoped.
9. Replace `current.md` as a whole only after the complete candidate exists.
10. Do not change `knowledge/`, cycle results, or the Git index.

## Output

Return `output_state: current_compacted`, the snapshot path, sizes before and after, used references, and a warning when `Pinned` alone exceeds the budget.

## Blockers

- `promotion_incomplete`
- `pinned_change_unjustified`
- `reference_missing`
- `budget_requires_semantic_loss`
- `current_shape_invalid`

## Idempotency

The same old snapshot and promotion manifest must produce identical `current.md`. Never overwrite the cycle snapshot on a repeated call.

---
name: pcw-promote-knowledge
description: Classify every accepted result in one Persistent Context Workspace cycle, update only durable knowledge records, and write a complete promotion manifest for current compaction. Internal subskill; use only when loaded by persistent-context-workspace at a memory checkpoint or recovery boundary.
---

# Promote knowledge

Classify new meanings once, update durable knowledge, and prepare the compactor's complete input.

## Preconditions

- Exactly one open or recovering cycle exists.
- Every accepted Reader or Worker result was recorded through `pcw-record-result` or uses the same canonical format.
- `current.md` and `knowledge/` are readable.

## Inputs

- `workspace` and `cycle_id`.
- `current.md`.
- Every unpromoted result in the cycle.
- Relevant existing `knowledge/` records.
- Verbatim user messages stored in cycle material.

## Procedure

1. Build a complete `result_id` inventory; skip none.
2. Assign every distinct meaning to exactly one primary category.
3. Classify a meaning as a `Current` candidate only when every condition holds:
   - it is factually true at checkpoint time;
   - without it, a fresh agent has a material risk of misunderstanding state or acting incorrectly in the next session;
   - it remains relevant under a reasonable change of the next request within the same subproject;
   - it is not an assumed next action, old plan, or minor completed chronology;
   - primary coordinates or an explicit user statement support it.
   An explicitly authorized unfinished operation is a factual Current candidate, not an assumed next action, when its exact target, authorized scope, and execution state have user or recorded-result evidence and its absence would break continuation.
4. If one stable reference makes the meaning cheap to recover, store the detail in `knowledge/` and pass only a reference candidate to Current.
5. Classify a meaning as `Pinned` only when it is a verbatim user constraint that still applies. Never infer `Pinned` from agent behavior or an old plan.
6. Classify a meaning as durable knowledge when it is verified, useful beyond the current stage, and does not need to occupy `current.md` continuously.
7. Classify a meaning as ephemeral when it is an intermediate command, repetition, closed detail, tool output without durable value, or a detail already reachable through a reference.
8. Put incompatible supported meanings in `conflicts`; never choose one silently.
9. Update an existing knowledge record instead of duplicating it. Use `supersedes` for replaced information.
10. Write `knowledge/` changes first, then write the complete `tmp/<cycle-id>/promotion.md`.
11. Do not change `current.md`.

## Output

Return `output_state: knowledge_promoted`, the `promotion.md` path, changed records, and category counts. The processed `result_id` count must match the accepted result count.

## Blockers

- `unrecorded_result`
- `evidence_missing`
- `knowledge_identity_ambiguous`
- `unrepresentable_conflict`
- `pinned_source_missing`
- `partial_promotion`

## Idempotency

With identical inputs, never create duplicate records, repeated relations, or duplicate promotion entries. A repeated result with different content blocks promotion until resolved.

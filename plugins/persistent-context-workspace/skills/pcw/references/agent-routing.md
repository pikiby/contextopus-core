# Agent routing

## Clean Controller for `pcw-run`

- Start the Controller with no inherited conversation turns.
- Pass the exact run request, complete `current.md`, source roots, referenced coordinates, and authority boundary; pass nothing from earlier chat.
- Require the Controller to read Current before source inspection or delegation.
- Do not allow the Controller to search `knowledge/` to repair an incomplete context-plan.
- Return `context_insufficient` when Current cannot support the requested run.
- Route new questions and authority requests through the primary agent.

The clean Controller may perform simple work itself. For distributed execution, it creates Workers from its own clean context so they inherit Current rather than the primary conversation.

## Cheap source pass

Before launching Readers for a `$pcw` context update, inspect types, sizes, file count, searchability, and natural structural boundaries. Read small or clearly structured sources directly.

For one large or unknown file:

1. create sequential overlapping windows without gaps;
2. identify the local structure of each window;
3. repartition adaptively around events, rows, objects, or sections;
4. merge and reread objects split by a boundary;
5. perform a targeted second pass only on regions related to the context request.

The map is temporary material in `tmp/`, not durable knowledge.

## Readers

- Always include the exact current context request.
- Assign one exact, non-overlapping core range; use overlap only to reconstruct boundaries.
- Require facts, coordinates, relations, and uncertainty.
- Reject summaries without primary coordinates.
- Use Luna for high-volume simple reading and classification.
- Use Terra for ambiguous regions, cross-file relations, and architectural analysis.

## Workers

- Provide the complete prepared `current.md` and original target objects.
- Never let multiple Workers modify the same file or live system concurrently.
- Require changed objects, executed checks, coordinates, and remaining uncertainty.
- Do not let a Worker change the prepared task, scope, constraints, or plan.

The primary agent remains the user interface and authority boundary. Do not add a separate Verifier. Create another coordination role only for a concrete need.

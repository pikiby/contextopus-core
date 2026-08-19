# Agent routing

## Cheap first pass

Before launching Readers, inspect types, sizes, file count, searchability, and natural structural boundaries. Read small or clearly structured sources directly.

For one large or unknown file:

1. create sequential overlapping windows without gaps;
2. identify the local structure of each window;
3. repartition adaptively around events, rows, objects, or sections;
4. merge and reread objects split by a boundary;
5. perform a targeted second pass only on regions related to the user request.

The map is temporary navigation material in `tmp/`, not durable knowledge.

## Readers

- Always include the original user request.
- Assign one exact, non-overlapping core range; use overlap only to reconstruct boundaries.
- Require facts, coordinates, relations, and uncertainty.
- Reject summaries without primary coordinates.
- Use Luna for high-volume simple reading and classification.
- Use Terra for ambiguous regions, cross-file relations, and architectural analysis.
- Increase reasoning after the cheap pass instead of assigning maximum effort in advance.

## Workers

- Provide original target objects, not only summaries.
- Pass literal scope and `Pinned` constraints.
- Never let multiple Workers modify the same file or live system concurrently.
- Require changed objects, executed checks, coordinates, and remaining uncertainty.

The primary agent remains the user interface and makes the final decision. Do not add a separate Verifier. Create an Integrator or Correlator only for a concrete need, never as a mandatory layer.

# Agent routing

## Clean Controller for `pcw-run`

- Start the Controller with no inherited conversation turns.
- Pass the exact run request, complete `current.md`, workspace and source roots, referenced coordinates, and authority boundary; pass nothing from earlier chat.
- Require the Controller to read Current before source inspection or delegation.
- Treat Current as the immutable task root: knowledge retrieval may supply evidence and detail, but it cannot change task identity, scope, authority, user constraints, or plan.
- Read a small, precise target directly. For a large or ambiguous target, give one Reader one exact question instead of performing a broad search.
- Check that every Reader result answers the assigned question, stays in scope, preserves claim meaning, and provides primary coordinates before accepting it.
- Return `context_insufficient` when task identity, scope, authority, or a required fact cannot be established by bounded retrieval.
- Route new questions and authority requests through the primary agent.

The clean Controller may perform simple work itself. For distributed execution, it creates Workers from its own clean context so they inherit Current rather than the primary conversation. It receives only the compact parent Reader result, never every recursive child report.

## Cheap source pass

Before broad source inspection, inspect types, sizes, file count, searchability, and natural structural boundaries. Read small or clearly structured sources directly.

For one large or unknown file:

1. create sequential overlapping windows without gaps;
2. identify the local structure of each window;
3. repartition adaptively around events, rows, objects, or sections;
4. merge and reread objects split by a boundary;
5. perform a targeted second pass only on regions related to the exact question.

The map is temporary material in `tmp/`, not durable knowledge.

## Readers

A Reader collects the smallest sufficient evidence for one exact question. It does not audit the whole system, rewrite instructions, propose an operator plan, or synthesize unrelated recommendations.

Give every Reader:

- the exact current request and one atomic question;
- the allowed knowledge and source scope;
- the required compact result shape and explicit non-goals.

For run-time retrieval, a Reader:

1. starts with knowledge links explicitly present in Current;
2. follows active, non-superseded relations only when they can answer the question;
3. uses targeted `knowledge/index.md`, filename, relation, or full-text search only when the linked records are insufficient;
4. follows stable source coordinates or inspects an allowed original target when primary evidence is required;
5. may recursively assign bounded subquestions, but merges their reports itself and returns one compact result to its caller.

Store accepted intermediate Reader reports in the active `tmp/` cycle. Do not forward their raw text through every ancestor.

Each Reader result contains:

- the answer and `confirmed`, `contradicted`, or `unverified` for each assigned claim;
- facts with the shortest sufficient primary coordinates;
- relevant relations, conflicts, uncovered scope, and uncertainty.

Preserve the claim's subject, scope, modality, and time. Missing evidence is `unverified`, not `contradicted`, unless the inspected source is authoritative and exhaustive for the exact claim. Do not infer a system-wide negative from absence in bounded paths or confuse a manual requirement with workflow automation.

Do not dump complete large files or run suites, builds, installers, formatters, or other write-capable commands unless the exact assignment requires them. For an explicitly required test, check dependencies first, prevent cache writes where possible, and verify that the workspace remains unchanged.

Use Luna for high-volume literal reading and classification. Use Terra for ambiguous regions, cross-file relations, and architectural analysis.

## Workers

- Provide the complete prepared `current.md`, the compact relevant Reader result, and original target objects.
- Never let multiple Workers modify the same file or live system concurrently.
- Require changed objects, executed checks, coordinates, and remaining uncertainty.
- Do not let a Worker change the prepared task, scope, constraints, authority, or plan.

The primary agent remains the user interface and authority boundary. Do not add a separate permanent role; recursion is internal Reader behavior.

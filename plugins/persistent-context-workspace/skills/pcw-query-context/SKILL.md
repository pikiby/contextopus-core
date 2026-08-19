---
name: pcw-query-context
description: Build one focused and source-linked context packet from a resolved Persistent Context Workspace without opening a cycle or changing any file. Internal read-only subskill; use only when loaded by the persistent-context-workspace orchestration contract for an explicit ask or do command.
---

# Query context

Retrieve the smallest durable context that answers one request without turning memory access into a write transaction.

## Preconditions

- The `persistent-context-workspace` orchestration contract loaded this file.
- A successful `pcw-resolve-workspace` receipt identifies an existing workspace.
- One exact query or task is available.

## Inputs

- The resolved `workspace` and `subproject`.
- The exact `query`.
- `current.md`, `knowledge/index.md`, and targeted search capability.
- A packet budget, defaulting to 1,200 tokens.

## Procedure

1. Remain read-only. Do not create or recover a cycle and do not change Git state.
2. Read `current.md` completely. Preserve every active `Pinned` constraint relevant to the query verbatim.
3. Extract concrete identities, paths, terms, and relations from the query and Current.
4. Use `knowledge/index.md`, links already selected by Current, filenames, and targeted full-text search to find candidate records.
5. Read only records whose contents materially affect the query. Do not load all of `knowledge/` or follow unrelated links recursively.
6. Prefer current supported facts over superseded records. Keep contradictions and uncertainty explicit.
7. Build a packet within budget by replacing detail with stable coordinates, never by dropping a relevant Pinned constraint. Return a warning if Pinned alone exceeds the budget.
8. Include no plan, recommendation, inferred next action, or unrelated history.

## Output

Return the standard envelope with `input_state: workspace_resolved`, `output_state: context_returned`, `cycle_id: null`, and `artifacts: []`, plus this visible packet:

```markdown
# PCW context packet

Workspace: <absolute workspace path>
Request: <exact query>

## Current

<relevant active state>

## Pinned

<relevant constraints verbatim, or None>

## Relevant knowledge

- <meaning> — [[knowledge/<id>]]

## Evidence

- <stable primary or memory coordinate>

## Uncertainty

- <unresolved contradiction or missing evidence, or None>
```

Also return `selected_records`, `search_basis`, and the approximate packet token count.

## Blockers

- `workspace_missing`
- `query_missing`
- `current_unreadable`
- `knowledge_index_unreadable`
- `relevant_reference_missing`
- `budget_requires_constraint_loss`

## Idempotency

Remain strictly read-only. Identical workspace contents, query, and budget produce a semantically equivalent packet and the same selected records.

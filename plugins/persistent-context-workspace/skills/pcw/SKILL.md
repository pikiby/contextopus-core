---
name: pcw
description: Create or update one Persistent Context Workspace from a natural-language request. Use only when the user explicitly invokes $pcw to maintain linked knowledge or create, refine, replace, or close a persistent task-specific current context and plan.
---

# PCW

Manage context without executing the source task. Interpret the entire invocation as natural language; paths, project identity, facts, scope, and requested changes may appear in any order.

## Required reading

Read this fixed set completely before working. Do not skip documents or sections based on your own judgment of relevance. Paths are relative to this skill directory.

- [Shared memory contract](references/workspace-contract.md)
- [Context editing rules](references/state-machine.md)
- [Shared Reader routing](references/agent-routing.md)
- [Resolve workspace](references/operations/pcw-resolve-workspace.md)
- [Query context](references/operations/pcw-query-context.md)
- [Inspect source](references/operations/pcw-inspect-source.md)
- [Checkpoint memory](references/operations/pcw-checkpoint-memory.md)

These are instruction references, not separate skills. Stop with `shared_contract_unavailable` if any required document cannot be read completely; do not reconstruct it from memory. Execution-only instructions belong to the other entrypoint and are not part of this set.

## Update context

1. Resolve the workspace from the current request with `pcw-resolve-workspace`.
2. For existing memory, use `pcw-query-context`. For missing memory, create it only when the request clearly asks to establish context; follow the context editing rules.
3. Use `pcw-inspect-source` only when the request needs source information. Read a small precise target directly or use bounded Readers for broad sources.
4. Write the requested meaning directly to its durable owner under the context editing rules. Saving already supplied text does not call for new research or rewriting.
5. Use `pcw-checkpoint-memory` unless the user forbids the local memory commit.

Do not add a validation, review, rereading, comparison, or test phase to this workflow. Perform such work only when it is itself requested by the user. Do not create temporary process documents.

## Boundaries and output

Do not execute the prepared task or mutate the source project. Do not independently replace, broaden, or close an active task. Keep the request's authority and explicit constraints.

Return the selected workspace, changed durable paths, the requested context result, unresolved questions, and local memory commit id when one was created. Do not claim completion when an operation reports failure.

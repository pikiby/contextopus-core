---
name: pcw
description: Create or update one Persistent Context Workspace from a natural-language request. Use only when the user explicitly invokes $pcw to maintain linked knowledge or create, refine, replace, or close a persistent task-specific current context and plan.
---

# PCW

Manage context without executing the source task. Treat the entire request after the skill invocation as natural language; project identity, paths, facts, rules, constraints, blockers, task scope, and requested context changes may appear in any order.

The selected workspace always has the shape `<work-root>/.pcw/<subproject>/`.

## Resolve meaning

Determine from the complete request:

- the project root and semantic workspace;
- whether a missing workspace should be created;
- durable objects, facts, rules, constraints, blockers, decisions, or relations to add, correct, supersede, or revoke;
- whether `current.md` should be created, refined, replaced, or closed;
- source areas that may be inspected read-only as evidence.

Use explicit paths and identities first. Otherwise select the only workspace that unambiguously belongs to the active project and request. Ask only when unresolved ambiguity would select a materially different workspace, task, or meaning. Never infer direction from an old plan or incidental similarity.

## Load the shared contract

1. Derive and canonicalize `references/` from the directory containing this `SKILL.md`.
2. Read `workspace-contract.md` and `state-machine.md` completely.
3. Read `agent-routing.md` when broad source inspection may require Readers.
4. Before each internal operation, read its exact `references/operations/<operation>.md` contract completely and follow it directly. These files are references, not invocable skills.

Stop with `shared_contract_unavailable` rather than reconstructing a missing operation from memory.

## Update context

1. Run `pcw-resolve-workspace` against the interpreted root and identity.
2. If memory is missing, create it only when the natural request clearly asks to establish new context. Otherwise return `workspace_missing` without creating a variant.
3. For an existing workspace, run `pcw-query-context` to select only the knowledge and existing Current meaning relevant to this request.
4. Run `pcw-open-cycle` to create or recover one transaction.
5. Record exact user-provided meaning. Preserve user constraints verbatim; keep claims about external state attributed until primary evidence verifies them.
6. When the request needs project evidence, run `pcw-inspect-source` and, only when required, `pcw-map-source`. Source inspection is read-only.
7. Update `knowledge/` as linked durable objects. Modify an existing object instead of duplicating it; keep superseded and conflicting meanings explicit.
8. Build or revise `current.md` as the self-contained compressed context and plan for one active task. Select only knowledge and evidence that materially affect that task. Include no unrelated history or project detail.
9. A user may refine `current.md` repeatedly. Preserve those supported refinements until the user changes, replaces, or closes the task.
10. Complete `pcw-promote-knowledge` → `pcw-compact-current` → `pcw-validate-memory` → `pcw-checkpoint-memory` → `pcw-prune-tmp`.

## Boundaries

- Do not execute the task described by `current.md` and do not mutate the source project.
- Do not erase durable knowledge merely because it is irrelevant to the active task; omit it only from `current.md`.
- Do not silently replace or close an active task.
- Keep `current.md` after the transaction; it is not temporary cycle material.
- The validated local memory checkpoint and exact-cycle prune are automatic unless the user explicitly forbids that memory transaction.
- Commits outside the selected memory repository and every push still require explicit user authorization.

## Output

Return the selected workspace, created or changed knowledge objects, the resulting active `current.md` purpose and scope, unresolved conflicts, and the local memory checkpoint id.

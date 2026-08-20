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
- the user's literal requested outcome, explicit scope, exclusions, constraints, and authority;
- durable objects, facts, rules, constraints, blockers, decisions, or relations the user actually asked to add, correct, supersede, or revoke;
- whether the user actually asked for `current.md` to be created, refined, replaced, or closed;
- source areas that may be inspected read-only as evidence.

Use explicit paths and identities first. Otherwise select the only workspace that unambiguously belongs to the active project and request. Ask only when unresolved ambiguity would select a materially different workspace, task, or meaning. Never infer direction from an old plan or incidental similarity.

Do not improve, broaden, complete, or reinterpret the request on the user's behalf. A discovered fact may clarify how to perform the requested work, but it does not create a new goal, audience, deliverable, lifecycle phase, or required section. When a material boundary is not stated and different choices would change the result, ask instead of choosing one.

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
5. Record exact user-provided meaning and build or preserve the Task lock defined by `workspace-contract.md`. Replace its verbatim task request only when the user actually establishes or changes the task; a knowledge-only request leaves the existing lock unchanged. Preserve every explicit user constraint and never relabel agent-authored text as user meaning.
6. Classify task material by provenance:
   - `user`: an outcome, scope boundary, exclusion, constraint, or authority explicitly supplied by the user;
   - `derived`: an implementation detail proven necessary to achieve that outcome inside its existing scope;
   - `fact`: supporting evidence that does not itself become a requirement;
   - `unresolved`: an inference or material ambiguity that requires user input before it can affect the task.
7. When the request needs project evidence, run `pcw-inspect-source` and, only when required, `pcw-map-source`. Source inspection is read-only. Classify relevant evidence without promoting surrounding-system facts into the task.
8. Update `knowledge/` as linked durable objects. Modify an existing object instead of duplicating it; keep superseded and conflicting meanings explicit.
9. Build or revise `current.md` as the compact task root for one active task. Keep the Task lock, authority, critical user constraints, blockers, and supported execution logic directly in Current; link stable knowledge and evidence detail instead of copying it. Include no unrelated history, infrastructure, workflow phase, or project detail merely because it was discovered.
10. Before promotion, compare the proposed Task lock and complete Current change set with the verbatim request. Reject any task-defining statement without `user` provenance and any `derived` step that is not necessary, evidenced, and mapped to an explicit requested outcome. After compaction, validation repeats this semantic comparison against the complete written Current. Ask the user when repair would require choosing new meaning.
11. A user may refine `current.md` repeatedly. Preserve those supported refinements until the user changes, replaces, or closes the task.
12. Complete `pcw-promote-knowledge` → `pcw-compact-current` → `pcw-validate-memory` → `pcw-checkpoint-memory` → `pcw-prune-tmp` only after the semantic comparison passes.

## Boundaries

- Do not execute the task described by `current.md` and do not mutate the source project.
- Do not convert Reader findings, general best practices, style preferences, adjacent defects, or deployment prerequisites into task requirements unless the user requested them or primary evidence proves them strictly necessary inside the locked scope.
- Do not erase durable knowledge merely because it is irrelevant to the active task; omit it only from `current.md`.
- Do not silently replace or close an active task.
- Keep `current.md` after the transaction; it is not temporary cycle material.
- The validated local memory checkpoint and exact-cycle prune are automatic unless the user explicitly forbids that memory transaction.
- Commits outside the selected memory repository and every push still require explicit user authorization.

## Output

Return the selected workspace, created or changed knowledge objects, the resulting active `current.md` purpose and scope, unresolved conflicts, and the local memory checkpoint id.

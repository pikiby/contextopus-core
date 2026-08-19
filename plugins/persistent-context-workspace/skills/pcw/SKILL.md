---
name: pcw
description: Explicit command interface for Persistent Context Workspace. Invoke only as $pcw ask, $pcw remember, $pcw do, or $pcw sync to retrieve, store, use, or reconcile one named .pcw subproject without relying on implicit memory behavior.
---

# PCW

Provide an explicit, observable boundary between ordinary agent work and persistent project context.

## Command form

Require exactly one of these forms:

```text
$pcw ask <subproject> <question>
$pcw remember <subproject> <statement>
$pcw do <subproject> <task>
$pcw sync <subproject> [scope]
```

Use an absolute project path supplied in the request as `work_root`; otherwise use the active project root. Treat `<subproject>` as an exact memory identity. Do not infer it from an old task, silently switch it, or create a variant slug. Ask for the missing value when the work root or subproject is not uniquely resolvable.

## Load the orchestration contract

1. Derive the plugin skills root from the directory containing this `SKILL.md`.
2. Resolve the sibling file `<skills-root>/persistent-context-workspace/SKILL.md`.
3. Canonicalize both paths and require the sibling to remain inside the same skills root.
4. Read the sibling completely and verify that its frontmatter `name` is `persistent-context-workspace`.
5. Follow it as the orchestration contract for the selected command.

Stop with `orchestration_contract_unavailable` if any check fails. Do not reconstruct the workflow from memory.

## Dispatch

### `ask`

Require a question. Resolve the workspace and run the orchestration contract's read-only context-query path. Return the complete visible context packet. Do not open a cycle, write memory, change source files, stage, commit, prune, or push.

### `remember`

Require a statement. Open or recover one memory cycle, record the statement as `kind: user` with the current user message as its coordinate, then run the complete promotion, compaction, validation, checkpoint, and exact-cycle prune transaction. Preserve a statement verbatim only when it is an active user constraint eligible for `Pinned`. User attribution proves that the user said it; it does not independently verify claims about external state.

### `do`

Require a task. First resolve the workspace and build a context packet for that exact task. Show `PCW context loaded: <workspace>` and the packet's selected references before work begins. Then open or recover a cycle, perform the task within its existing authority, record the actual final result and checks, and complete the memory transaction. A memory checkpoint does not replace or complete the requested source work.

### `sync`

Resolve the workspace, retrieve context for the named scope, and compare it with the project, Git, or external state. Source and external inspection is read-only. If no evidenced difference exists, report a read-only no-op without opening a cycle. Otherwise open or recover one cycle, record only evidenced differences, remove or supersede stale memory through the normal transaction, and report what changed in memory. Do not repair or mutate the compared source.

## Boundaries

- Never activate this interface for an ordinary prompt that does not invoke `$pcw`.
- Never execute more than the selected verb.
- Never load all of `knowledge/`; retrieve only what the query or comparison needs.
- Never invent a next action from memory.
- Require normal user authority for source changes, source-repository commits, live mutations, and every push.
- Treat the validated local commit and exact-cycle prune inside the selected PCW memory repository as the automatic memory transaction defined by the orchestration contract.

## Output

- `ask`: a visible `# PCW context packet` and no memory mutation.
- `remember`: the recorded meaning and local memory checkpoint id.
- `do`: the requested work result, verification, and memory checkpoint id.
- `sync`: evidenced memory changes, unresolved discrepancies, and memory checkpoint id when changes exist.

Do not report a successful mutation verb until its memory transaction has either completed or returned a concrete blocker.

---
name: persistent-context-workspace
description: Internal orchestration contract for the explicit pcw command interface. Coordinate persistent file-backed context through a .pcw workspace containing current.md, tmp, knowledge, and Git history, and load each narrow pcw-* operation from its verified sibling SKILL.md file. Do not invoke implicitly for ordinary work.
---

# Persistent Context Workspace

Manage long-running work through bounded external context after the explicit `$pcw` interface selects a command. Do not perform memory operations ad hoc. Select one state transition, load its narrow internal subskill, execute it, and verify its result before continuing.

## Required contract

Before changing memory, read these files completely:

- [workspace-contract.md](references/workspace-contract.md) for file formats and invariants;
- [state-machine.md](references/state-machine.md) for legal states and transitions;
- [agent-routing.md](references/agent-routing.md) for source analysis and agent routing.

Treat them as canonical. Stop with `contract_conflict` if an internal subskill contradicts them.

## Internal subskill loader

Do not rely on implicit skill matching, generated `$skill-name` text, or a runtime skill-call command.

For every internal operation:

1. Determine the directory containing this `SKILL.md` from the path used to load it.
2. Resolve the plugin skills root as that directory's parent.
3. Resolve the requested sibling exactly as `<skills-root>/<pcw-skill-name>/SKILL.md`.
4. Canonicalize both paths and require the requested file to remain inside the same skills root.
5. Read the sibling `SKILL.md` completely, continuing until EOF if the read is truncated.
6. Verify that its frontmatter `name` exactly matches the requested operation.
7. Follow that file as the active operation contract in the current agent context.
8. Require its standard result envelope before selecting another transition.

If the sibling file is missing, unreadable, outside the skills root, or has a mismatched name, stop with `internal_skill_unavailable`. Do not reconstruct the missing procedure from memory.

## Boundaries

- Treat `$pcw` as the only user-facing entry point. This skill is its internal orchestration contract.
- Do not let an internal subskill change scope or choose the following transition.
- Never mix memory from separate semantic subprojects.
- Do not load all of `knowledge/`; open only records found through the current request, `current.md` references, and targeted search.
- Never treat `tmp/` as confirmed knowledge.
- Treat a validated local commit inside the selected PCW memory repository and pruning its exact absorbed cycle as one automatic internal transaction unless the user explicitly forbids it; never stage `tmp/`.
- Require explicit user authorization for commits outside that memory repository and every push.
- Never add a next action, plan, or forecast to `current.md` unless the user explicitly pinned it as a durable constraint.

## Command routing

Accept the exact verb, work root, subproject, and payload already parsed by `$pcw`. Never replace the selected verb.

- `ask`: run `pcw-resolve-workspace` and `pcw-query-context`, return the packet, and stop without opening a cycle.
- `remember`: resolve and open or recover a cycle, record one `kind: user` result, then complete the memory checkpoint chain.
- `do`: resolve the workspace, run `pcw-query-context` for the task, expose the loaded workspace and selected references, then open or recover a cycle, perform and record the actual work, and complete the checkpoint chain.
- `sync`: resolve and query memory, compare it with the exact named scope read-only, and stop without a cycle when no evidenced difference exists. Otherwise open or recover a cycle, record only evidenced differences, and complete the checkpoint chain. Do not mutate the compared source.

Return `unsupported_command` for any other verb. An `ask` result is terminal for that invocation; `context_returned` is an input receipt, not a completed user task, for `do`.

## Query context

1. Load and execute `pcw-resolve-workspace` with the exact work root, subproject, and payload.
2. If the workspace does not exist, return `workspace_missing`; do not create memory for `ask`.
3. Load and execute `pcw-query-context` with the exact question or task.
4. Verify that the receipt is read-only, names the same workspace, has `cycle_id: null`, and contains `output_state: context_returned`.
5. For `ask`, return the complete visible packet and stop. For `do`, retain the packet as explicit task input before opening a cycle. For `sync`, retain it as comparison input and open a cycle only when the read-only comparison finds an evidenced difference.

## Open a cycle

1. Load and execute `pcw-resolve-workspace` with the work path, semantic subproject, and current request.
2. Validate its receipt, then load and execute `pcw-open-cycle`.
3. If the result contains `recovery_required`, finish the existing memory chain first:
   `pcw-promote-knowledge` → `pcw-compact-current` → `pcw-validate-memory` → `pcw-checkpoint-memory` → `pcw-prune-tmp`.
4. If the user explicitly forbade the local memory transaction, stop without opening a new cycle over unabsorbed material.
5. Read `current.md`, then retrieve only knowledge records relevant to the selected command.

For `remember`, record the statement through `pcw-record-result` as `kind: user`, with the user message as its source coordinate. User-provided constraints may be promoted to `Pinned` verbatim. Treat other user-provided external claims as attributed statements until supported by primary evidence.

## Work with a source

1. Load and execute `pcw-inspect-source` before broad reading.
2. For `decision: direct`, use targeted native reads and searches.
3. For `decision: map`, load and execute `pcw-map-source`, then use its map to assign Readers.
4. Give every Reader the original user request, one exact range, and the required evidence format.
5. Give every Worker original target objects, relevant reduced context, and literal user constraints.
6. Load and execute `pcw-record-result` for every accepted Reader or Worker result.
7. Treat direct work by the primary agent as Worker activity for memory purposes. Record the final target state and checks after the work; a pre-work analysis or assignment is not its result.
8. Include stable coordinates for external evidence that materially affected the result. Let promotion decide whether the meaning needs a knowledge record or remains recoverable through the target.

Do not introduce a mandatory Verifier. Do not introduce an Integrator or Correlator unless a concrete task requires one.

## Completion gate

Before reporting a user task or meaningful stage as complete:

1. Inventory every accepted source change and every external fact that materially affected it.
2. Require one recorded final result for each item, including target coordinates, checks, and remaining uncertainty.
3. Compare `current.md` and relevant knowledge with the actual target state. If either contradicts the target or retains an uncertainty resolved by the work, do not report completion.
4. Run the memory checkpoint chain for all unabsorbed results through successful validation.
5. Complete the automatic local memory transaction unless the user explicitly forbade it; never call the PCW cycle complete while it remains pending.

Do not let a successful source edit, direct reading mode, or the absence of subagents bypass this gate.

## Create a memory checkpoint

Run this chain after a meaningful stage, before a session handoff, when unabsorbed `tmp/` exists, or when `current.md` exceeds its budget:

1. `pcw-promote-knowledge` classifies cycle material and updates only `knowledge/`.
2. `pcw-compact-current` rebuilds only `current.md` from the promotion manifest.
3. `pcw-validate-memory` validates the new state without writing.
4. On `status: ok`, run `pcw-checkpoint-memory`, then use its created receipt to run `pcw-prune-tmp` without separate permission.

Never reorder these operations or merge their responsibilities manually.

## Return to unresolved work

Treat memory work as infrastructure. It does not complete or replace the source task that caused it.

1. After recovery, checkpointing, pruning, or another memory-only interruption, identify the latest unresolved and still-authorized user task only from explicit user messages, cycle manifests, accepted results, and supported Current facts.
2. Treat a request to record, inspect, compact, or checkpoint memory as additive when it does not explicitly cancel, replace, pause, or narrow the unfinished source task.
3. When the task remains authorized and memory is consistent, resume it without asking the user to repeat the request. Preserve its original target, scope, and authority boundaries.
4. Stop instead when the user cancelled, replaced, paused, or materially rescoped the task, when the task is already complete, or when continuation requires new authority.
5. Never resume from an agent-generated next action, stale plan, or incidental similarity to an old request.

An explicitly authorized unfinished operation may remain in `Current` as a factual state when its absence would break continuation. Describe only its supported target, authorized scope, and actual execution state in declarative language. Do not turn it into a recommendation or forecast. Update or remove it when the task changes state.

## Accept an internal result

For every operation, require the envelope from `workspace-contract.md` and verify:

- `operation` matches the loaded internal skill;
- `workspace` and `cycle_id` did not change;
- the input state permits the transition;
- every artifact is inside the operation's allowed write scope;
- `status: blocked` includes a concrete `reason` and stops the chain.

Treat `output_state` as a postcondition, not a recommendation. Select the next transition only from the canonical state machine.

## Stop conditions

Stop and return a verifiable blocker when:

- the subproject cannot be resolved uniquely;
- work requires broader scope or new authority;
- a contradiction cannot be represented explicitly;
- `Pinned` would be changed without user evidence;
- a required internal skill is unavailable;
- validation fails;
- the user explicitly forbade the pending local memory transaction.

Do not delete inputs or report a completed cycle in any of these states.

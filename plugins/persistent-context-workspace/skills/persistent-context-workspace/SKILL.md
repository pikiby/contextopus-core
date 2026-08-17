---
name: persistent-context-workspace
description: Orchestrate persistent file-backed context for long-running or multi-session work through a .rlm workspace containing current.md, tmp, knowledge, and Git history. Use when the user invokes $persistent-context-workspace, asks to continue work across sessions, requests RLM-style external memory, or needs a bounded context layer around a large source or project. This is the only public entry point; it loads every internal pcw-* subskill from its sibling SKILL.md file.
---

# Persistent Context Workspace

Manage long-running work through bounded external context. Do not perform memory operations ad hoc. Select one state transition, load its narrow internal subskill, execute it, and verify its result before continuing.

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

- Use this skill as the only user-facing entry point.
- Do not let an internal subskill change scope or choose the following transition.
- Never mix memory from separate semantic subprojects.
- Do not load all of `knowledge/`; open only records found through the current request, `current.md` references, and targeted search.
- Never treat `tmp/` as confirmed knowledge.
- Never commit or push without explicit user authorization.
- Never prune `tmp/` without successful validation and a confirmed checkpoint.
- Never add a next action, plan, or forecast to `current.md` unless the user explicitly pinned it as a durable constraint.

## Open a cycle

1. Load and execute `pcw-resolve-workspace` with the work path, semantic subproject, and current request.
2. Validate its receipt, then load and execute `pcw-open-cycle`.
3. If the result contains `recovery_required`, finish the existing memory chain first:
   `pcw-promote-knowledge` → `pcw-compact-current` → `pcw-validate-memory` → `pcw-checkpoint-memory` → `pcw-prune-tmp`.
4. If checkpointing requires authorization, stop for the user. Do not open a new cycle over unabsorbed material.
5. Read `current.md`, then retrieve only knowledge records relevant to the new request.

## Work with a source

1. Load and execute `pcw-inspect-source` before broad reading.
2. For `decision: direct`, use targeted native reads and searches.
3. For `decision: map`, load and execute `pcw-map-source`, then use its map to assign Readers.
4. Give every Reader the original user request, one exact range, and the required evidence format.
5. Give every Worker original target objects, relevant reduced context, and literal user constraints.
6. Load and execute `pcw-record-result` for every accepted Reader or Worker result.

Do not introduce a mandatory Verifier. Do not introduce an Integrator or Correlator unless a concrete task requires one.

## Create a memory checkpoint

Run this chain after a meaningful stage, before a session handoff, when unabsorbed `tmp/` exists, or when `current.md` exceeds its budget:

1. `pcw-promote-knowledge` classifies cycle material and updates only `knowledge/`.
2. `pcw-compact-current` rebuilds only `current.md` from the promotion manifest.
3. `pcw-validate-memory` validates the new state without writing.
4. On `status: ok`, run `pcw-checkpoint-memory`.
5. Only a receipt with `checkpoint_status: created` permits `pcw-prune-tmp`.

Never reorder these operations or merge their responsibilities manually.

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
- checkpointing still needs user authorization.

Do not delete inputs or report a completed cycle in any of these states.

---
name: pcw-run
description: Execute the task prepared in one Persistent Context Workspace current.md through a clean Controller that inherits no prior conversation. Use only when the user explicitly invokes $pcw-run with a natural-language execution request.
---

# PCW Run

Execute an already prepared `current.md` without letting the primary agent's earlier conversation alter the task context or plan.

The selected workspace always has the shape `<work-root>/.pcw/<subproject>/`.

## Resolve the run

Interpret the natural-language invocation only to identify the existing workspace, exact run request, target scope, and authority supplied by the user. Do not use it to rebuild or reinterpret `current.md`. Ask only when multiple workspaces or materially different execution targets remain possible.

## Load the shared contract

1. Derive the plugin skills root from the directory containing this `SKILL.md`.
2. Resolve and canonicalize `<skills-root>/pcw/references/` and require it to remain inside the same skills root.
3. Read `workspace-contract.md`, `state-machine.md`, and `agent-routing.md` completely.
4. Before each internal operation, read its exact `<shared-references>/operations/<operation>.md` contract completely and follow it directly. These files are references, not invocable skills.

Stop with `shared_contract_unavailable` rather than reconstructing a missing operation from memory.

## Isolation gate

The primary agent is only the user interface and authority boundary. It must not summarize prior conversation into the run, author a replacement context, or execute the prepared task itself.

1. Resolve the existing workspace and require a valid active `current.md`.
2. Open or recover one transaction for run results.
3. Start a clean Controller with no inherited conversation turns. In Codex, use a fresh subagent context such as `fork_turns: none`. If the host cannot provide clean isolation, return `clean_controller_unavailable` instead of falling back to the contaminated primary context.
4. Give the Controller only:
   - the exact current `$pcw-run` request verbatim;
   - the absolute workspace and source roots;
   - the complete prepared `current.md` and its referenced source coordinates;
   - the exact mutation scope and authority available for this run;
   - the shared operation contracts needed to record and finalize results.
5. Do not pass chat summaries, earlier messages, unrelated memory, or the primary agent's interpretation.

## Execute

1. The clean Controller reads `current.md` before any source inspection or delegation.
2. It works only from that context and the original target objects named by it. It does not search `knowledge/` to repair missing task context.
3. If `current.md` is insufficient, contradictory, or does not cover the requested run, return `context_insufficient` to the primary agent. Do not improvise a plan.
4. The Controller may execute a simple task itself or create Workers from its clean context. Every Worker receives the complete `current.md`, exact target objects, and authority boundaries.
5. New user input or broader authority is requested through the primary agent with `needs_input`; the Controller never expands scope itself.
6. Record actual changed objects, checks, evidence, failures, blockers, and remaining uncertainty in the active `tmp/` cycle.
7. Promote durable results into `knowledge/`. Update `current.md` only with factual execution state; do not change its task, scope, constraints, or plan independently.
8. Complete `pcw-promote-knowledge` → `pcw-compact-current` → `pcw-validate-memory` → `pcw-checkpoint-memory` → `pcw-prune-tmp` before reporting the run complete.

## Control and output

The primary agent verifies only the returned scope, target changes, checks, authority receipts, and final transaction state. It does not rewrite the Controller's semantic result from old conversation context.

Return the execution result, changed targets, checks, blockers, unresolved uncertainty, clean Controller identity, and local memory checkpoint id.

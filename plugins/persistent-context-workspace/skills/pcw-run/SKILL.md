---
name: pcw-run
description: Execute the task prepared in one Persistent Context Workspace current.md through a clean Controller that inherits no prior conversation. Use only when the user explicitly invokes $pcw-run with a natural-language execution request.
---

# PCW Run

Execute an already prepared `current.md` without letting the primary agent's earlier conversation or preferences alter the user's locked task meaning.

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

The primary agent is the user interface, authority boundary, and later semantic acceptance boundary, but never a task author. It must not summarize prior conversation into the run, author a replacement context, or execute the prepared task itself.

1. Resolve the existing workspace and require a valid active `current.md`.
2. Open or recover one transaction for run results.
3. Start a clean Controller with no inherited conversation turns. In Codex, use a fresh subagent context such as `fork_turns: none`. If the host cannot provide clean isolation, return `clean_controller_unavailable` instead of falling back to the contaminated primary context.
4. Give the Controller only:
   - the exact current `$pcw-run` request verbatim;
   - the absolute workspace and source roots;
   - the complete prepared `current.md`, including its Task lock, knowledge links, and referenced source coordinates;
   - the exact mutation scope and authority available for this run;
   - the shared operation contracts needed to record and finalize results.
5. Do not pass chat summaries, earlier messages, unrelated memory, or the primary agent's interpretation.

## Execute

1. The clean Controller reads `current.md` before any source inspection or delegation.
2. It treats Current's Task lock as immutable. Retrieval may add evidence and necessary implementation detail, but never a new outcome, audience, deliverable, lifecycle phase, scope, authority, user constraint, or agent-owned quality rule.
3. Before source inspection or mutation, it maps every planned output section, action, and target to an explicit requested outcome. A technical step without direct user wording is allowed only when primary evidence proves it necessary inside the locked scope. Omit unmapped material; return `context_scope_conflict` when omission or inclusion requires a material choice.
4. It reads a small precise target directly. For missing detail in a large or ambiguous area, it gives one Reader one exact question under `agent-routing.md`.
5. A Reader starts from Current's explicit knowledge links, may follow only relevant knowledge relations and source coordinates, and returns one compact answer with relevance classifications, facts, coordinates, conflicts, uncovered scope, and uncertainty. Recursive child reports stay below the parent Reader and in `tmp/`; the Controller receives only the merged result.
6. If task identity, scope, authority, or a required fact remains insufficient or contradictory after bounded retrieval, return `context_insufficient` to the primary agent. If new user meaning is required, return `needs_input`. Do not improvise, broaden the search, or turn adjacent findings into requirements.
7. The Controller may execute a simple task itself or create Workers from its clean context. Every Worker receives the complete `current.md`, the compact relevant Reader result, exact target objects, and authority boundaries.
8. The Controller returns the complete proposed result with a requirement mapping for every material change or output section, all deliberately excluded `out_of_scope` findings, checks, failures, and uncertainty.
9. Before accepting or recording the final Controller result, the primary agent reads the complete changed target and compares it semantically with the Task lock. It verifies that the requested outcome is present, user constraints are preserved, every addition is mapped, and no unrelated subject was introduced. It must not use old chat, invent new quality criteria, or rewrite the task during this review.
10. If semantic review fails, keep the same cycle in `working`, record no accepted final Controller result, forbid promotion, checkpoint, prune, and completion, and return exact Current-based deficiencies to the same clean Controller. Use `needs_input` instead when repair requires new user meaning.
11. Record only semantically accepted compact Reader and final execution results, including their mappings, actual changed objects, checks, evidence, failures, blockers, and remaining uncertainty in the active `tmp/` cycle.
12. Promote durable results into `knowledge/`. Update `current.md` only with factual execution state; do not change its task, scope, constraints, authority, or plan independently.
13. Complete `pcw-promote-knowledge` → `pcw-compact-current` → `pcw-validate-memory` → `pcw-checkpoint-memory` → `pcw-prune-tmp` before reporting the run complete. A failed semantic review or blocked validation stays in the same cycle and forbids checkpoint, prune, and completion.

## Control and output

The primary agent is an acceptance boundary, not a second task author. It verifies both transaction correctness and semantic fidelity to Current's verbatim request and Task lock. It never repairs the result by importing old conversation context or adding its own preferred scope, structure, style, or requirements.

Return the execution result, requirement mapping, excluded out-of-scope findings, changed targets, semantic acceptance result, checks, blockers, unresolved uncertainty, clean Controller identity, and local memory checkpoint id.

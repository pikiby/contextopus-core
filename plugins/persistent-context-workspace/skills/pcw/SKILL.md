---
name: pcw
description: Maintain and use a Persistent Context Workspace from a natural-language request. Use only when the user explicitly invokes $pcw to prepare context, retain knowledge, or execute or continue a task using that memory.
---

# PCW

PCW is the primary agent's working memory. The primary alone reads and changes knowledge, Current, links and the task ledger through MCP, performs consolidation and authorized memory checkpoints. Workers investigate or change explicitly authorized real sources and return substantive findings. A narrow semantic helper chooses embedding boundaries inside materials already divided by the primary. PCW does not dispatch agents, run a Controller or intercept completion.

## Start and restore context

Call `pcw_startup` once for the explicitly selected work root and workspace. Use its combined task, Current, memory and environment state to resume unfinished work; otherwise call `pcw_task_begin`. Its default checkpoint policy is `not_authorized`; choose `required` or `forbidden` only with actual authority and record its source in `checkpoint_reason`. Absence of permission is not a prohibition. An authorized request correction uses `pcw_task_update` with its current revision and reason; it preserves outstanding assignments.

The primary sets Current's step and blocker (`""` means none); goal, constraints and completion come from the registered request. Read back the update. Change Current when the chosen step or obstacle changes, not after every tool call. After conversation compaction or restart, use the startup state to recover the task, pending assignments, check plan and discrepancies. These control records survive loss of the derived index.

Try exposed MCP tools first. For missing tools or runtime components use [Runtime setup](references/setup.md). Recovery of PCW itself belongs to the primary. Missing knowledge is not an empty successfully recovered memory.

## Rules and operations

Use the instructions already loaded. Consult `pcw_rules_get` or [Action requirements](references/action-requirements.md) only when the relevant rule is needed. Retrieving rules has no operation side effects and is not a prerequisite before every call. Operations return compact state, missing prerequisites and relevant coordinates.

Use `pcw_assignment_prepare`, `pcw_result_assess`, `pcw_transition` and `pcw_finish` for their actual operations. Complete missing prerequisites, then retry the affected operation. Batch independent saving, reading, linking, preparation and boundary submission. A context-preparation request does not authorize executing a future task described in that context.

## Prepare and launch

Read relevant full materials and follow useful links; do not search empty knowledge. Select needed facts and put them in a complete assignment: goal, facts, allowed real source objects, constraints, expected result, check criteria and what to return. Workers receive no memory paths, material IDs, Current, ledger or memory-management instructions. Read [Native assignments](references/native-assignments.md).

The primary discovers actual native model/reasoning capabilities, records them with `pcw_environment_check`, compares them with task roles and publishes `pcw_tools_map_publish`. Reuse an existing map while actual capabilities are unchanged. A new conversation, session ID or warning output is not a capability change; environment version contains the real version, without diagnostics or session identity. Select a sufficient published profile with a reason and use its supported launch parameters. Do not delegate map construction or invent a provider ranking.

Call `pcw_assignment_prepare` with the full assignment and exact profile. For a planned checker, pass `check_id` here to bind it without rewriting the plan. Launch only after `ready: true`. Send **only `handoff.launch_message`** in a separate native context without inherited conversation (Codex: `fork_turns: "none"`). Bind the actual executor session with `pcw_assignment_bind`. Workers do not retrieve assignments through PCW. Every follow-up needs a fresh complete registered assignment; use a clean new context when existing worker history is inappropriate.

The handoff prohibits PCW tools and discovery, reading or changing of `.pcw` through any tool, shell or script. Only explicitly authorized task sources/actions are allowed. This is an assignment-level prohibition, not an OS or tool-access guarantee.

## Receive, save and assess

On each substantive work/check return, the primary immediately divides the returned text into large, meaningful, independently useful knowledge materials and links related materials. Preserve actual facts, conditions, details, code, tables, uncertainty and blockers. Do not mechanically create one file per heading or use fixed-size cuts. Do not require an additional giant unmodified return file.

Save those materials together with `pcw_save_result_blocks`, the assignment ID and actual executor session ID. MCP generates each filename-ID and UTC save time; the control record accounts for all blocks from that return. Read every saved block with `pcw_read_many(..., assignment_id=...)`, link with `pcw_links_many`, and record an explicit assessment using `pcw_result_assess`. Saving or reading is not factual acceptance. Continuations have separate registered returns even when they reuse a worker session.

A `needs_attention` finding remains unresolved until accepted clarification/check evidence and actual corrections address it. Update or replace known incorrect active knowledge; adding a linked clarification and closing the ledger is insufficient. See [Memory operations](references/memory-operations.md).

Record planned intermediate/final factual checks with `pcw_task_checks_set`, including timing, objects and criteria. Choose them for task complexity and add a check for a mismatch requiring attention. Do not create a checker automatically for every return. Checkers observe real sources or reproduce behavior, including research without changes. Save, read and assess their substantive findings.

## Prepare search and finish

After topic materials are saved, use `pcw_prepare_many` and a cheap suitable semantic helper to choose embedding boundaries **within** them. The helper receives only literal numbered text and returns boundary arrays without tools. Submit through `pcw_submit_boundaries_many`; use the single-material APIs for one material. Boundaries and technical receipts belong to control state. See [Prepare search](references/prepare-search.md).

Search still selects whole topic materials; read their full bodies and follow links. Helper fragments are embedding units, not a new snippet-search interface. Links-only changes and moves do not re-embed. Read [Embedding configuration](references/embeddings.md) for provider settings or failures; defaults are not measured performance claims.

The primary applies consolidation, links, Current and authorized checkpoints itself. Preserve useful knowledge; provenance metadata need not survive consolidation. Call `pcw_finish` with the whole acceptance scope and factual-check results. It checks registered work, planned checks, discrepancies, Current, preparation and required checkpoints. A `ready` response alone is not factual completion: compare the observed result with the user's full requested outcome and continue remaining authorized work. Report a concrete blocker only when continuation is impossible. Publication, source commits, installation and model downloads retain their own authorization requirements.

---
name: pcw
description: Maintain and use a Persistent Context Workspace from a natural-language request. Use only when the user explicitly invokes $pcw to prepare context, retain knowledge, or execute or continue a task using that memory.
---

# PCW

PCW is the primary agent's working memory. The primary alone reads and changes knowledge, Current, links and the task ledger through MCP, performs compaction and authorized memory checkpoints. Workers investigate or change explicitly authorized real sources and return substantive findings. A semantic helper only identifies block endings in supplied text. PCW does not dispatch agents, run a Controller or intercept completion.

## Start and restore context

Read `pcw_task_status`, `pcw_current_get` and `pcw_status` for the explicitly selected work root and workspace. Resume an unfinished request; otherwise call `pcw_task_begin`. Its default checkpoint policy is `not_authorized`; choose `required` or `forbidden` only with actual authority and record its source in `checkpoint_reason`. Absence of permission is not a prohibition. Use `pcw_task_update` with the request revision and reason for an authorized correction; it preserves outstanding assignments.

The primary calls `pcw_current_set` with the chosen step and blocker (`""` means none). Active-task goal, constraints and completion are copied from the registered request. Update step or blocker when they change, not after every tool call. Read back Current. On conversation compaction or restart, reload task status, Current, pending work, check plan and discrepancies before continuing. These control records survive loss of the derived index.

Try exposed MCP tools first. For missing tools or runtime components use [Runtime setup](references/setup.md). Recovery of PCW itself belongs to the primary. An unavailable or damaged knowledge directory is not an empty successfully recovered memory.

## Short action loop

1. Get `pcw_action_requirements` for `prepare_assignment`, `process_result`, `transition` or `finish` immediately before that action.
2. Perform the action within user authority. Correct missing prerequisites before proceeding.
3. Record its result through the applicable MCP operation.
4. Repeat for the next action.

Detailed [action requirements](references/action-requirements.md) are supplied by this call. A request to create context does not authorize executing a task described inside that context.

## Prepare and launch

The primary reads relevant memory with search/read/navigation; do not search empty knowledge. It selects needed facts and writes them into a complete assignment: goal, facts, allowed source objects, constraints, expected result, check criteria and what to return. Do not give workers memory paths, material IDs, Current, control records or memory-management instructions. Read [Native assignments](references/native-assignments.md).

The primary itself discovers current native models and reasoning capabilities, records them with `pcw_environment_check`, gathers model information, compares it with roles and publishes `pcw_tools_map_publish`. Refresh this map when the environment changes. Select a sufficient published profile, explain the choice and specify supported model/reasoning parameters at launch. Do not delegate map construction or invent a provider ranking.

Call `prepare_assignment` with the full assignment and exact profile. Launch only after `ready: true`. Send **only `handoff.launch_message`**, not the enclosing MCP response. Use a separate context without inherited conversation (in Codex, `fork_turns: "none"`). After launch, the primary calls `pcw_assignment_bind` with the actual executor session ID. Workers do not call PCW to retrieve assignments. For a continuation, register a fresh complete task; use a new clean context when previous worker history is no longer appropriate.

Every generated handoff prohibits use of PCW tools and discovery, reading or changing of `.pcw` through filesystem tools, shell or scripts. Only expressly authorized task sources/actions are allowed. This release implements an assignment-level prohibition; it does not claim OS or tool-access isolation.

## Results and checks

Workers return substantive Markdown: facts, method, source observations, changes, conditions, uncertainty and blockers. The primary calls `pcw_save_subagent_result` with the unmodified return, assignment ID and actual executor session ID, then `pcw_read` with material and assignment IDs, then `process_result` with an explicit assessment. MCP creates the filename-ID and UTC timestamp. Each new substantive assignment gets a separate return ID, including continuations. A conflict with the actual return must be resolved before acceptance.

Operational receipts such as “Current updated” or “index built” are not knowledge and must not be requested as substantive assignments. Semantic boundaries are recorded in control state by `pcw_submit_boundaries`; see [Prepare search](references/prepare-search.md). The primary performs Current and other memory operations directly.

Record planned intermediate/final factual checks using `pcw_task_checks_set`, including timing, objects and criteria. Choose them according to task complexity; assign an additional check when a result exposes a mismatch requiring attention. Do not schedule checks automatically for every return. Checkers inspect actual sources or reproduce behavior, including for research without changes. Save/read their substantive findings before acceptance. A `needs_attention` discrepancy remains until an accepted clarification/check explicitly resolves it.

## Finish memory work

Use [Memory operations](references/memory-operations.md) for updates, compaction, links, deletion and authorized history operations. Preserve useful facts, conditions, uncertainty, code and tables; compaction does not require retaining source attribution or provenance metadata. The primary applies all memory decisions itself.

Prepare retained changed bodies using the narrow semantic helper, then check actual indexed state. Links-only changes and moves do not re-embed. Read [Embedding configuration](references/embeddings.md) only for provider settings or failures; numerical defaults are not measured performance claims.

Call `finish` with the acceptance scope and factual-check results. Finish checks registered work, the check plan, unresolved discrepancies, Current, affected material preparation and required checkpoints. A ready response does not replace the primary's assessment of factual conformity. Continue authorized remaining work, or report a concrete blocker and the unfinished step. Publication, source commits, installation and model downloads retain their own authorization requirements.

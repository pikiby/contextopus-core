# Native assignments

The primary supplies a complete task in a separate native context. Use the current tools-map model and reasoning explicitly. In Codex request `fork_turns: "none"`; other environments need their equivalent. The access prohibition is part of the assignment contract; a clean context is not a filesystem or OS sandbox.

## Assignment contract

Include the goal, necessary facts as text, explicitly allowed real source objects, constraints, expected result, observable criteria and what to return. For edits, identify owned targets and tell the worker that others share the codebase: preserve and accommodate their changes. Do not pass knowledge filenames, IDs, Current, the task ledger, the parent conversation or memory-management instructions. Commands must remain within the authorized task.

The generated launch message prohibits PCW MCP and any discovery, reading or changing of `.pcw` via tools, shell or scripts. Workers act only on authorized real sources. They return findings to the primary, which owns saving, consolidation, links, Current and memory history.

Call `pcw_assignment_prepare` with the complete assignment and exact published profile. Correct missing prerequisites and retry until ready. Send only `handoff.launch_message`; enclosing coordination data remains primary-only. Bind the actual executor session with `pcw_assignment_bind` after native launch. Workers do not retrieve assignments through MCP.

For a follow-up, use `continuation_of` and register a complete fresh assignment with all needed facts. A continuation is new accountable work with its own substantive return blocks. Reuse a worker session only while its previous task context remains appropriate; otherwise launch a fresh clean context. Never use an abbreviated memory reference or inherit the primary conversation.

Obtain the executor's actual individual session identifier from native launch metadata. If unavailable, include only the narrow step needed for the worker to read and return its own native identifier. Do not invent one or substitute a parent/shared-tree ID. This identifier records the executor; it is not authentication or write authority. Cancel an unused, unlaunched preparation explicitly; a launched worker must return substantive findings or its concrete blocker.

## Substantive return

Workers return actual findings, source observations, conditions, method, changes, uncertainty and blockers. A content-creation task returns the content itself, not merely a claim that it exists elsewhere.

The primary immediately divides the return into large, independently meaningful knowledge materials, preserving useful facts and detail. It saves them with `pcw_save_result_blocks`, reads all of them through `pcw_read_many` with the assignment ID, adds useful links and explicitly assesses through `pcw_result_assess`. An extra monolithic copy of the return is not required. The later semantic helper only chooses embedding boundaries inside these materials. See [Memory operations](memory-operations.md) and [Prepare search](prepare-search.md).

A mismatch is an observation to return, not permission to broaden scope. A failed attempt alone does not prove previous knowledge false. Clarification or new authority needed for further work is a concrete blocker. When evidence establishes that active knowledge is wrong, the primary corrects or replaces that knowledge before resolving the discrepancy.

## Factual checks

The primary chooses intermediate/final checks according to task complexity and records timing, scope and criteria with `pcw_task_checks_set`. A mismatch requiring attention triggers an additional check. A return alone does not.

Give a checker the original requirement, allowed real objects, necessary facts, expected observation and concrete conformity criteria. Use purpose `check` and supply the planned `check_id` to `pcw_assignment_prepare`; preparation binds the check, so do not repeat `pcw_task_checks_set` merely to attach the assignment. Revise the plan with a reason when the plan itself changes.

A checker inspects the real source or reproduces behavior, including for no-change research. Inspect an existing artifact before a command that regenerates it, distinguishing that observed state from later reproduction. Return method, observations, mismatch, uncertainty and blocker. The primary saves, reads and assesses the findings. A success assertion, exit code or saved material alone is not factual acceptance.

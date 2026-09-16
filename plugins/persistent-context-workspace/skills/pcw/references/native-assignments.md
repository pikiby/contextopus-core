# Native assignments

The primary supplies a complete task in a separate native context. Use the current tools-map model and reasoning explicitly. In Codex request `fork_turns: "none"`; other environments must supply their equivalent. A clean context is not a filesystem sandbox. This implementation enforces the prohibition through the task contract only.

## Assignment contract

Include goal, necessary facts as text, explicitly allowed real source objects, constraints, expected result, observable criteria and what to return. For edits, identify owned targets and tell the worker that others share the codebase: preserve and accommodate their changes. Do not pass knowledge filenames, IDs, Current, a PCW journal, parent conversation or memory-management instructions. Commands may be included only within the authorized task.

The generated launch message explicitly prohibits using PCW MCP or discovering, opening or changing `.pcw` through any tool, shell or script. Workers execute only stated actions against authorized task sources. They do not save their own reports or perform memory compaction, links, Current or memory Git operations. Those belong to the primary.

Submit the complete assignment to `pcw_action_requirements(action="prepare_assignment")`. Correct its missing prerequisites and repeat until ready. Send only `handoff.launch_message`; the surrounding response contains primary-only coordination data. Bind the actual session using `pcw_assignment_bind` after native launch. Worker-side assignment retrieval through MCP is removed.

A follow-up uses `continuation_of` and a new complete assignment, with fresh facts rather than an abbreviated reference to previous memory. Its substantive return gets a new filename-ID. Do not inherit the primary conversation. Reusing a worker session is permitted only while its own previous context remains appropriate; a clean new worker receives the complete new task as usual.

Obtain the executor's actual individual session identifier from native launch metadata. If the host omits it, include only the narrow step needed for the worker to read its own native identifier and return that value. Do not invent an identifier or substitute a parent/shared-tree ID. The identifier records who produced the result; it is not authentication or write authority.

## Substantive return

Return actual findings, source coordinates, conditions, method, observations, changes, uncertainty and blockers. A content-creation task returns the content itself, not a claim that it was saved elsewhere. The primary saves the unmodified result through `pcw_save_subagent_result`, reads it through `pcw_read`, and assesses it through `process_result`. See [Memory operations](memory-operations.md).

A discovered mismatch is an observation to return, not permission to broaden scope. A failed attempt alone does not prove that previous knowledge is false. Clarification or new authority needed for further work is a concrete blocker.

## Factual checks

The primary chooses intermediate/final checks according to complexity and records their timing, scope and criteria with `pcw_task_checks_set`. A mismatch requiring attention triggers an additional check. A return alone does not.

Give a checker the original requirement, allowed real objects, necessary facts in the task, expected observation and concrete conformity criteria. Use purpose `check`. It verifies the real source or reproduces behavior even when no file changes were requested. It returns the method, observations, mismatch, uncertainty and blocker; the primary saves and reads those findings.

Inspect an existing artifact before a command that can regenerate it. Distinguish its observed state from later reproduction; a check must not hide a defect by rebuilding the artifact first. A success assertion, command exit code or saved material alone is not factual acceptance.

# Native assignments

The primary supplies a complete task in a separate native context. Use the current tools-map model and reasoning explicitly. In Codex request `fork_turns: "none"`; other environments need their equivalent. The access prohibition is part of the assignment contract; a clean context is not a filesystem or OS sandbox.

## Assignment contract

Include the goal, necessary facts as text, explicitly allowed real source objects, constraints, expected result, observable criteria and what to return. For edits, identify owned targets and tell the worker that others share the codebase: preserve and accommodate their changes. Do not pass knowledge filenames, IDs, Current, the task ledger, the parent conversation or memory-management instructions. Commands must remain within the authorized task.

The generated launch message prohibits PCW MCP and any discovery, reading or changing of `.pcw` via tools, shell or scripts. Workers act only on authorized real sources. They return findings to the primary, which owns saving, consolidation, links, Current and memory history.

Call `pcw_assignment_prepare` with the complete assignment and exact published profile. Correct missing prerequisites and retry until ready. Send only `handoff.launch_message`; enclosing coordination data remains primary-only. Bind the actual executor session with `pcw_assignment_bind` after native launch. Workers do not retrieve assignments through MCP.

For a follow-up, use `continuation_of` and register a complete fresh assignment with all needed facts. A continuation is new accountable work with its own substantive return blocks. Reuse a worker session only while its previous task context remains appropriate; otherwise launch a fresh clean context. Never use an abbreviated memory reference or inherit the primary conversation.

Obtain the executor's identity from the actual native launch response or narrowly scoped native metadata. Never ask a worker to discover its identity through shell environment variables: these may contain the parent's ID. If the host returns a canonical task handle instead of a UUID, bind that handle with its parent launch-session scope and native evidence. `pcw_assignment_bind` requires `evidence={source: native_launch|native_metadata, reference: observed response/metadata coordinate, executor_session_id: actual identity}`. Evidence is recorded, not host-authenticated; PCW cannot independently authenticate an arbitrary host response. For a proven mistaken binding, use `pcw_assignment_rebind` with exact assignment IDs, expected old identity, corrected identity, evidence and reason. It corrects result metadata, preserves history and blocks finish after a conflict or interrupted repair. Do not substitute the old ID to pass finish. Cancel an unused, unlaunched preparation explicitly; a launched worker must return findings or its concrete blocker.

Prepared-message transfer belongs to the native environment. Reuse the already prepared launch text; do not recreate the assignment for transfer. If the host supports direct forwarding, use it. The current text-only launcher has no message-reference parameter; do not invent one, claim zero-copy delivery or add a PCW dispatcher. Refresh the capability map when the native interface actually changes. Prefer completion notifications or bounded 30–60-second waits over short polling.

## Substantive return

Workers return actual findings, source observations, conditions, method, changes, uncertainty and blockers. A content-creation task returns the requested content itself in its first response. Before returning, check every requested deliverable. Verify preservation against the file captured before the task and the exact allowed edit, not an unrelated Git HEAD. Missing deliverables must be identified as incomplete.

The primary records incomplete/error returns with `pcw_return_record`, specifying missing deliverables. This permits a continuation without a knowledge file or false acceptance. An accepted continuation names the earlier assignment in `assessment.resolves`. Completed operational evidence with no new reusable knowledge also uses control storage and a separate explicit assessment.

The primary divides substantive new knowledge into independently meaningful topic materials. Use `pcw_result_store` to save bodies, explicit links and verified read-back together, then explicitly assess through `pcw_result_assess`. Keep operational history and redundant artifact copies out of knowledge. Reuse returned `split_sources` for the semantic helper, which only chooses embedding boundaries inside these topic materials. See [Memory operations](memory-operations.md) and [Prepare search](prepare-search.md).

A mismatch is an observation to return, not permission to broaden scope. A failed attempt alone does not prove previous knowledge false. Clarification or new authority needed for further work is a concrete blocker. When evidence establishes that active knowledge is wrong, the primary corrects or replaces that knowledge before resolving the discrepancy.

## Factual checks

The primary chooses intermediate/final checks according to task complexity and records timing, scope and criteria with `pcw_task_checks_set`. A mismatch requiring attention triggers an additional check. A return alone does not.

Give a checker the original requirement, allowed real objects, necessary facts, expected observation and concrete conformity criteria. Use purpose `check` and supply the planned `check_id` to `pcw_assignment_prepare`; preparation binds the check, so do not repeat `pcw_task_checks_set` merely to attach the assignment. Revise the plan with a reason when the plan itself changes.

A checker inspects the real source or reproduces behavior, including for no-change research. Inspect an existing artifact before a command that regenerates it, distinguishing that observed state from later reproduction. Return method, observations, mismatch, uncertainty and blocker. The primary saves, reads and assesses the findings. A success assertion, exit code or saved material alone is not factual acceptance.

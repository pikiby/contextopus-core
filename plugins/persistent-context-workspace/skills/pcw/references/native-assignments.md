# Native assignments

Use the complete `handoff.launch_message` returned by a successful `prepare_assignment`. After launch, the primary binds the actual native session with `pcw_assignment_bind`. The executor calls `pcw_assignment_get` with the registered assignment ID and its own native session ID before any task work. That response, including current context and acceptance criteria, is the authoritative handoff. A follow-up must be registered anew with complete fresh context and `continuation_of`; a shortened message must not substitute for that stored assignment. Status claims require current observations, not a status copied from an earlier turn.

Read after `pcw_action_requirements(..., action="prepare_assignment", ...)` and before a real-source investigation, implementation, Current update, durable knowledge operation, Git operation, or factual check. The primary retains the user conversation, scope, model/reasoning choice, and final decision. It starts the native subagent directly; PCW neither dispatches it nor supplies a Controller or completion hook.

Choose the concrete model and supported reasoning settings from the current tools-map profile and pass both explicitly. Use a clean, prepared context where the host supports it, such as `fork_turns: "none"`; this is not a separate filesystem sandbox. A prepared local task can use a smaller available model when its map profile and the task justify it. Do not manufacture provider rankings or cross-provider effort labels.

Before launching, submit the complete assignment to `pcw_action_requirements(action="prepare_assignment")` with the exact published profile ID. If it returns `ready: false`, correct the listed prerequisites and repeat that call. Receiving the instructions alone does not validate a launch; launch only after `ready: true` for this assignment. The primary still judges the task's suitability and acts within the user's authority.

Every assignment includes:

- one outcome or factual question, the user authority, exact allowed roots, objects, or services, and explicit non-goals;
- the relevant knowledge facts and filename-IDs from MCP, source coordinates when known, and the selected model/reasoning profile with its reason;
- constraints, completion or factual-check criteria, and whether the job is investigation, change, Current/knowledge application, Git, or verification;
- for edits, owned targets and a reminder that other workers share the workspace, so existing concurrent changes must be preserved and accommodated;
- a requested raw Markdown return: findings or changes, real-source coordinates, check method and observations, uncertainty, mismatch, blocker, and any correction to supplied knowledge; for Current, knowledge, preparation, maintenance, or Git operations, require the affected material filename-IDs (and Current path when affected) and their actual completion status; obtain the actual executor identifier from native launch metadata, or ask the worker to include its own native identifier when the launch response omits it.

The worker investigates only the assigned real sources and makes only authorized changes. A read-only task does not grant mutation authority. Existing execution authority does not expand to unrelated outcomes. It applies Current, content, links, compaction, migration, checkpoint, or source changes only when these are part of its prepared assignment. It does not make primary decisions about task scope, acceptance, model selection, or semantic consolidation.

## Result and primary save

The worker itself writes the raw Markdown return. The primary receives it and its actual native session ID, then calls `pcw_save_subagent_result` with the unmodified return before interpreting it. After a confirmed save, the primary calls `pcw_read` and obtains `saved_at` and `executor_session_id`. It may request an addressable clarification through the native host if the saved session remains reachable. A save is neither task acceptance nor a proof that the claimed change exists.

A follow-up return must name the materials actually affected by that follow-up and state their status. Do not redeliver an earlier material list when the affected objects changed. A new raw return from the same executor can replace its earlier raw return under the same filename with `expected_previous_revision`; follow the guarded-save procedure in [Memory operations](memory-operations.md). The worker authors the new text, and the primary passes it unchanged. Reuse an identical return only while its facts, affected IDs, and status remain accurate for the completed assignment.

Use the identifier of the individual executor, not a shared parent/session-tree identifier or an invented value. In the verified Codex native environment, the worker's `CODEX_THREAD_ID` identifies its own thread; `CODEX_SESSION_ID` can identify the shared parent tree. If launch metadata does not expose the individual identifier, include a first step in the assignment: read that native metadata value before opening task materials, retain it, and return it unchanged. This identifies the executor; it is not an additional factual check of the task. Prefer an individual identifier exposed by the native host over an identifier written inside a material. A task path alone is not evidence of session identity. Other environments may expose a different native identifier; verify its meaning rather than requiring a Codex-specific format. If no actual identifier is available, report that gap instead of fabricating one.

When the worker finds a real mismatch with knowledge, it establishes the cause within scope and returns the observation. A failed attempt alone does not prove knowledge stale. If the needed continuation requires new user authority or a material user choice, return facts and the exact blocker; do not proceed. The primary decides the next assignment, compaction, content, links, and acceptance after reading the saved result.

When reporting an executor identifier after reading other workers' materials, reread the native metadata immediately before the final return and copy that fresh value unchanged. In the verified Codex shell, `printenv CODEX_THREAD_ID` reads only this value. A newly started executor reporting the individual ID already associated with a different native executor is an identity conflict; clarify it from native metadata before the primary save. An actual follow-up to the same executor keeps its original ID.

## Factual check assignment

The primary schedules checks at planned moments chosen from complexity, or when a saved return shows a mismatch that needs attention. It does not schedule one automatically for every return. Give the checker the original requirement, object to verify, expected result, observable conformity criteria, allowed scope, and relevant filename-IDs.

The checker reproduces the behavior or verifies real sources. For research with no intended change, it still verifies the requested factual conclusion against real sources. Its raw return states the method, observations, conformity or mismatch, uncertainty, and blocker. The primary saves then reads this return in the same order before deciding to accept, correct within authority, continue, or report a gap. A successful command, a test label, or a worker assertion without the observed source result is not sufficient factual evidence.

When checking an existing artifact, inspect and record its actual state before running any authorized command that could regenerate or replace it. Distinguish the originally observed result from a later reproduction; use separate outputs where needed and permitted. A check must not erase an existing mismatch by rebuilding the artifact before observing it.

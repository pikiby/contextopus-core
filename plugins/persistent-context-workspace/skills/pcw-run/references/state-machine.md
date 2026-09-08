# Execution rules

These instructions belong only to `pcw-run`. Execute an existing task; do not author or refine it.

## Clean handoff

Interpret the invocation to select the existing workspace, exact run request, target scope, and current authority. Do not rebuild Current from the invocation or old chat. Missing workspace or Current returns `workspace_missing` or `context_insufficient`.

Start a fresh Controller with no inherited conversation. In Codex use `fork_turns: none`. If clean isolation is unavailable, return `clean_controller_unavailable`; never fall back to executing in the primary agent's earlier context.

Pass only:

- the exact current run request;
- the absolute workspace and source roots;
- the complete prepared `current.md`, including its Task lock, knowledge links, and source coordinates;
- the exact mutation scope and current authority;
- the complete required instruction set listed by the entrypoint.

Do not pass chat summaries, earlier messages, unrelated memory, or the primary agent's interpretation. The Controller reads Current completely before source inspection or delegation.

## Execution

Current's Task lock, task identity, outcome, scope, exclusions, user constraints, and plan remain fixed. The effective authority is limited by both the prepared task and the user's current authorization. New information can supply implementation detail, not new goals, audiences, deliverables, lifecycle phases, or permission.

Read a small precise target directly. For missing detail across a broad source, use `pcw-inspect-source` and give a Reader one exact question with Current's relevant knowledge links and source coordinates. The Reader returns one merged answer under the shared routing rules.

If a required fact, scope, or authority remains missing or contradictory, return `context_insufficient`, `context_scope_conflict`, or `needs_input` through the primary agent. Do not silently choose a broader task or expand a search to justify it.

The Controller may perform a simple task itself or create Workers from its clean context. Give each Worker the complete Current, relevant compact Reader answers, exact owned targets, and authority. Do not assign concurrent writers to the same files or live objects. Workers do not change task identity, scope, constraints, authority, or plan.

There is no required preflight audit, requirement-mapping report, post-execution review, or acceptance loop. Run tests or verification only when they are part of the user-requested task. Do not invent successful results when work fails.

## Persist results

Write useful cross-task results directly into their existing knowledge records or new records with available attribution. Update Current only with factual execution state, blockers, and status; do not independently change its task or plan. Leave unrelated content unchanged.

Intermediate Reader and Worker answers stay in the agents' working contexts. Do not create a process journal, result staging directory, or temporary files for resuming the run. Legacy temporary files are left untouched.

Use the shared checkpoint operation for this request's durable memory changes. Return the actual result, changed targets, blockers, uncertainty, and commit id directly to the primary agent. It relays this answer without a separate semantic acceptance step.

## Interruption

An interrupted run may leave memory or source edits uncommitted. No saved stage or all-or-nothing recovery is available. Do not claim that Git restores external actions or lost in-memory results, and do not automatically replay external side effects. Ask when the known state is insufficient to continue safely.

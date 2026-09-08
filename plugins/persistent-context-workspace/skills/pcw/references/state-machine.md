# Context editing rules

These instructions belong only to `pcw`. They define context creation and editing, not task execution.

## Interpret the request

Take project identity, paths, requested knowledge, task changes, exclusions, constraints, and authority from the complete current user request.

Do not improve, broaden, complete, or reinterpret the request on the user's behalf. An old plan, adjacent defect, best practice, or discovered infrastructure detail does not create a new goal, audience, deliverable, or lifecycle phase. Ask only when missing meaning would select a materially different workspace, task, or result.

Distinguish meaning while writing:

- `user`: an outcome, scope, exclusion, constraint, or authority explicitly supplied by the user;
- `derived`: an implementation detail grounded in available evidence and necessary inside the requested outcome;
- `fact`: supporting information, not a new requirement;
- `unresolved`: an inference or material choice that remains non-binding until the user resolves it.

This is a writing rule, not an additional review phase or a requirement-mapping report.

## Create missing memory

Create a workspace only when the user clearly asks to establish new context. Otherwise return `workspace_missing`.

Initialize the semantic directory, its local Git repository, request-derived `current.md`, and `knowledge/index.md`. Add the parent ignore rule needed to keep `.pcw/` out of source-project Git. Do not create placeholder process files.

An incomplete user task may remain `Status: draft` with its open questions; do not invent the missing outcome.

## Choose the durable owner

- For a request to retain durable cross-task knowledge or correct an existing record, edit `knowledge/` and its entry links.
- For a task, scope, constraint, authority, plan, blocker, or status change, edit Current.
- A knowledge-only request does not establish a new task, replace its Task lock, or trigger automatic rebuilding of Current.
- A task-only refinement does not also create a duplicate knowledge record.
- Save supplied content with its attribution and requested division. Do not turn a save request into research, idea evaluation, or an unsolicited rewrite.

## Refine Current

Preserve the task-establishing `Verbatim request`. Apply later refinements by replacing the affected active field or paragraph, not by appending message history, a `Latest verbatim refinement` field, or another copy of the same meaning. A user-established replacement task supplies a new verbatim request.

Keep explicit user constraints verbatim. Preserve unaffected task, scope, authority, and plan fields. Keep unresolved material as an open question instead of choosing a broader interpretation.

Keep only meaning needed for the task. A simple clarification should not materially grow Current; new active meaning may. Do not remove a required constraint to meet the size budget.

Replacing or closing an active task requires the user's request. An explicitly closed task remains in Current with `Status: closed`.

## Workflow

Resolve workspace → select relevant existing context → gather source information only if needed → write the requested durable changes → local memory commit.

No additional review or temporary process stage lies between writing and the commit. A tool error remains an error; do not report the corresponding operation as completed.

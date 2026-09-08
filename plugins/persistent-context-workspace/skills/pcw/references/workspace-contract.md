# Shared memory contract

This document contains memory rules used by both entrypoints, not their separate workflows.

## Memory root

Use one semantic subproject directory, not one directory per session:

```text
<work-root>/.pcw/<subproject>/
├── current.md
├── knowledge/
│   ├── index.md
│   └── <object>.md
└── .git/
```

The selected path stays fixed for the request. Memory has its own local Git repository and stays outside source-project Git.

## Knowledge

`knowledge/` holds compact durable objects, facts, rules, constraints, blockers, decisions, and relations useful beyond one task. It is neither raw source storage nor an execution log.

Each record uses:

```yaml
---
id: <stable-slug>
kind: object | fact | rule | constraint | blocker | decision | relation
status: active | resolved | superseded
tags: []
supersedes: []
sources: []
---
```

One record covers one coherent meaning. Update an existing record instead of duplicating it. Retain available source coordinates and attribution; a proposal stays a proposal, a user claim stays attributed, and uncertainty stays explicit. Do not invent facts or sources.

Use `[[knowledge/<id>]]` for workspace-relative links. Relations use `depends_on`, `affects`, `blocked_by`, or `supersedes`. Conflicting and superseded meanings remain explicit; irrelevant-to-task knowledge is not deleted merely to shorten Current.

## Current

`current.md` is the persistent compact context and plan for one active task.

```markdown
# Current

Task: <active task identity and outcome>
Status: draft | ready | running | blocked | complete | closed

## Task lock

Verbatim request: <exact user wording that established or replaced the task>
Required outcome: <outcome supplied by that wording>
In scope: <explicit scope, or "not further specified">
Out of scope: <explicit exclusions, or "not further specified">
User constraints: <verbatim constraints, or "none stated">
Authority: <explicit mutation and external-action authority>
Open questions: <material unresolved choices, or "none">

<compact execution logic, blockers, and factual execution state>

# References

- knowledge: [[knowledge/<id>]]
- evidence: <stable coordinate>
```

Task identity, outcome, scope, exclusions, authority, critical user constraints, blockers, and execution logic belong directly in Current. Linked detail cannot create or expand them. Only the user establishes or changes task meaning.

Give each meaning one durable owner: task-specific meaning belongs in Current, cross-task meaning in knowledge. Link stable detail instead of duplicating it. The default Current budget is about 3,000 tokens, without dropping relevant user constraints. Keep Current after work ends.

## Direct persistence

Write durable changes directly. Neither entrypoint creates or uses `tmp/`, cycle manifests, intermediate result files, receipts, promotion files, snapshots, or cleanup phases. Keep intermediate responses in the agents' working contexts; do not introduce a replacement process journal elsewhere.

Existing legacy temporary files are not a recovery protocol for these skills. Leave them untouched unless the user separately requests their removal.

Git holds committed memory versions. Interrupted writes may remain uncommitted; no exact-stage recovery, all-or-nothing transaction, automatic rollback, or restoration of lost agent context is promised. Do not overwrite or discard pre-existing changes. If their ownership overlaps the request and is unclear, ask the user.

## Authority and Git

- A local memory commit is automatic unless the user explicitly forbids it.
- Commit only this request's durable memory paths. Permitted memory paths are `current.md`, `knowledge/`, and a workspace `.gitignore` when actually needed.
- Source-project commits and every push require explicit user authorization.
- Never store secrets, tokens, or private keys in memory.
- Do not add automatic validation, semantic acceptance, rereading for review, comparison, or tests. Such actions belong only to an explicit user task, not to routine memory handling.
- Report actual operation failures and unresolved questions without inventing success.

## Operation results

Operations return compact results directly to their caller, not files:

```yaml
status: ok | blocked
operation: <operation-name>
workspace: <absolute-path-or-null>
output_state: <resulting-state>
reason: <when blocked>
```

Add only operation-specific result fields. Do not add a `next_action`; the calling entrypoint owns the workflow.

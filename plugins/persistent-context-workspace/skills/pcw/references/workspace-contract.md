# Workspace contract

## 1. Memory root

Use one directory for each semantic subproject:

```text
<work-root>/.pcw/<subproject>/
├── current.md
├── knowledge/
│   ├── index.md
│   └── <object>.md
├── tmp/
│   └── <cycle-id>/
│       ├── manifest.md
│       ├── findings/
│       ├── work/
│       ├── receipts/
│       ├── promotion.md
│       └── current.before.md
└── .gitignore
```

A directory represents a semantic subproject, not a session. Once resolved, the workspace path remains fixed throughout the transaction.

## 2. `knowledge/`

`knowledge/` is the only durable system memory. It stores compact, source-backed objects, facts, rules, constraints, blockers, decisions, and relations that may remain useful when the active task changes. It is neither a raw source copy nor a task-specific Current.

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

One record covers one coherent meaning and retains stable primary coordinates. Update an existing record instead of duplicating it. Express relations as `depends_on`, `affects`, `blocked_by`, or `supersedes`. Preserve user constraints verbatim. Keep user claims about external state attributed until primary evidence verifies them.

## 3. `current.md`

`current.md` is the persistent compressed context and plan for one active task. It is not general project memory and must contain nothing that does not materially affect that task.

Required minimal format:

```markdown
# Current

Task: <active task identity and outcome>
Status: draft | ready | running | blocked | complete | closed

## Task lock

Verbatim request: <exact user wording that established or last changed the task>
Required outcome: <meaning entailed by that wording>
In scope: <explicit scope, or "not further specified">
Out of scope: <explicit exclusions, or "not further specified">
User constraints: <verbatim constraints, or "none stated">
Authority: <explicit mutation and external-action authority>
Open questions: <material unresolved choices, or "none">

<compact supported execution logic, blockers, and factual execution state>

# References

- knowledge: [[knowledge/<id>]]
- evidence: <stable coordinate>
```

Rules:

- Build `current.md` only through `$pcw` from the user's natural request, relevant `knowledge/`, and supported evidence.
- Preserve the request that establishes or changes task meaning verbatim in the Task lock. A summary may clarify it but must not replace, narrow, broaden, or improve it.
- Keep task identity, intended outcome, scope, exclusions, mutation authority, critical user constraints, blockers, and execution logic directly in Current. Retrieval must never be required to discover or change them.
- Use these provenance classes when building or validating Current:
  - `user`: task identity, outcome, scope, exclusion, constraint, authority, audience, deliverable, or quality criterion explicitly supplied by the user;
  - `derived`: an implementation step supported by primary evidence and necessary to achieve a `user` outcome without adding a new subject or lifecycle phase;
  - `fact`: supporting evidence that may guide execution but cannot become a task requirement by itself;
  - `unresolved`: an inference or material choice that remains non-binding until the user resolves it.
- Never treat Reader findings, adjacent defects, general best practices, existing knowledge, or implementation inventory as `user` meaning. A `derived` step must retain its evidence and mapping to the exact requested outcome.
- When the request leaves a material boundary unspecified, write it as an open question and ask. Do not silently select the broader, more complete, or more elaborate interpretation.
- A user may refine it repeatedly. Preserve supported task, scope, constraints, and plan changes until the user changes, replaces, or closes them.
- Do not include unrelated history or knowledge merely because it exists.
- Do not delete it after a run. A run may update only factual execution state and status; it must not independently replan.
- Replacing or closing the active task requires user meaning supplied through `$pcw`.
- Keep stable detail in `knowledge/` and link it instead of copying it into Current. These links are permitted run-time retrieval entry points for exact Reader questions.
- Use a default budget of about 3,000 tokens. Never meet the budget by dropping a relevant user constraint.

## 4. `tmp/`

`tmp/` is the transaction buffer for one active or interrupted context update or run. It stores raw findings, Controller and Worker results, source maps, receipts, promotion input, and the pre-change Current snapshot.

Nothing in `tmp/` is durable fact merely because it was written. After validation, selected meanings move into `knowledge/` and the permitted factual state moves into `current.md`; rejected or transient material is discarded. The exact absorbed cycle directory is then removed. The `tmp/` directory itself remains and is always ignored by Git so an interrupted operation can be recovered before pruning.

## 5. Cycle manifest

Store `tmp/<cycle-id>/manifest.md` as:

```yaml
---
cycle_id: <stable-id>
workspace: <absolute-path>
entry_skill: pcw | pcw-run
status: open
started_at: <ISO-8601 UTC>
request: <verbatim user request>
source_roots:
  - <absolute path or URL>
current_budget_tokens: 3000
absorbed: false
---
```

Allowed `status` values are `open`, `working`, `promotion_ready`, `knowledge_promoted`, `current_compacted`, `validated`, `checkpointed`, `closed`, and `blocked`.

## 6. Accepted result

Store every accepted result in its own Markdown file:

```yaml
---
result_id: <caller-provided-stable-id>
kind: reader | controller | worker | user
cycle_id: <cycle-id>
scope: <exact path, range, object, or user message>
status: complete | partial | blocked
sources:
  - <path:line, byte range, object id, or URL>
---
```

The body contains only user-provided meaning, facts, changes, checks, uncertainty, and coordinates. A `kind: reader` result records its exact question, claim verdicts, relevance classification, compact answer, primary coordinates, conflicts, uncovered scope, and uncertainty; a parent Reader records one merged result rather than forwarding every child report. A final `kind: controller` result records a mapping from every material change or output section to a `user` outcome or evidenced `derived` necessity, the findings excluded as `out_of_scope`, and the primary agent's semantic acceptance. A `kind: user` result preserves exact user meaning and distinguishes authority or constraints from unverified external claims. Do not copy an entire source unless necessary.

## 7. Promotion manifest

`promotion.md` lists every accepted `result_id` exactly once and classifies its meanings:

- `knowledge_changes`: created, updated, superseded, or resolved knowledge records;
- `current_changes`: user-authorized context-plan changes for `$pcw`, or factual execution-state changes for `$pcw-run`;
- `references`: links for Current to retain;
- `ephemeral`: discarded transient details with a short reason;
- `conflicts`: incompatible claims that remain explicit.

## 8. Internal operation envelope

Every internal operation returns:

```yaml
status: ok | blocked
operation: <operation-name>
workspace: <absolute-path-or-null>
cycle_id: <id-or-null>
input_state: <state>
output_state: <state>
artifacts: []
warnings: []
reason: <required when blocked>
```

Never add `next_action`. `output_state` is a postcondition, not a decision about the following transition.

## 9. Git

- A checkpoint may contain `current.md`, `knowledge/`, and the workspace `.gitignore`.
- `tmp/` is always ignored by Git.
- Commit validated paths inside the selected PCW memory repository and prune the exact absorbed cycle automatically unless the user explicitly forbids that transaction.
- Commits outside that memory repository and every push require explicit user authorization.
- Never store secrets, tokens, or private keys in memory.

# Workspace contract

## 1. Memory root

Use one directory for each semantic subproject:

```text
<work-root>/.pcw/<subproject>/
├── current.md
├── knowledge/
│   ├── index.md
│   └── <topic>.md
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

A directory represents a semantic subproject, not a session. Once resolved, the workspace path must remain fixed throughout the cycle.

## 2. `current.md`

Required minimal format:

```markdown
# Current

A dense description of what is currently true and required for correct continuation.

# Pinned

Verbatim active user constraints.

# References

- knowledge: [[knowledge/<id>]]
- blocked_by: [[knowledge/<id>]]
- evidence: <stable coordinate>
```

Rules:

- Do not maintain a journal or list minor completed actions.
- Do not record an assumed next step.
- An explicitly authorized unfinished operation may appear in `Current` when its absence would materially break continuation. Describe only its evidenced target, authorized scope, and factual execution state; this is active state, not a next action.
- Update or remove that operation when it is completed, revoked, replaced, paused, or materially rescoped.
- Do not duplicate details available through a stable link.
- Do not paraphrase `Pinned` without an explicit user change.
- Use a default budget of about 3,000 tokens unless the cycle overrides it.
- If `Pinned` alone exceeds the budget, preserve it completely and return a warning instead of shortening it.

## 3. Cycle manifest

Store `tmp/<cycle-id>/manifest.md` as:

```yaml
---
cycle_id: <stable-id>
workspace: <absolute-path>
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

## 4. Reader, Worker, or user-memory result

Store every accepted result in its own Markdown file:

```yaml
---
result_id: <caller-provided-stable-id>
kind: reader | worker | user
cycle_id: <cycle-id>
scope: <exact path, range, or object>
status: complete | partial | blocked
sources:
  - <path:line, byte range, object id, or URL>
---
```

The body contains only facts, changes, checks, uncertainty, and coordinates. A `kind: user` result preserves the explicit remember payload verbatim and distinguishes user authority or constraints from unverified external claims. Do not copy an entire source unless necessary.

## 5. Knowledge record

```yaml
---
id: <stable-slug>
status: active | resolved | superseded
tags: []
supersedes: []
sources: []
---
```

One record covers one coherent subject. Create a record only when no suitable existing record exists. Express relations as `depends_on`, `affects`, `blocked_by`, or `supersedes`.

## 6. Promotion manifest

`promotion.md` must list every accepted `result_id` exactly once and classify its meanings:

- `current_candidates`: concise confirmed meanings for `Current`;
- `pinned_additions`: only verbatim new user constraints;
- `pinned_removals`: only verbatim revoked constraints with revocation evidence;
- `knowledge_changes`: created or changed knowledge records;
- `references`: links for the compactor to consider;
- `ephemeral`: discarded transient details with a short reason;
- `conflicts`: incompatible claims that must not be silently collapsed.

## 7. Internal subskill envelope

Every internal subskill returns:

```yaml
status: ok | blocked
operation: <skill-name>
workspace: <absolute-path-or-null>
cycle_id: <id-or-null>
input_state: <state>
output_state: <state>
artifacts: []
warnings: []
reason: <required when blocked>
```

Never add `next_action`. `output_state` is a postcondition, not a decision about the next transition.

## 8. Git

- A checkpoint may contain `current.md`, `knowledge/`, and the workspace `.gitignore`.
- `tmp/` is always ignored by Git.
- Commit validated paths inside the selected PCW memory repository and prune the exact absorbed cycle automatically unless the user explicitly forbids that transaction.
- Commits outside that memory repository and every push require explicit user authorization; pruning still requires a receipt with an actual commit id.
- Never store secrets, tokens, or private keys in memory.

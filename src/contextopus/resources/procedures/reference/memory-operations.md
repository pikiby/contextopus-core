# Memory operations

Mutating work operations require an active `cycle_id`. Search, reads, lists, instructions, the project record and history can be read independently without starting a cycle. Tools do not authenticate a human: invocation policy, chat presentation and any required approval are obligations of the cycle agent. Drafts and permanent changes are separate interfaces; no direct create/update/delete/link/restore MCP bypass is exposed.

## Temporary work

`tmp_write(cycle_id, content)` stores ordinary Markdown and returns a generated ID, revision and path. Update that result with its `material_id` and `expected_revision`. Use `tmp_list` for bounded metadata and `tmp_read` for a chosen result. Temporary materials are not embedded or included in permanent search.

All permanent records, including tasks, goals and the project description, use `proposal_prepare/apply`, `read/read_many`, links and shared indexing. Set `type` and optional `status` in a change; type names are open vocabulary. Find relevant state through `search(types=[...], statuses=[...])` rather than remembering task IDs. Update only the selected context's records. Notes and intermediate results remain in tmp; startup/finish clear only the addressed cycle tmp. INSTRUCTIONS is read in full and changed only through the [instructions procedure](procedure:instructions).

## Prepare a permanent change

After completing the task or a substantive part, review the results through vector search by the conclusion and reading suitable existing topics. This review is mandatory even when no permanent write follows. Apply the current workspace's `INSTRUCTIONS.md` for knowledge selection, organization and maintenance; do not substitute a rule copied into this reference.

Call `proposal_prepare(cycle_id, changes, replacements?, proposal_id?, no_changes_reason?, transformations?, summary?)`. It stores a plan and review in tmp; it does not write permanent materials. Each change describes one final topic:

```json
[
  {"key": "new-topic", "content": "# Topic\n\nEstablished result, evidence and conditions.", "links": ["existing.md"]},
  {"material_id": "existing.md", "expected_revision": "revision-from-read", "content": "Revised complete body", "links": ["@new-topic"]}
]
```

- A new topic uses a unique `key` and complete `content`; the plugin generates a stable YAML `id` and a descriptive filename from the heading. An explicit `path` relative to knowledge may choose the filename. `@key` refers to another new topic in this set, including mutual links. Duplicate IDs and destination paths are rejected.
- Required sources use a fenced YAML `sources` block inside `content`, with an unambiguous `reference` and bounded retrieval `instruction`. References are not limited to URLs: files, records, queries and knowledge fragments are supported by the agent's reading procedure. These are separate from navigation `links`. Apply INSTRUCTIONS authoring criteria; preserve blocks when revising/splitting relevant content and show their changes/removals. On receipt follow [required-source reading](procedure:reference/required-sources) regardless of authoring settings.
- An existing topic requires `material_id` and `expected_revision`. Supply changed `content`, complete outgoing `links`, a concise `description`, or a `path` relative to knowledge. Omitted fields are preserved. Renaming keeps the YAML ID and incoming links. Metadata/path-only changes do not reembed. Link targets can belong to another context under the same memory root; returned labels include their workspace. Reading them does not change active rules. Writes affect the selected context; foreign incoming links must be explicitly corrected before deleting their target.
- Deletion uses `material_id`, `expected_revision`, `delete:true` without other changes on that entry.
- A merge supplies the final survivor plus deleted entries and `replacements: {"old.md": "survivor.md"}`. A split supplies the revised original and new topics. A replacement target may be `@key`. Declare `transformations: [{"kind": "merge", "sources": ["first.md", "second.md"], "targets": ["@combined"]}]`, or `kind: "split"` with one source and multiple targets. Include a retained source ID in targets. Supply a concise one-line `summary`. These provenance declarations enter the reviewed revision and Git commit, and must be shown with the changed passages. Follow [History and analytics](procedure:reference/history-analytics).
- Incoming link removal/redirection is computed before application and included in the review. The apply checks complete file fingerprints, including links and paths, so concurrent navigation changes also conflict.
- To revise an unapplied proposal, supply its `proposal_id`. The returned revision changes; earlier approval cannot apply the revised contents.

If comparison establishes that nothing needs changing, pass `changes: []` with a nonempty `no_changes_reason` explaining that result. The tool records `status: no_changes` in tmp; explain the reason to the user. This requires no approval, apply call, knowledge write or embeddings. It is not a substitute for searching and comparing. Preparation binds the review to the current temporary material contents and INSTRUCTIONS.md revision. A changed instructions revision requires reading the rules and preparing the knowledge review again. New or changed temporary results require another review before closure.

The response contains the proposal ID/revision, created-ID map, review path, structural effects and `review_changes`. Each review entry identifies its topic and paths, contains exact before/after body passages with nearby context, and names added/removed link targets. Creates/deletions contain the complete added/removed body; unchanged bodies are omitted. Automatic incoming-link changes are included. `proposal_read` also returns these entries when retrieving a saved proposal; no extra read is needed immediately after preparation.

Present the actual changes in chat according to `INSTRUCTIONS.md`: topic names, full new text or exact before/after passages, deletions, moves and link effects. A file link, UUID, tool log or general summary does not replace the changed content. Large proposals may span messages. Present the full scope in both approval modes; ask only when the workspace requires approval. The review file is supplementary.

## Apply under the workspace policy

If `material_max_tokens` is configured, preparation counts each final body with the index tokenizer. A `needs_split` response lists the exact oversized entries and counts, without writing knowledge or saving an applicable proposal. Revise semantic topics and prepare again; the limit never chooses the meaning boundaries for the agent.

`proposal_apply(cycle_id, proposal_id, expected_revision, confirmation?)` applies the previously shown version. The boolean `knowledge_approval_required` in INSTRUCTIONS.md frontmatter selects the mode. With `true`, wait for approval of the shown revision and pass the actual user message as `confirmation`; silence, saved approvals and self-approval do not qualify. With `false`, apply after presenting the changes without waiting or supplying confirmation. Missing setting retains required approval for existing/custom instructions; malformed settings are errors. The packaged template sets the initial value. Preparation returns `approval_required` and the corresponding `next_action`. The policy is read from instructions, never chosen in the apply arguments. Instruction edits follow the independent `instructions_approval_required` setting in current instructions (missing means true), through the instructions procedure. A proposed change to false still requires approval under current true rules.

The plugin validates the full affected set before writing, writes survivors and incoming links before deletion, then indexes changed bodies. Links-only and unchanged-body updates do not reembed. A partial failure preserves tmp and the same proposal; retry that operation rather than generating duplicate materials. An already-started authorized application can finish recovery if instructions subsequently change; closure still requires a result review under the current instructions. An external conflict requires reinspection, a new proposal, presentation and approval if the policy requires it. An already applied retry returns its receipt without writing again.

Discard an exact rejected/unneeded unapplied proposal with `proposal_discard`. Discard changes no permanent knowledge and leaves temporary evidence until closure. Do not label partial application as rejection or completion.

## Close or restart

`finish(cycle_id)` closes the cycle and deletes all its tmp only after the current results have completed memory review and the task and memory discussion are complete. Call it without requesting separate permission; the tool has no `confirmation` parameter. Prepared proposals must be applied or discarded. Without a matching review, or with unfinished applications/indexing or pending required approval, closure is blocked and tmp stays intact. A recorded no-change review and rejected updates need no fake permanent write. The check establishes that preparation covered the current tmp revision; it cannot judge the truth of the agent's explanation or authenticate human approval. An older proposal without a tmp revision needs a fresh review before normal closure. `cancel:true` is for actual user cancellation: it deletes temporary context, reports incomplete operation IDs, and does not roll back already written knowledge. Report the actual cleanup result in the conversation language.

For a new explicit invocation use a fresh `request_id` with `startup`. Only if restarting a specific old task, pass its `restart_cycle_id`: its returns, temporary task state, proposals and permission state are removed. Never choose a different active cycle as the cleanup target. Startup/finish retries are idempotent and do not erase subsequent work. Cycle IDs are not native session IDs; a clean-context cycle agent can use the same cycle.

## History and older workspaces

When enabled in INSTRUCTIONS, local Git captures permanent data automatically. `history_list/search/changes/diff/read` expose older versions and declared transformations; restoration is an ordinary shown proposal. `history_retry` uses immutable saved snapshots after a failed commit. Legacy manual `checkpoint` accepts only exact knowledge paths with separate user authority. Tmp, analytics and runtime state are excluded. See [History and analytics](procedure:reference/history-analytics).

Opening checks format without hidden migration or creation. On incompatibility immediately run upgrade, then resume. It preserves IDs, factual content, links and custom instructions while converting filename identity to YAML, legacy source syntax and the shared RAG. Legacy Current content and PROJECT are migrated into typed records, preserving IDs and pending proposals; semantic rewriting is separate requested work. Missing derived storage uses recovery or upgrade; missing knowledge remains blocked. Never create a replacement empty memory to bypass incompatibility.

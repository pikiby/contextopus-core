# Memory operations

All calls after startup require the active `cycle_id`. Tools do not authenticate a human: explicit invocation, chat presentation and any required approval are obligations of the cycle agent. Drafts and permanent changes are separate interfaces; no direct create/update/delete/link/restore MCP bypass is exposed.

## Temporary work

`pcw_tmp_write(cycle_id, content)` stores ordinary Markdown and returns a generated ID, revision and path. Update that result with its `material_id` and `expected_revision`. Use `pcw_tmp_list` for bounded metadata and `pcw_tmp_read` for a chosen result. Temporary materials are not embedded or included in permanent search.

Task goals, progress, blockers and notes are ordinary temporary Markdown written through `pcw_tmp_write`; there is no fixed Current schema. Knowledge writes preserve temporary results. Startup and finish clear only the addressed cycle tmp. The workspace's persistent `INSTRUCTIONS.md` remains outside tmp, is returned by startup and is read again through `pcw_instructions_read` when needed. Changes to it follow only the [instructions-edit skill](../../pcw-instructions/SKILL.md), never a knowledge proposal.

## Prepare a permanent change

After completing the task or a substantive part, review the results through vector search by the conclusion and reading suitable existing topics. This review is mandatory even when no permanent write follows. Apply the current workspace's `INSTRUCTIONS.md` for knowledge selection, organization and maintenance; do not substitute a rule copied into this reference.

Call `pcw_proposal_prepare(cycle_id, changes, replacements?, proposal_id?, no_changes_reason?)`. It stores a plan and review in tmp; it does not write permanent materials. Each change describes one final topic:

```json
[
  {"key": "new-topic", "content": "# Topic\n\nEstablished result, evidence and conditions.", "links": ["existing.md"]},
  {"material_id": "existing.md", "expected_revision": "revision-from-read", "content": "Revised complete body", "links": ["@new-topic"]}
]
```

- A new topic uses a unique `key` and complete `content`; the plugin generates its filename-ID. `@key` refers to another new topic in this set, including mutual links.
- An existing topic requires `material_id` and `expected_revision`. Supply changed `content`, complete outgoing `links`, or a `path` relative to knowledge. Omitted fields are preserved. Moving preserves the filename-ID.
- Deletion uses `material_id`, `expected_revision`, `delete:true` without other changes on that entry.
- A merge supplies the final survivor plus deleted entries and `replacements: {"old.md": "survivor.md"}`. A split supplies the revised original and new topics. A replacement target may be `@key`.
- Incoming link removal/redirection is computed before application and included in the review. The apply checks complete file fingerprints, including links and paths, so concurrent navigation changes also conflict.
- To revise an unapplied proposal, supply its `proposal_id`. The returned revision changes; earlier approval cannot apply the revised contents.

If comparison establishes that nothing needs changing, pass `changes: []` with a nonempty `no_changes_reason` explaining that result. The tool records `status: no_changes` in tmp; explain the reason to the user. This requires no approval, apply call, knowledge write or embeddings. It is not a substitute for searching and comparing. Preparation binds the review to the current temporary material contents and INSTRUCTIONS.md revision. A changed instructions revision requires reading the rules and preparing the knowledge review again. New or changed temporary results require another review before closure.

The response contains the proposal ID/revision, created-ID map, review path, structural effects and `review_changes`. Each review entry identifies its topic and paths, contains exact before/after body passages with nearby context, and names added/removed link targets. Creates/deletions contain the complete added/removed body; unchanged bodies are omitted. Automatic incoming-link changes are included. `pcw_proposal_read` also returns these entries when retrieving a saved proposal; no extra read is needed immediately after preparation.

Present the actual changes in chat according to `INSTRUCTIONS.md`: topic names, full new text or exact before/after passages, deletions, moves and link effects. A file link, UUID, tool log or general summary does not replace the changed content. Large proposals may span messages. Present the full scope in both approval modes; ask only when the workspace requires approval. The review file is supplementary.

## Apply under the workspace policy

`pcw_proposal_apply(cycle_id, proposal_id, expected_revision, confirmation?)` applies the previously shown version. The boolean `knowledge_approval_required` in INSTRUCTIONS.md frontmatter selects the mode. With `true`, wait for approval of the shown revision and pass the actual user message as `confirmation`; silence, saved approvals and self-approval do not qualify. With `false`, apply after presenting the changes without waiting or supplying confirmation. Missing setting retains required approval for existing/custom instructions; malformed settings are errors. The packaged template sets the initial value. Preparation returns `approval_required` and the corresponding `next_action`. The policy is read from instructions, never chosen in the apply arguments. Instruction edits always require approval through the mini-skill.

The plugin validates the full affected set before writing, writes survivors and incoming links before deletion, then indexes changed bodies. Links-only and unchanged-body updates do not reembed. A partial failure preserves tmp and the same proposal; retry that operation rather than generating duplicate materials. An already-started authorized application can finish recovery if instructions subsequently change; closure still requires a result review under the current instructions. An external conflict requires reinspection, a new proposal, presentation and approval if the policy requires it. An already applied retry returns its receipt without writing again.

Discard an exact rejected/unneeded unapplied proposal with `pcw_proposal_discard`. Discard changes no permanent knowledge and leaves temporary evidence until closure. Do not label partial application as rejection or completion.

## Close or restart

`pcw_finish(cycle_id)` closes the cycle and deletes all its tmp only after the current results have completed memory review and the task and memory discussion are complete. Call it without requesting separate permission; the tool has no `confirmation` parameter. Prepared proposals must be applied or discarded. Without a matching review, or with unfinished applications/indexing or pending required approval, closure is blocked and tmp stays intact. A recorded no-change review and rejected updates need no fake permanent write. The check establishes that preparation covered the current tmp revision; it cannot judge the truth of the agent's explanation or authenticate human approval. An older proposal without a tmp revision needs a fresh review before normal closure. `cancel:true` is for actual user cancellation: it deletes temporary context, reports incomplete operation IDs, and does not roll back already written knowledge. Report the actual cleanup result in the conversation language.

For a new explicit invocation use a fresh `request_id` with `pcw_startup`. Only if restarting a specific old task, pass its `restart_cycle_id`: its returns, temporary task state, proposals and permission state are removed. Never choose a different active cycle as the cleanup target. Startup/finish retries are idempotent and do not erase subsequent work. Cycle IDs are not native session IDs; a clean-context cycle agent can use the same cycle.

## History and older workspaces

`pcw_checkpoint` accepts only exact permanent knowledge Markdown paths and needs separate user authorization. Tmp and runtime state cannot enter memory Git history. `pcw_history_read` reads historical text; restoration is an ordinary reviewed proposal, not an immediate overwrite.

Existing knowledge IDs, content and links are preserved on upgrade. Legacy workspace-root Current and old control records remain on disk but are not resumed as cycle context or authority. Opening does not migrate those files. Missing derived storage uses `pcw_recover_workspace`; missing knowledge remains blocked, not silently recreated. Legacy UUID links remain readable via filename identity; applied topic updates write canonical navigation links.

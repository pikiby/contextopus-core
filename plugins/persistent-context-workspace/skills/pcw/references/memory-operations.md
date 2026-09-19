# Memory operations

All calls after startup require the active `cycle_id`. Tools do not authenticate a human: explicit invocation and approval are obligations of the cycle agent. Drafts and permanent changes are separate interfaces; no direct create/update/delete/link/restore MCP bypass is exposed.

## Temporary work

`pcw_tmp_write(cycle_id, content)` stores ordinary Markdown and returns a generated ID, revision and path. Update that result with its `material_id` and `expected_revision`. Use `pcw_tmp_list` for bounded metadata and `pcw_tmp_read` for a chosen result. Temporary materials are not embedded or included in permanent search.

Current lives in `tmp/<cycle-id>/current.md`. `pcw_current_get` reads its five fields; `pcw_current_set` updates supplied fields and returns a compact verified receipt. Knowledge writes preserve Current and all temporary results. Start and explicit finish clear only the addressed work area. A new explicit invocation never resumes an earlier approval or implicitly consumes an old return.

## Prepare a permanent change

After vector search by the conclusion and reading suitable existing topics, call `pcw_proposal_prepare(cycle_id, changes, replacements?, proposal_id?)`. It stores a plan and review in tmp; it does not write permanent materials. Each change describes one final topic:

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
- Incoming link removal/redirection is computed before approval and included in the review. The apply checks complete file fingerprints, including links and paths, so concurrent navigation changes also conflict.
- To revise an unapplied proposal, supply its `proposal_id`. The returned revision changes; earlier approval cannot apply the revised contents.

The response contains the proposal ID/revision, created-ID map, readable review path and structural/link effects. Present the exact resulting changes to the user. `pcw_proposal_read` returns the full review when needed; do not load it merely to repeat supplied text. One topic need not contain every fact from the task, and each fact need not become a separate topic.

## Approve and apply

`pcw_proposal_apply(cycle_id, proposal_id, expected_revision, confirmation)` applies the previously shown version only after the human's direct approval. `confirmation` carries the current user's actual message; supplying text does not prove its origin. Questions, silence, general task authority, saved past approvals and self-approval do not authorize this operation.

The plugin validates the full affected set before writing, writes survivors and incoming links before deletion, then indexes changed bodies. Links-only and unchanged-body updates do not reembed. A partial failure preserves tmp and the same proposal; retry that operation rather than generating duplicate materials. An external conflict requires reinspection, a new proposal and approval. An already applied retry returns its receipt without writing again.

Discard an exact rejected/unneeded unapplied proposal with `pcw_proposal_discard`. Discard changes no permanent knowledge and leaves temporary evidence until closure. Do not label partial application as rejection or completion.

## Close or restart

`pcw_finish(cycle_id, confirmation)` requires the user's explicit agreement to close and delete all cycle tmp. Prepared proposals must be applied or discarded; unfinished applications/indexing block normal closure. No-change and rejected-update cycles close without a fake permanent write. `cancel:true` is for actual user cancellation: it deletes temporary context, reports incomplete operation IDs, and does not roll back already written knowledge.

For a new explicit invocation use a fresh `request_id` with `pcw_startup`. Only if restarting a specific old task, pass its `restart_cycle_id`: its returns, Current, proposals and permission state are removed. Never choose a different active cycle as the cleanup target. Startup/finish retries are idempotent and do not erase subsequent work. Cycle IDs are not native session IDs; a clean-context cycle agent can use the same cycle.

## History and older workspaces

`pcw_checkpoint` accepts only exact permanent knowledge Markdown paths and needs separate user authorization. Tmp, Current and runtime state cannot enter memory Git history. `pcw_history_read` reads historical text; restoration is an ordinary reviewed proposal, not an immediate overwrite.

Existing knowledge IDs, content and links are preserved on upgrade. Legacy workspace-root Current and old control records remain on disk but are not resumed as cycle context or authority. Opening does not migrate those files. Missing derived storage uses `pcw_recover_workspace`; missing knowledge remains blocked, not silently recreated. Legacy UUID links remain readable via filename identity; approved topic updates write canonical navigation links.

# Persistent Context Workspace

Version 0.9.0 provides project knowledge through explicit cycles: permanent Markdown topics, temporary working context, human-reviewed changes and automatic token-window embeddings in LanceDB. It works over standard MCP without requiring a particular agent host or native session identifier.

The [governing document](docs/context-workspace-design-v2.md) defines the current cycle. The [previous design](docs/context-workspace-design.md) and older assessments remain historical references. See [release notes](CHANGELOG.md).

## Work cycle

1. The user explicitly invokes `$pcw` or requests PCW for a task. Mentions and previous invocations do not activate it.
2. `pcw_startup` opens an independent cycle and clears its tmp. It returns a cycle ID, fresh Current and bounded knowledge status without loading weights. Reuse the request ID only for retries; a new invocation has a fresh ID. Explicitly restarting previous work names only that old cycle for cleanup.
3. Search permanent knowledge and read relevant whole topics and links before external investigation. Conversation context does not replace PCW reading.
4. Work directly or delegate as applicable. Save results, worker returns and working notes in tmp. A clean-context subagent may perform the full cycle with the same instructions while the main agent relays the user's messages.
5. Search by the conclusion, read related topics, and prepare precise additions, corrections, compaction and links through `pcw_proposal_prepare`. It writes a reviewable proposal in tmp without changing knowledge.
6. Present the actual changes and mechanical link effects. Questions and revisions continue the discussion. Only after explicit human approval, apply the exact proposal revision through `pcw_proposal_apply`. **Knowledge writes preserve tmp.**
7. After agreement to close the cycle, `pcw_finish` deletes all cycle tmp. Prepared proposals must be applied or discarded; unfinished application/indexing blocks normal closure. Closing without memory changes needs no dummy write. Explicit user cancellation reports unfinished operations without rolling back knowledge.

The skill prohibits calls outside an explicit cycle. The MCP runtime requires an active cycle and binds writes to exact prepared revisions, but it cannot authenticate whether an agent-supplied confirmation came from a human. Host permissions may strengthen that boundary; no universal chat hook or sandbox isolation is claimed.

## Storage and recovery

```text
<work-root>/.pcw/<workspace>/
  knowledge/<generated-id>.md
  tmp/<cycle-id>/
    current.md
    materials/<generated-id>.md
    proposals/<proposal-id>.json
    proposals/<proposal-id>.md   # readable review
  .pcw-runtime/                 # derived index/configuration
  .git/                         # only after an authorized memory checkpoint
<work-root>/.pcw/.control/<workspace>/
  cycles.json                   # IDs, states, revisions; no retained draft bodies
```

Other active cycles are not cleared. A fresh cycle does not inherit old Current, temporary results or permissions. Startup and closure retries cannot erase later work. Temporary materials and proposals never enter permanent vector search or memory Git checkpoints.

Proposals preserve existing filename IDs and can create, update, move, delete, merge or split topics with exact links. New-topic keys allow links between newly created materials. Complete affected-file fingerprints detect concurrent body, path and link changes. Incoming links are rewritten before deletion. Multi-file writes report partial state rather than claiming rollback or all-or-nothing filesystem transactions; retrying the same operation does not duplicate materials.

If indexing fails, saved knowledge and tmp remain. Repair the cause and retry the same proposal, or reconcile derived indexing before retrying apply. History restoration uses `pcw_history_read` followed by a reviewed proposal. Existing knowledge is preserved on upgrade; legacy root Current and older orchestration records are not resumed. Missing permanent storage is reported as a recovery problem, never silently recreated.

## Embeddings

Default: local `Qwen/Qwen3-Embedding-0.6B`, pinned revision, 1024 dimensions, CPU. Overlapping token windows default to 512/64 tokens. Other sentence-transformers models, Ollama or explicitly configured embedding APIs are supported with compatible tokenizers. No boundary-generation agent is needed.

Only approved permanent text is indexed. Unchanged bodies, link edits and moves preserve embeddings. Provider or chunking changes rebuild an inactive table and activate it after source revision checks; failure retains the previous configuration. API credentials are referenced by environment-variable name, not stored in knowledge. See [embedding configuration](plugins/persistent-context-workspace/skills/pcw/references/embeddings.md).

## Upgrade

0.9.0 changes the MCP API: callers pass cycle_id, permanent mutations use proposal preparation/application, and Current belongs to cycle tmp. Old immediate-write tools are no longer exposed. Start a new host session for the changed skill/tool definitions.

For the existing Git marketplace tracking this repository:

```bash
codex plugin marketplace upgrade persistent-context-workspace
codex plugin add persistent-context-workspace@persistent-context-workspace
```

These are installation commands, not actions performed by this source update. Portable hosts use the packaged plugin and `mcp.json`. Startup never installs Python dependencies or downloads model weights. Read [setup](plugins/persistent-context-workspace/skills/pcw/references/setup.md) for a concrete setup failure.

## Verification

The tests retain the existing storage/token-window regressions and add cycle isolation, proposal review/conflicts, partial failure/retry and full cleanup tests. The standard-MCP launcher test uses a temporary workspace. Opt-in real-agent host tests exercise reading and tmp retention before approval, followed by application after a separate human-message turn. Static and deterministic tests do not establish model compliance in every host.

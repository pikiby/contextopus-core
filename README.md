# Persistent Context Workspace

Version 0.10.0 provides project knowledge through explicit cycles: permanent Markdown topics, temporary working context, configurable knowledge approval and automatic token-window embeddings in LanceDB. It works over standard MCP without requiring a particular agent host or native session identifier.

The [governing document](docs/context-workspace-design-v2.md) defines the current cycle. The [previous design](docs/context-workspace-design.md) and older assessments remain historical references. See [release notes](CHANGELOG.md).

## Project instructions and work cycle

Current is replaced by persistent `<work_root>/.pcw/<workspace>/INSTRUCTIONS.md`. Its free Markdown is the workspace's primary project guidance. The single [default template](plugins/persistent-context-workspace/pcw_runtime/default_instructions.md) is copied only on initial creation; existing user instructions are not merged with it or reset.

The main [pcw skill](plugins/persistent-context-workspace/skills/pcw/SKILL.md) requires explicit invocation, reads the complete instructions returned by startup, then searches and reads project knowledge. Work results and task state go to tmp. Before closure, the agent reviews results against knowledge according to `INSTRUCTIONS.md`, prepares changes or an explained empty result, presents actual changes in chat, and applies the exact shown revision according to `knowledge_approval_required` in INSTRUCTIONS.md frontmatter. The default template sets `false`: show changes and apply without asking. Set `true` to require user approval; existing files without the setting retain required approval. Changes to INSTRUCTIONS.md always require explicit approval. Finish clears cycle tmp without a separate closure question and preserves instructions and knowledge.

The [pcw-instructions mini-skill](plugins/persistent-context-workspace/skills/pcw-instructions/SKILL.md) is the single procedure for direct requests to edit project rules, including requests routed from the main skill. A standalone instructions cycle uses `purpose="instructions"`; it does not run ordinary work or write knowledge. Project policies are not duplicated in the skills or MCP prompts. Tools bind revisions but cannot authenticate the human origin of a confirmation.

Context creation and switching require an unambiguous user instruction. The agent keeps the established workspace, asks if the intended context is unclear and checks that an existing workspace is present before startup; it must not probe guessed names with a tool that can create storage. The [pcw-create mini-skill](plugins/persistent-context-workspace/skills/pcw-create/SKILL.md) helps choose a new context's location and task in ordinary language. The main `pcw` routes explicit functional requests to all additional skills: "PCW create a context for this task" opens creation, and "PCW update the instructions" opens instructions editing. Users do not need to name the mini-skill. These are agent instructions, not a runtime guarantee of correct selection.

## Storage and recovery

```text
<work-root>/.pcw/<workspace>/
  INSTRUCTIONS.md               # persistent project guidance
  knowledge/<generated-id>.md
  tmp/<cycle-id>/
    materials/<generated-id>.md
    proposals/<proposal-id>.json
    proposals/<proposal-id>.md   # readable review
  .pcw-runtime/                 # derived index/configuration
  .git/                         # only after an authorized memory checkpoint
<work-root>/.pcw/.control/<workspace>/
  cycles.json                   # IDs, states, revisions; no retained draft bodies
  instructions-initialized.json # prevents silent recreation of lost user rules
```

Other active cycles are not cleared. A fresh cycle does not inherit temporary results or permissions. Startup and closure retries cannot erase later work. Temporary materials and proposals never enter permanent vector search or memory Git checkpoints.

Proposals preserve existing filename IDs and can create, update, move, delete, merge or split topics with exact links. New-topic keys allow links between newly created materials. Complete affected-file fingerprints detect concurrent body, path and link changes. Incoming links are rewritten before deletion. Multi-file writes report partial state rather than claiming rollback or all-or-nothing filesystem transactions; retrying the same operation does not duplicate materials.

If indexing fails, saved knowledge and tmp remain. Repair the cause and retry the same proposal, or reconcile derived indexing before retrying apply. History restoration uses `pcw_history_read` followed by a reviewed proposal. Existing knowledge is preserved on upgrade; legacy root Current and older orchestration records are not resumed. Missing permanent storage is reported as a recovery problem, never silently recreated.

## Embeddings

Default: local `Qwen/Qwen3-Embedding-0.6B`, pinned revision, 1024 dimensions, CPU. Overlapping token windows default to 512/64 tokens. Other sentence-transformers models, Ollama or explicitly configured embedding APIs are supported with compatible tokenizers. No boundary-generation agent is needed.

Only applied permanent text is indexed. Unchanged bodies, link edits and moves preserve embeddings. Provider or chunking changes rebuild an inactive table and activate it after source revision checks; failure retains the previous configuration. API credentials are referenced by environment-variable name, not stored in knowledge. See [embedding configuration](plugins/persistent-context-workspace/skills/pcw/references/embeddings.md).

## Upgrade

The 0.10.0 API removes `pcw_current_get`, `pcw_current_set` and startup's fixed goal/constraints/completion arguments. Startup accepts `purpose` and returns `instructions` with full Markdown and its revision. Task state is ordinary temporary material. Instructions have separate read/prepare/apply tools and survive cleanup. Legacy Current files are preserved but never loaded as project rules. A previously initialized missing instructions file is reported, not silently reset. Pending knowledge proposals bind the instructions revision; changes to rules require fresh preparation.


0.9.2 removes the `confirmation` argument from `pcw_finish`; use `pcw_finish(cycle_id)` when the cycle is complete. Knowledge application still requires approval of the presented proposal.

0.9.3 requires preparation covering the current temporary results before normal closure. Existing proposals without a tmp revision need a fresh result review. If comparison finds no changes, use `pcw_proposal_prepare(changes=[], no_changes_reason=...)`; it records the review without a knowledge write or an approval request. New or changed temporary results invalidate the earlier review for closure.

0.9.0 changes the MCP API: callers pass cycle_id, permanent mutations use proposal preparation/application, and Current belongs to cycle tmp. Old immediate-write tools are no longer exposed. Start a new host session for the changed skill/tool definitions.

For the existing Git marketplace tracking this repository:

```bash
codex plugin marketplace upgrade persistent-context-workspace
codex plugin add persistent-context-workspace@persistent-context-workspace
```

These are installation commands, not actions performed by this source update. Portable hosts use the packaged plugin and `mcp.json`. Startup never installs Python dependencies or downloads model weights. Read [setup](plugins/persistent-context-workspace/skills/pcw/references/setup.md) for a concrete setup failure.

## Verification

The tests retain the existing storage/token-window regressions and add cycle isolation, proposal review/conflicts, partial failure/retry and full cleanup tests. The standard-MCP launcher test uses a temporary workspace. Opt-in real-agent host tests exercise reading and tmp retention before approval, followed by application after a separate human-message turn. Static and deterministic tests do not establish model compliance in every host.

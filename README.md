# Persistent Context Workspace

Version 0.11.1 implements the [v3 design](docs/context-workspace-design-v3.md): selected project memory, independent reading, task state, configurable work/approval policies, local history and an analytical journal over standard MCP. Source changes do not update an installed plugin automatically.

See the [API and storage contracts](docs/context-workspace-v3-contracts.md), [upgrade plan](docs/context-workspace-upgrade-plan.md), [execution goal](docs/context-workspace-upgrade-goal.md), [verification results](docs/context-workspace-v3-verification.md) and [release notes](CHANGELOG.md). Earlier design documents describe earlier versions.

## Select the procedure

| Skill | Purpose |
| --- | --- |
| pcw | Work cycle and natural-language routing |
| pcw-create | Explicit creation with selected location, scope and settings |
| pcw-search | Independent retrieval without a work cycle |
| pcw-instructions | Requested and explicitly approved rule changes |
| pcw-upgrade | Technical migration of selected contexts |
| pcw-audit | Evidence-based inspection without permanent changes |
| pcw-rework | Requested transformation of existing knowledge |

Creation and switching require clear user direction. A guessed repository name or empty search cannot create a workspace. If the intended context is unclear, the agent asks. Each procedure reads the selected context's rules; remembered chat does not replace PCW retrieval. The plugin does not choose models, launch workers or require a host-specific session ID.

## Project rules and work

`INSTRUCTIONS.md` is the single source of project rules and settings. The [default template](plugins/persistent-context-workspace/pcw_runtime/default_instructions.md) is used for creation, with the user's selected settings; upgrades preserve custom text. A direct rule-edit request follows pcw-instructions and always needs approval of shown changes.

Four settings are selected separately at creation:

| Setting | Meaning | Missing legacy value |
| --- | --- | --- |
| allow_implicit_updates | Permit work without an explicit PCW invocation | false |
| knowledge_approval_required | Wait for approval of shown knowledge/PROJECT changes | true |
| git_history_enabled | Record local permanent-data snapshots | false |
| material_max_tokens | Optional body limit with the index tokenizer | null (disabled) |

Independent reading needs no work cycle, tmp, proposal or finish. It never creates storage, repairs an index or migrates a context. Normal work opens a cycle, reads instructions and PROJECT, retrieves relevant knowledge and creates/resumes a task Current. Significant results go to tmp; concise verified progress goes to Current.

Before closure, the agent compares results with existing knowledge and prepares actual changes or an explained no-change result. It shows exact new text or changed passages, deletions and link effects in chat. It applies the shown revision under the approval setting; showing a file link is insufficient in either mode. Finish clears only that cycle's tmp without another permission question. Pending review or incomplete application/indexing prevents normal closure.

## Storage

```text
<work_root>/.pcw/<workspace>/
  INSTRUCTIONS.md              # rules and settings
  PROJECT.md                   # purpose, goals and accepted boundaries
  current/<task-id>.md          # separate persistent task states
  knowledge/<filename-id>.md    # current factual descriptions
  tmp/<cycle-id>/               # results, drafts and proposal reviews
  .pcw-runtime/                # derived vector index and configuration
  .git/                        # when local history is selected
<work_root>/.pcw/.control/<workspace>/
  format.json                  # workspace format, independent of plugin version
  cycles.json                  # cycle identities and states
  creation.json                # idempotent creation receipt
  task-requests.json           # idempotent task creation
  migration.json, backups/     # migration recovery
  history/                     # immutable pending Git snapshots
<work_root>/.pcw/.analytics/events.sqlite
```

Task IDs belong to tasks, not host sessions. Several tasks/cycles can use one workspace. Updating Current checks its revision and affects only the explicitly bound task; closing a cycle preserves Current. PROJECT changes do not rewrite earlier tasks. Knowledge, PROJECT and instructions have distinct purposes; Current and analytics are not vector knowledge.

## Materials, links and embeddings

Materials answer independent questions according to workspace instructions. Agents prepare coherent final topics and links; the code does not choose semantic boundaries. Reads return the entire selected topic plus target titles and saved descriptions. Only useful neighbors are loaded; `from_id` records a declared traversal of an actual link.

Proposals can create, revise, move, delete, merge or split topics while preserving filename IDs and reviewing incoming-link effects. Metadata and unchanged-body updates do not reembed. An optional token cap rejects oversized final bodies before a permanent write; it does not certify semantic quality.

Default embeddings use local `Qwen/Qwen3-Embedding-0.6B`, a pinned revision, CPU and 1024 dimensions. Index windows default to 512 tokens with 64-token overlap. Other sentence-transformers models, Ollama and configured APIs are supported with compatible tokenizers. Only permanent bodies enter the index. See [embedding configuration](plugins/persistent-context-workspace/skills/pcw/references/embeddings.md).

## History and analysis

When selected, Git creates an initial snapshot and one commit per actual applied permanent change. It includes knowledge, PROJECT and INSTRUCTIONS; excludes tmp, Current, index and analytics; and never pushes automatically. Empty comparisons do not create commits. Failed commits retain exact snapshots for ordered retry without incorporating later file edits. File-save, index and Git statuses are distinct.

SQLite automatically records dispatched MCP calls, parameters, results, errors, timing, selected context/cycle/task and observed file versions. Read only selected event bodies when analyzing operations. Assessments remain separate from observations. A missing terminal record has an unknown outcome; filesystem and SQLite are not one transaction.

Optional adapters import an explicitly selected other-agent transcript (`codex-jsonl` or portable `pcw-session-v1`). No disk-wide session discovery or timestamp-based actor attribution is performed. Git/file observations do not establish every outside action. Credential filters run before logging, but cannot identify arbitrary unlabelled secrets. Do not submit secrets as content. See [history and analytics](plugins/persistent-context-workspace/skills/pcw/references/history-analytics.md).

## Compatibility and recovery

Workspace format 1 is separate from the plugin version. Opening incompatible storage reports the need for pcw-upgrade. Recognized unversioned 0.8–0.10 contexts can be copied, migrated and verified explicitly. Knowledge, links, IDs and user instructions are preserved. Old root Current files remain intact; deciding how their contents become PROJECT, Current or knowledge is separate semantic rework.

`pcw_upgrade_plan` performs the preflight in one call: compatibility, exact revision, technical changes, unfinished work with proposal states and material titles, and blockers. Compatible active cycles survive migration unchanged. The backup includes the entire workspace (including tmp and the index) and separate control state (including cycle records and ID reservations). Prepared proposals are neither applied nor discarded; already-applied proposals keep their state. Source and backup integrity are checked before marking the format current. Retry a pending migration with its returned `resume_revision` and the same snapshot. Unsupported/interrupted cycle states or damaged proposals are reported before application and need separate recovery, not blanket cancellation.

Missing permanent files are not reset to defaults. Missing derived storage is repaired explicitly. Failed multi-file writes report partial state and retain the proposal; retry that same operation. Indexing errors preserve written text. Source conflicts require a new review. No filesystem-wide atomic transaction or universal model compliance is claimed.

## Installation and verification

For an existing Git marketplace tracking this repository, authorized installation uses:

```bash
codex plugin marketplace upgrade persistent-context-workspace
codex plugin add persistent-context-workspace@persistent-context-workspace
```

Portable hosts use the packaged plugin and `mcp.json`. These commands are not executed by a source update. Startup never installs dependencies or downloads model weights. Use [setup](plugins/persistent-context-workspace/skills/pcw/references/setup.md) for an actual failure.

Tests use temporary workspaces and deterministic embeddings with real LanceDB, Git and SQLite. They cover storage preservation, independent reading, policy combinations, revision conflicts, tasks, history retry, analytics and session imports. Opt-in host tests use real model inference and must report the exact tested candidate; deterministic tests alone do not prove every agent follows the skill.

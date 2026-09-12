# Persistent Context Workspace

Version 0.4.0 provides one explicit `$pcw` skill, linked Markdown knowledge, and local semantic search. The primary agent manages memory and task decisions; native subagents investigate real sources, make authorized changes, and prepare literal search parts.

```text
$pcw Prepare context for the validator project at /path/to/project. Record its architecture and the task constraints.

$pcw Continue the validator task using its existing context.
```

Everything after `$pcw` is natural language. Preparing or refining context does not execute the saved task. An explicit execution request includes the necessary preparation; no separate run skill or Controller is required.

## Local setup

The runtime requires Python 3.11 or newer on a POSIX system, Git for memory checkpoints, and the package dependencies. LanceDB is embedded; no database server is needed. Install dependencies explicitly into a dedicated virtual environment:

```bash
pcw_repo=/absolute/path/to/persistent-context-workspace
pcw_venv="${XDG_DATA_HOME:-$HOME/.local/share}/persistent-context-workspace/venv"
python3 -m venv "$pcw_venv"
"$pcw_venv/bin/python" -m pip install "$pcw_repo/plugins/persistent-context-workspace[local]"
"$pcw_venv/bin/python" "$pcw_repo/plugins/persistent-context-workspace/scripts/launch.py" --check
```

The `[local]` extra installs sentence-transformers and its model runtime dependencies. It does not pre-download the Qwen model. When explicitly using an existing remote embedding endpoint, omit `[local]`; the base install supplies LanceDB and MCP. Git commits use your configured Git identity.

The launcher selects `PCW_PYTHON` when set to an absolute executable path. Otherwise it uses the dedicated environment above. It imports runtime code from the active plugin copy, including a Codex cache copy, while reusing that environment's dependencies. Dependency upgrades require an explicit install command again. A source-checkout `.venv` is not silently assumed to exist inside the installed plugin.

The bundled stdio configuration uses `PLUGIN_ROOT`, with `CLAUDE_PLUGIN_ROOT` compatibility, to locate the launcher. The host starts the process when needed; the model stays loaded only for that process's lifetime. Startup never installs packages or downloads model weights. `--check` checks imports without loading the model; the first embedding request may download weights unless offline mode is explicitly configured.

For a checkout you intend to register as a local marketplace:

```bash
codex plugin marketplace add /absolute/path/to/persistent-context-workspace
codex plugin add persistent-context-workspace@persistent-context-workspace
```

Use the marketplace entry that points to this checkout if already configured. Start a new thread after installation or updating the installed copy. These commands are deployment instructions, not steps performed by the runtime. The repository also remains installable from its published GitHub branch; unpushed local changes are not present in that branch.

The legacy `.codex-plugin/plugin.json` manifest includes the bundled `.mcp.json` configuration. See the [official bundled MCP documentation](https://developers.openai.com/plugins/build/plugins#bundled-mcp-servers-and-lifecycle-hooks) for plugin-host configuration.

## Memory and task flow

Each semantic workspace lives under its source project:

```text
<work-root>/.pcw/<workspace>/
├── current.md
├── knowledge/
│   └── <material>.md
├── .pcw-runtime/
│   ├── active.json
│   ├── lancedb/
│   └── lock
└── .git/
```

Knowledge is full Markdown with permanent `id` and `links` fields in YAML frontmatter. Links contain material IDs, without relation types or explanations; real dependencies and conditions belong in the body. Renaming a file changes its address without changing its ID. Reading by ID opens the full material and its navigation list.

Current contains goal, constraints, completion condition, current step, and blocker. The primary reads it at task start or recovery and updates the working step when its decision changes. Current stays compact and does not accumulate tool events, subagent reports, or duplicated knowledge.

The primary searches existing knowledge, reads useful materials, follows relevant ID links, and gives native subagents concrete source questions or implementation assignments. It incorporates accepted findings and corrections into the affected knowledge itself, preserving conditions and uncertainty. It removes repeated content when consolidation is useful; a new summary beside unchanged duplicates is not consolidation.

New or edited material is saved immediately and marked `pending_preparation`. A clean native helper obtains its original body, divides it into literal semantic parts, and submits them with the material revision. It keeps tables, code, conditions, and their existing explanations intact. The helper does not summarize, open source files, or choose fixed token windows. The Python server exposes the preparation tools; the host's agent starts the helper.

LanceDB stores each part's text and embedding with the material ID and path. The runtime validates literal coverage and revision before indexing. Pending materials remain readable, while stale parts are excluded from search. An embedding error does not erase the primary's saved content or claim indexing succeeded. Links-only changes and renames do not trigger splitting or embedding.

No separate graph database, search agent, raw-result archive, process journal, or permanent background service is required.

## Search and embeddings

The default is local `Qwen/Qwen3-Embedding-0.6B` through sentence-transformers, pinned to revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`. It uses 1024 dimensions, normalized vectors, CPU float32 execution, and Qwen's retrieval instruction for queries only. The model is loaded lazily once and reused. Configure `local_files_only: true` for a previously provisioned offline cache.

Search requests at most `N` nearest parts, discards distances above `d_max`, cuts at the first sufficiently large adjacent distance gap, and deduplicates material IDs. It returns IDs and paths; the primary reads the selected full materials. Defaults `N=20`, `d_max=0.8`, `min_jump=0.02`, and `multiplier=3` with cosine distance are provisional engineering choices, not calibrated retrieval claims. Empty results do not establish that knowledge is absent.

Explicit alternatives are Ollama `/api/embed` and an OpenAI-compatible `/v1/embeddings` service. A configuration separates provider connection from model, revision, dimensions, input formatting, normalization, and precision. API credentials are environment-variable references. Chat subscriptions do not themselves provide an embedding API or authorize paid calls.

The local adapter checks input length; Ollama receives `truncate: false`. Compatible HTTP providers must reject oversized input: their common protocol has no universal flag that proves non-truncation, and a returned vector cannot establish it. Invalid vector responses fail; the runtime never fabricates vectors or automatically switches providers.

`pcw_switch_embeddings` accepts the full intended configuration and search settings. It re-embeds stored literal parts into a new table, then activates the matching provider and table together. It does not split materials again or change knowledge IDs and links. A rebuild failure retains the previous configuration and table. Matching dimensions or a shared model name do not establish compatibility; credential-only changes do not require re-embedding existing parts.

Tool-specific guidance is in the skill's [embedding reference](plugins/persistent-context-workspace/skills/pcw/references/embeddings.md).

## Git, restoration, and legacy memory

The first local checkpoint initializes the workspace's own Git repository. Checkpoints include only exact request-owned Current and knowledge paths, unless the user forbids the commit. Runtime configuration, database data, caches, and credentials stay outside Git. The source project's Git must ignore `.pcw/`; runtime operations themselves stay inside the selected workspace.

Merge and delete tools mechanically update incoming ID links before removing materials. They accept final content and explicit replacements from the primary, and report partial changes if a multi-file operation fails. Physical LanceDB cleanup is separate maintenance; removed rows must disappear from current search even if disk space is not immediately reclaimed.

`pcw_restore` restores authorized, exact memory paths from a local commit. Reconciliation removes stale search rows, repairs paths, and exposes material IDs needing fresh preparation. The same reconciliation detects externally restored knowledge. Git provides memory history; it does not reverse external actions, recover lost agent context, or make multi-file changes transactional.

Existing Markdown is not silently rewritten. `pcw_adopt` explicitly registers legacy files, preserves existing IDs and metadata, and assigns missing IDs. The primary deliberately converts useful old wiki navigation to ID lists; relation prose and conditions are preserved. Legacy Current is returned verbatim until explicitly replaced with the new focus fields. A legacy `index.md` is an optional ordinary material, not a compulsory global entrypoint.

## Development

The plugin contains the single skill and conditional references, manifest and stdio configuration, launcher, `pcw_runtime/`, and `pyproject.toml`. [PLAN.md](PLAN.md) records the architecture and remaining measurements.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_contracts.py -v
"$pcw_venv/bin/python" -m unittest discover -s tests -v
```

Contract tests cover packaging and fixture links; their real stdio handshake uses the installed runtime dependencies. Runtime tests exercise local LanceDB with deterministic embedding fixtures. Adapter tests check provider protocols and failure behavior without external credentials or model downloads. Those tests do not measure real Qwen quality, latency, or memory consumption. Run the complete suite in the installed environment so integration tests are not skipped.

Routine memory handling does not add semantic acceptance, source rereading, or tests. Verification required by the actual task still applies.

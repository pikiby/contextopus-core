# Persistent Context Workspace

Version 0.4.2 provides one explicit `$pcw` skill, linked Markdown knowledge, and local semantic search. The primary agent manages memory and task decisions; native subagents investigate real sources, make authorized changes, and prepare literal search parts.

```text
$pcw Prepare context for the validator project at /path/to/project. Record its architecture and the task constraints.

$pcw Continue the validator task using its existing context.
```

Everything after `$pcw` is natural language. Preparing or refining context does not execute the saved task. An explicit execution request includes the necessary preparation; no separate run skill or Controller is required.

## Local setup

The runtime requires an existing Python 3.11 or newer on a POSIX system, Git for memory checkpoints, and the package dependencies. LanceDB is embedded; no database server or virtual environment is required. The primary agent checks setup when `$pcw` is invoked, requests any missing installation permission with the exact scope, repairs missing requirements after approval, and continues the original task.

Use the active plugin directory, which can be a checkout or an installed cache copy:

```bash
pcw_plugin=/absolute/path/to/persistent-context-workspace/plugins/persistent-context-workspace
/bin/sh "$pcw_plugin/scripts/launch.sh" --check
/bin/sh "$pcw_plugin/scripts/launch.sh" --check-local
```

The shell launcher selects an absolute `PCW_PYTHON` when configured, otherwise `python3` from PATH. An explicit interpreter works even when `python3` is absent. The cheap checks report Python and dependency versions, missing or incompatible requirements, pip availability, and `dependency_install_target`. `--check` covers the MCP runtime; `--check-local` also covers local embedding dependencies. Neither imports the model runtime nor proves that model weights are cached. Deeper import checks are available for installation verification; see [Runtime setup](plugins/persistent-context-workspace/skills/pcw/references/setup.md).

Dependencies can be supplied by the selected interpreter or installed with its pip into the reported private packages directory using `--target`. This directory contains packages, not a Python executable or a virtual environment. `PCW_DEPENDENCIES` can select another absolute packages directory; the default is under the user's data directory and is separated by Python ABI and platform. The launcher imports active plugin code first, then that target. Python runs with `-E -P -B` to exclude the working directory and `PYTHONPATH` while preserving its normal installed-package and virtual-environment policy. Existing user site-packages remain available when that policy allows them; `PYTHONNOUSERSITE` is honored. Run checks through the launcher to see what the runtime actually uses.

After consent, install only the reported missing or incompatible distributions and their required dependencies into the agreed destination. Do not override system package protections or create a virtual environment automatically. The `[local]` package extra describes sentence-transformers and its runtime dependencies; it does not download the Qwen weights. Existing remote embedding configurations need only the base runtime requirements. Git commits use your configured Git identity.

The portable root `plugin.json` and `mcp.json` let Codex resolve `${PLUGIN_ROOT}/scripts/launch.sh` into an absolute script argument before starting `sh`. This is plugin-path substitution, not a shell lookup of an assumed environment variable. The host starts the persistent MCP process; a loaded model is reused for that process's lifetime. Startup never installs packages or downloads weights. Before a first embedding request that would download weights, the agent discloses model/cache and resource scope and requests permission unless already authorized. Refused or failed setup remains a concrete blocker.

For a checkout you intend to register as a local marketplace:

```bash
codex plugin marketplace add /absolute/path/to/persistent-context-workspace
codex plugin add persistent-context-workspace@persistent-context-workspace
```

Use the marketplace entry that points to this checkout if already configured. These commands are deployment instructions, not steps performed by the runtime. The repository also remains installable from its published GitHub branch; unpushed local changes are not present in that branch.

After dependency repair, retry the bundled server through a supported host reload if one is available and verify that PCW tools are exposed. A successful standalone check or stdio handshake does not reconnect an existing failed host connection. If the current host cannot reload, preserve the original task and next action in the conversation and resume them after restarting the host session. A newly installed plugin copy may require a new thread to expose updated skills/tools; that continues the same task without a new assignment. There is no automatic live reconnect promise or separate manual `codex mcp add` step.

The `.codex-plugin/plugin.json` compatibility metadata remains, but does not redeclare MCP through the legacy `mcpServers` field. Codex loads the portable root manifest and resolves the root `mcp.json` transport. `codex mcp get pcw --json` must show an absolute launcher argument, not an unresolved placeholder. See the [official bundled MCP documentation](https://developers.openai.com/plugins/build/plugins#bundled-mcp-servers-and-lifecycle-hooks) for plugin-host configuration.

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
```

For the full suite, install the `[test]` extra or pytest in the selected development Python or its private packages directory. From the checkout root, set `pcw_plugin` to its plugin directory and copy `python.executable` and `dependency_install_target` from that launcher's `--check` report into `pcw_python` and `pcw_packages`. Include both paths when starting pytest so an installation using only `--target` works:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  PYTHONPATH="$pcw_plugin:$pcw_packages" PCW_DEPENDENCIES="$pcw_packages" \
  "$pcw_python" -m pytest tests -q -p no:cacheprovider
```

The pytest command collects both unittest cases and the runtime's pytest functions; unittest discovery alone is not the full suite. Contract tests cover packaging and fixture links, including real stdio initialization when dependencies are available. Runtime tests exercise local LanceDB with deterministic embedding fixtures. Adapter tests check provider protocols and failure behavior without external credentials or model downloads. These tests do not measure real Qwen quality, latency, or memory consumption. Report any integration skips explicitly.

Before release, install the matching candidate and run the actual Codex-host regression:

```bash
PCW_TEST_CODEX=1 PCW_TEST_QWEN=1 PYTHONDONTWRITEBYTECODE=1 \
  python3 -B -m unittest discover -s tests -p test_codex_host.py -v
```

This requires Codex and already provisioned Qwen weights. It reads the transport from `codex mcp get`, starts an ephemeral Codex app-server thread, checks its MCP tool inventory, and invokes PCW through `mcpServer/tool/call`. The test makes no language-model turns, downloads, installations, or persistent configuration changes; it writes only temporary test knowledge. It needs normal Codex state-directory access. Other configured MCP servers/plugins are disabled only for this test process. The parent process has no manually supplied plugin-root variables. Omitting `PCW_TEST_QWEN=1` skips the embedding case; omitting `PCW_TEST_CODEX=1` skips both host cases. A direct launcher test does not replace this host regression.

Routine memory handling does not add semantic acceptance, source rereading, or tests. Verification required by the actual task still applies.

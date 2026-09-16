# Runtime setup and recovery

Use this reference when the bundled `pcw` tools are unavailable or an embedding operation needs prerequisite checks. The primary first calls `pcw_startup` for the selected workspace; a successful response establishes live MCP availability and supplies the initial state in one read. A new conversation alone is not a reason to launch diagnostics first. This availability check does not prove that model weights are cached or embeddings work.

When diagnostics or repair are needed, the primary consults the relevant rules, reuses existing authority and established observations, and performs the bounded PCW setup work itself. Ask only for authority that is actually missing. Do not retrieve rules before every setup operation. The primary gathers model capabilities itself and reuses the published map while actual capabilities remain unchanged; session IDs and diagnostic warnings do not belong in the environment version. Setup does not grant a worker access to PCW. A missing interpreter or distribution does not require broad source research or web diagnosis.

An exposed server with a broken workspace returns `recovery_required`. Task status, instructions and model-map tools use `.pcw/.control/<workspace>/` independently of the derived index. The primary calls `pcw_recover_workspace` itself. Missing knowledge remains a blocker; `recreate_missing_knowledge: true` needs actual authority and does not restore lost content. Do not interpret a missing lock as proof that a new workspace cannot bootstrap. Reload outstanding tasks and synchronize Current after recovery. No diagnostic worker receives memory paths or PCW instructions.

## Check the active plugin

The primary resolves the active plugin root from this skill's location: it is two directories above `skills/pcw/`. It uses that exact copy, including when it is under a host plugin cache, and does not infer that editing a source checkout changed an installed copy. It sets `setup_plugin` to that absolute root and runs:

```sh
/bin/sh "$setup_plugin/scripts/launch.sh" --check
```

The shell can diagnose missing Python itself. It honors an absolute `PCW_PYTHON` or selects `python3` from PATH. Reuse a suitable existing interpreter; an existing user-chosen virtual environment is acceptable but is not required. Do not create one automatically. The Python requirement is 3.11 or newer.

The stdlib readiness report identifies the selected interpreter/version, missing or incompatible distributions, `pip_available`, `externally_managed`, and `dependency_install_target`. The runtime uses the active plugin and configured private packages directory ahead of the selected Python's normal installed packages. Startup with `-E -P -B` excludes `PYTHONPATH` and the working directory while retaining the interpreter's normal user-site and virtual-environment policy; `PYTHONNOUSERSITE` is honored through `-s`. Reuse already-available dependencies. A plain shell import can still disagree with the launcher because of the different project and private-package paths.

`--check` checks base requirements. For the default local embedding provider, also run:

```sh
/bin/sh "$setup_plugin/scripts/launch.sh" --check-local
```

These checks inspect dependency availability and versions without loading the model runtime. They do not prove that native libraries import, the model is cached, embeddings work, or the host is connected. Readiness output is authoritative for the installation destination and observed requirements; do not substitute a historical venv path.

## Repair only the missing requirements

The primary reports the observed missing Python/packages, selected installation method, exact destination, and expected network/disk scope, then asks permission if it is not already authorized. For a missing Python or pip, the primary establishes only the necessary local OS/package-manager facts to make that proposal. Do not ask the user to choose Python internals when an existing suitable interpreter resolves the issue. Do not install packages or download model weights merely because `$pcw` was invoked.

After approval, perform the agreed installation and continue the same task. The primary prefers the report's private packages destination with the selected interpreter's `-m pip install --target`, passing only reported missing/incompatible distribution requirements and their required dependencies. An explicit `PCW_DEPENDENCIES` selects another absolute target when agreed. Do not add blanket upgrades or reinstall already-satisfied direct requirements. The target is a package directory, not a Python environment. Do not use `--break-system-packages`, change system protections, or create an automatic venv to get around an error.

The primary repeats cheap checks after installation. It uses the deeper import checks after a dependency change or for an actual import failure, without loading model weights:

```sh
/bin/sh "$setup_plugin/scripts/launch.sh" --check-imports
/bin/sh "$setup_plugin/scripts/launch.sh" --check-local-imports
```

Use the local checks only when the selected provider is local. Preserve actionable import failures and their tracebacks. A dependency inventory marked ready is not equivalent to a successful deep import check.

If consent is refused, execution is denied, or installation fails due to network, disk, package resolution, or permissions, report that concrete blocker and any partial installation effects. Do not repeatedly attempt the same denied action, switch providers, or claim memory/index/checkpoint success. Retain the user's task and the next required action in the conversation; an unavailable runtime cannot save a new Current or checkpoint through its tools.

## Local model and live connection

Model discovery follows the cheap base readiness check; it need not block dependency repair. Once tools are available, the primary reads the selected provider/profile through `pcw_status`. If tools are unavailable and the exact workspace is already established, the primary may read only its known `<work-root>/.pcw/<workspace>/.pcw-runtime/active.json` for `config.provider` and `config.profile`, without scanning project sources or other workspaces. If no configuration exists, use the bundled default: local `sentence-transformers` on CPU, `Qwen/Qwen3-Embedding-0.6B` revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`, `cache_folder: null`, and `local_files_only: false`.

The primary uses an existing `provider.cache_folder` and applicable cache environment settings, such as `SENTENCE_TRANSFORMERS_HOME`, `HF_HUB_CACHE`, or `HF_HOME`. With no overrides, the usual Hugging Face cache is under `~/.cache/huggingface/hub`. It inspects only the selected cache location without loading or downloading a model; cache inspection can wait until the base tools are available. Report known defaults/overrides and whether cached weights were actually established. If the final destination is not yet resolvable, say so rather than researching unrelated configuration or inventing a path.

Before an uncached load, disclose the model, known cache destination/defaults, weight download, storage, and CPU/RAM use; request any still-missing download permission. Do not invent a precise download size or latency measurement. Reuse existing permission and an existing verified cache. Read [Embedding configuration](embeddings.md) when configuring offline loading or diagnosing a model failure. No remote embedding fallback is selected automatically.

The plugin manifest already declares the persistent stdio MCP server. Keep that declaration; do not add a duplicate manual MCP server or replace memory tools with a one-shot runtime invocation. After setup succeeds, retry through the host's supported reload/reconnect facility only when that facility is actually available, then verify PCW tools are exposed and the pending operation succeeds. Dependency repair and a standalone stdio initialization/tool-list handshake are useful checks, but do not establish this live connection.

If this host cannot reload its failed server, explain the remaining host-session restart requirement. Preserve the task and next action in the conversation and continue them after restart, without requiring the user to assign the task again. A separate process cannot reconnect the current host merely by starting successfully. Do not promise automatic reconnection or report memory saves/checkpoints that never occurred.

# Runtime setup and recovery

Use this reference when the bundled `pcw` tools are unavailable, setup has not been verified, or local embedding prerequisites have not been established. The primary performs these bounded checks before loading memory-operation references or delegating source work. Reuse results already established in this conversation. A missing interpreter or distribution does not require a research task, source-code investigation, or a diagnostic subagent.

## Check the active plugin

Resolve the active plugin root from this skill's location: it is two directories above `skills/pcw/`. Use that exact copy, including when it is under a host plugin cache. Do not infer that editing a source checkout changed an installed copy. Set `setup_plugin` to that absolute root and run:

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

If installation has not already been authorized, ask permission with the observed missing Python/packages, selected installation method, exact destination, and expected network/disk scope. For a missing Python or pip, establish only the necessary local OS/package-manager facts to propose a concrete installation. Do not ask the user to choose Python internals when an existing suitable interpreter resolves the issue. Do not install packages or download model weights merely because `$pcw` was invoked.

After approval, carry out the agreed installation and continue the same task. Prefer the report's private packages destination with the selected interpreter's `-m pip install --target`, passing only the reported missing/incompatible distribution requirements and allowing their required dependencies. An explicit `PCW_DEPENDENCIES` selects another absolute target when agreed. Do not add blanket upgrades or reinstall already-satisfied direct requirements. The target is a package directory, not a Python environment. Do not use `--break-system-packages`, change system protections, or create an automatic venv to get around an error.

Repeat the cheap checks after installation. Use the deeper import checks after a dependency change or for an actual import failure, without loading model weights:

```sh
/bin/sh "$setup_plugin/scripts/launch.sh" --check-imports
/bin/sh "$setup_plugin/scripts/launch.sh" --check-local-imports
```

Use the local checks only when the selected provider is local. Preserve actionable import failures and their tracebacks. A dependency inventory marked ready is not equivalent to a successful deep import check.

If consent is refused, execution is denied, or installation fails due to network, disk, package resolution, or permissions, report that concrete blocker and any partial installation effects. Do not repeatedly attempt the same denied action, switch providers, or claim memory/index/checkpoint success. Retain the user's task and the next required action in the conversation; an unavailable runtime cannot save a new Current or checkpoint through its tools.

## Local model and live connection

Model discovery follows the cheap base readiness check; it need not block dependency repair. Once tools are available, read the selected provider/profile from `pcw_status`. If tools are unavailable and the exact workspace is already established, its existing `<work-root>/.pcw/<workspace>/.pcw-runtime/active.json` records `config.provider` and `config.profile`. Read only that known configuration as needed, without scanning project sources or other workspaces. If no configuration exists, use the bundled default: local `sentence-transformers` on CPU, `Qwen/Qwen3-Embedding-0.6B` revision `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`, `cache_folder: null`, and `local_files_only: false`.

Use an existing `provider.cache_folder` and the model loader's applicable cache environment settings, such as `SENTENCE_TRANSFORMERS_HOME`, `HF_HUB_CACHE`, or `HF_HOME`. With no overrides, the usual Hugging Face cache is under `~/.cache/huggingface/hub`. Inspect only the selected cache location without loading or downloading a model; cache inspection can wait until the base tools are available. Report known defaults/overrides and whether cached weights were actually established. If the final destination is not yet resolvable, say so rather than researching unrelated configuration or inventing a path.

Before an uncached load, disclose the model, known cache destination/defaults, weight download, storage, and CPU/RAM use; request any still-missing download permission. Do not invent a precise download size or latency measurement. Reuse existing permission and an existing verified cache. Read [Embedding configuration](embeddings.md) when configuring offline loading or diagnosing a model failure. No remote embedding fallback is selected automatically.

The plugin manifest already declares the persistent stdio MCP server. Keep that declaration; do not add a duplicate manual MCP server or replace memory tools with a one-shot runtime invocation. After setup succeeds, retry through the host's supported reload/reconnect facility only when that facility is actually available, then verify PCW tools are exposed and the pending operation succeeds. Dependency repair and a standalone stdio initialization/tool-list handshake are useful checks, but do not establish this live connection.

If this host cannot reload its failed server, explain the remaining host-session restart requirement. Preserve the task and next action in the conversation and continue them after restart, without requiring the user to assign the task again. A separate process cannot reconnect the current host merely by starting successfully. Do not promise automatic reconnection or report memory saves/checkpoints that never occurred.

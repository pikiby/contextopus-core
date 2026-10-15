<p align="center">
  <img src="docs/media/contextopus-wide-1200.svg" alt="Contextopus animated logo" width="1200">
</p>

# Contextopus

Persistent context for people and coding agents. Keep project knowledge, working instructions and unfinished work outside a chat, then use the same context from a terminal or your coding assistant.

Contextopus is a standalone Python application with a shared Core, a Workspace module, a terminal interface and an MCP service. Coding-client integrations connect to that service and expose short skills.

**1.1.0 unifies projects, tasks and knowledge in searchable records**, adds project discovery, six short skills and native MCP service controls. Installation uses a checked wheel from [GitHub Releases](https://github.com/pikiby/contextopus-core/releases); no PyPI publication is implied. [Release notes](docs/releases/1.1.0.md) distinguish tests from platform and client verification.

![Contextopus terminal example](docs/media/tui/main-wide.png)

Actual Textual render with clearly marked synthetic example data. [Keyboard settings demo](docs/media/tui/settings-demo.gif) · [Narrow terminal](docs/media/tui/main-narrow.png) · [Capture method and limits](docs/media/tui/README.md).

## Use it

| Scenario | Entry |
|---|---|
| Continue project work with persistent knowledge | `w` skill |
| Find prior decisions without modifying memory | `w-search` skill |
| Analyze actual agent operations and historical instructions | `w-analyze` skill |
| Review a requested instructions change | `w-settings` skill |
| Create an explicitly requested Workspace | `w-create` skill |
| Find a context by name, path or meaning | `w-find` skill |
| Inspect status/settings/modules | `contextopus status`, `settings`, `modules` |
| Work from a terminal interface | `contextopus tui` |

Full procedures are served by the installed runtime when needed. Workspace selection stays explicit, source-reading rules persist, and permanent changes follow the selected Workspace's review and approval policy.

## Install

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), download the wheel from the [1.1.0 release](https://github.com/pikiby/contextopus-core/releases/tag/v1.1.0), and verify it against `SHA256SUMS`. From the download directory:

```console
uv tool install --python 3.12 ./contextopus_core-1.1.0-py3-none-any.whl
contextopus --version
contextopus init
contextopus tui
```

For local embedding inference, install the same verified wheel with its `local` extra: `uv tool install --python 3.12 "./contextopus_core-1.1.0-py3-none-any.whl[local]"`. Models download only when an explicitly requested operation needs inference; status and setup do not load a model. Python and application dependencies are managed by uv.

Use `--root <directory>` before a subcommand or `CONTEXTOPUS_ROOT` to select persistent storage. The default is the platform's user-data directory, outside plugin caches. Keep the same root across clients.

To update, install the verified 1.1.0 wheel with `uv tool install --force --python 3.12 ./contextopus_core-1.1.0-py3-none-any.whl` (append `[local]` inside a quoted wheel path if needed). Retain the existing data root, run `contextopus --root <existing-data-root> service restart`, then use `w` → upgrade in a fresh client session to review context and skill updates. The upgrade preserves unfinished tasks, tmp and pending approval state. See the [release update instructions](docs/releases/1.1.0.md#install-or-update) before upgrading an older installation.


```console
contextopus integrate codex --project <project-directory>
contextopus integrate codex --project <project-directory> --apply
```

Other client names: `claude-code`, `opencode`, `crush`. Integration refuses name collisions and preserves unrelated configuration. Start the service once; clients connect over loopback HTTP. Verify the actual client's MCP connection after reload.

## Structure and readiness

[Architecture](docs/architecture.md) describes Core, Workspace, MCP, CLI/TUI and module boundaries. Workspace format 3 uses typed records and preserves older memory through recoverable migration. Session search is optional and depends on a separate indexer. GraphFrontier integration is planned; the skills registry remains an idea.

- [Canonical old-installation/context/skills upgrade procedure](src/contextopus/resources/procedures/upgrade.md)
- [Native integration details and primary references](docs/integrations.md)
- [Transition acceptance and evidence](docs/implementation/contextopus-transition.md)
- [1.1.0 release notes](docs/releases/1.1.0.md)
- [Previous changelog](CHANGELOG.md)

The CI matrix tests, builds, verifies and installs the wheel on Linux, macOS and Windows with Python 3.12 and 3.13. Native service login and recovery checks are recorded separately; a passing Python test does not establish OS startup behavior.

## License

Licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for attribution.

# Contextopus

Persistent context for people and coding agents. Keep project knowledge, working instructions and unfinished work outside a chat, then use the same context from a terminal or your coding assistant.

Contextopus is a standalone Python application with a shared Core, a Workspace module, a terminal interface and an MCP service. Coding-client integrations connect to that service and expose short skills.

**1.0.0 is being prepared.** Installation below uses a verified local wheel or an authenticated private GitHub Release asset. No PyPI publication is implied. The terminal interface is implemented; the captures below show its actual headless rendering with synthetic example data. Live model/client readiness is verified separately.

![Contextopus terminal example](docs/media/tui/main-wide.png)

Actual Textual render with clearly marked synthetic example data. [Keyboard settings demo](docs/media/tui/settings-demo.gif) · [Narrow terminal](docs/media/tui/main-narrow.png) · [Capture method and limits](docs/media/tui/README.md).

## Use it

| Scenario | Entry |
|---|---|
| Continue project work with persistent knowledge | `w` skill |
| Find prior decisions without modifying memory | `ws` skill |
| Review a requested instructions change | `wi` skill |
| Create an explicitly requested Workspace | `wc` skill |
| Upgrade old PCW installation, contexts and native skills | `wu` skill |
| Inspect status/settings/modules | `contextopus status`, `settings`, `modules` |
| Work from a terminal interface | `contextopus tui` |

Full procedures are served by the installed runtime when needed. Workspace selection stays explicit, source-reading rules persist, and permanent changes follow the selected Workspace's review and approval policy.

## Install

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), download the private release's wheel through an authenticated GitHub session, and verify it against `SHA256SUMS`. From the download directory:

```console
uv tool install --python 3.12 ./contextopus_core-1.0.0-py3-none-any.whl
contextopus --version
contextopus init
contextopus service start
contextopus tui
```

For local embedding inference, install the same verified wheel with its `local` extra: `uv tool install --python 3.12 "./contextopus_core-1.0.0-py3-none-any.whl[local]"`. Models download only when an explicitly requested operation needs inference; status and setup do not load a model. Python and application dependencies are managed by uv.

Use `--root <directory>` before a subcommand or `CONTEXTOPUS_ROOT` to select persistent storage. The default is the platform's user-data directory, outside plugin caches. Keep the same root across clients.

```console
contextopus integrate codex --project <project-directory>
contextopus integrate codex --project <project-directory> --apply
```

Other client names: `claude-code`, `opencode`, `crush`. Integration refuses name collisions and preserves unrelated configuration. Start the service once; clients connect over loopback HTTP. Verify the actual client's MCP connection after reload.

## Structure and readiness

[Architecture](docs/architecture.md) describes Core, Workspace, MCP, CLI/TUI and module boundaries. Workspace incorporates the existing 0.14.0 implementation and its semantic constraints. Session search is optional and depends on a separate indexer. GraphFrontier integration is planned; the skills registry remains an idea.

- [Canonical old-installation/context/skills upgrade procedure](src/contextopus/resources/procedures/upgrade.md)
- [Native integration details and primary references](docs/integrations.md)
- [Transition acceptance and remaining validation](docs/implementation/contextopus-transition.md)
- [1.0.0 release notes](docs/releases/1.0.0.md)
- [Previous changelog](CHANGELOG.md)

The repository remains private. Cross-platform CI builds and checks Linux, macOS and Windows; release readiness requires those jobs to pass. Local validation alone does not establish another operating system's support.

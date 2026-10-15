# Native client integrations

Contextopus runs one loopback MCP owner at `http://127.0.0.1:8765/mcp`. Start it with `contextopus service start`. Native skills contain routing only; full procedures come from the installed service's `procedure` read operation.

Preview `contextopus integrate <client> --project <directory>`, then add `--apply` to merge. Supported project configurations:

| Client | Config | Skills | MCP form |
|---|---|---|---|
| Codex | `.codex/config.toml` | `.agents/skills` | `mcp_servers.contextopus.url` |
| Claude Code | `.mcp.json` | `.claude/skills` | `mcpServers.contextopus`, HTTP |
| OpenCode | `opencode.json` | `.opencode/skills` | `mcp.contextopus`, remote |
| Crush | `crush.json` | `.agents/skills` | `mcp.contextopus`, HTTP |

Existing unrelated values survive. A differing `contextopus` server or short skill name stops integration. OpenCode files with genuine JSONC comments/trailing commas require native editing rather than destructive rewriting; JSON-compatible `.jsonc` files merge in place. Preview output lists affected paths and never prints existing configuration contents. Clients may require project trust and MCP approval; restart/reload and verify tools from the actual client before declaring a connection ready.

Primary references checked during implementation:

- [Codex MCP](https://developers.openai.com/codex/mcp/), [Agent Skills](https://developers.openai.com/codex/skills/) and [plugin packaging](https://developers.openai.com/plugins/build/plugins).
- [Claude Code MCP and project configuration](https://code.claude.com/docs/en/mcp).
- [OpenCode local and remote MCP](https://opencode.ai/docs/mcp-servers/) and [skills](https://opencode.ai/docs/skills/).
- [Crush MCP and skill configuration](https://github.com/charmbracelet/crush/blob/main/README.md).

Configuration schema support is implemented; live compatibility remains subject to the installed client version and verification. Existing 0.14.0 plugin cache remains available to active sessions during transition.

## User installation and transition

`--user` selects native user configuration instead of a project file. `--config-only` reuses an already discoverable shared skill copy. `--legacy-skills <directory>` upgrades only recognized unchanged old manually installed skill entrypoints into compatibility aliases; edited/unknown files stop for review, and plugin caches are refused. The retained source/cache 0.14.0 entrypoints are represented by packaged content hashes.

Codex plugin users first run `codex plugin marketplace add <checkout>` and `codex plugin add contextopus@contextopus`, then preview/apply `contextopus integrate codex --user --native-plugin`. This cutover requires the installed new cache, disables the exact old plugin flag, removes its obsolete marketplace declaration and an exactly matching duplicate Contextopus manual HTTP entry, and preserves old cache files. Other servers are retained; a conflicting Contextopus definition fails. No plugin uninstall command is used.

Use `contextopus root --set <chosen persistent root>` only for an explicitly selected root; it writes the persistent default binding, creates no data root and never selects/switches a Workspace. `--root` and `CONTEXTOPUS_ROOT` override this default.

The complete repeatable installation/data/skills sequence is fetched with `procedure(name="upgrade")`; the `wu` skill uses that canonical resource.

## Verified native discovery

The 1.0.0 rollout checked installed Codex 0.162.1, Claude Code 2.1.126,
OpenCode 1.18.32 and Crush 0.87.0 against the shared HTTP owner. Fresh Codex
app-server calls listed one Contextopus MCP server, read `core.status` and
fetched the upgrade procedure. Codex namespaces plugin skills as
`contextopus:w`, `contextopus:ws`, `contextopus:wi`, `contextopus:wc`,
`contextopus:wu`, `contextopus:wa`, `contextopus:wr`, `contextopus:wx`.
The disabled old plugin's skills were absent from fresh discovery.

Claude's native MCP inspection and OpenCode's native MCP listing reported
connected. OpenCode's skill listing and Crush's native workspace API both
found all eight shared skills under `~/.claude/skills`; their integrations
therefore use `--config-only` without another skill copy. Crush's native MCP
state reported connected with four tools. These are discovery/connection checks
without model turns; they do not establish every host's complete task workflow.

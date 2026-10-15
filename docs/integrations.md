# Native client integrations

Contextopus runs one loopback MCP owner at `http://127.0.0.1:8765/mcp`. Install its native user service with `contextopus service install`; use `service start|stop|restart|status` afterwards. Native skills contain routing only; full procedures come from the installed service's `procedure` read operation.

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

`--user` selects native user configuration instead of a project file. `--config-only` reuses an already discoverable shared skill copy. `--legacy-skills <directory>` removes only recognized unchanged old manually installed entrypoints; edited/unknown files are preserved and reported, and plugin caches are refused. The retained source/cache 0.14.0 entrypoints are represented by packaged content hashes.

For literal `$w`, `$w-search`, `$w-create`, `$w-settings`, `$w-find`, `$w-analyze`, use `contextopus integrate codex --user --apply`. This direct native integration installs user skills and one HTTP MCP entry. Keep the Contextopus plugin disabled when using this method to avoid duplicate skills and tools. The rollout selected this direct method.

Optional Codex plugin users first run `codex plugin marketplace add <checkout>` and `codex plugin add contextopus@contextopus`, then preview/apply `contextopus integrate codex --user --native-plugin`. This cutover requires the installed new cache, disables the exact old plugin flag, removes its obsolete marketplace declaration and an exactly matching duplicate Contextopus manual HTTP entry, and preserves old cache files. Other servers are retained; a conflicting Contextopus definition fails. No plugin uninstall command is used.

Use `contextopus root --set <chosen persistent root>` only for an explicitly selected root; it writes the persistent default binding, creates no data root and never selects/switches a Workspace. `--root` and `CONTEXTOPUS_ROOT` override this default.

The complete repeatable installation/data/skills sequence is fetched with `procedure(name="upgrade")`; `w` routes upgrade requests to that canonical resource.

## Recovery of an existing client session

| Client | Mechanism | Checked boundary |
| --- | --- | --- |
| Codex 0.162.1 | `contextopus reconnect codex [--thread ID]`, existing app-server proxy and `config/mcpServer/reload` | Queues reload for **all loaded threads and MCP servers**. With a thread ID verifies an actual `core.status` call in that thread. No replacement conversation. |
| OpenCode 1.18.32 | `contextopus reconnect opencode --client-url URL --directory PROJECT` | Inspects the running client's `/doc`, then disconnects/connects Contextopus in that project. HTTP status is not a model tool-call check. Basic auth uses existing `OPENCODE_SERVER_USERNAME/PASSWORD` environment variables. |
| Claude Code 2.1.126 | Existing session's `/mcp` menu, Contextopus, Reconnect | Native user action; this release does not remotely control an existing Claude conversation. |
| Crush 0.87.0 | Native renewal on use of a previously established connection | Initial connection failure has no verified external retry adapter here. Resume the saved session after restarting its workspace if needed. |

Codex's action affects more than Contextopus; TUI labels its loaded-thread scope. Its existing daemon's proxy carries WebSocket frames, handled with wsproto; JSON-lines stdio is a different transport. A queued action is reported separately from successful discovery and a real call. If the native aggregate status call times out, the result remains unverified; a read call in the existing session can establish recovery. A new native process cannot prove an old session recovered. OpenCode requires the URL of the **existing** client server; the adapter never launches a substitute.

`scripts/verify_client_recovery.py codex|opencode` runs isolated native clients against temporary loopback MCP instances, with no model calls. Codex: two failed initializations → reload → successful tool calls in the same two threads; persisted nonempty history survives, as does subsequent server restart. OpenCode: failed initialization and restart recover through its native API; nonempty messages survive. Its test verifies connection, not tool execution by a model.

Primary contracts: [Codex app-server](https://learn.chatgpt.com/docs/app-server#api-overview), [OpenCode server and live OpenAPI](https://opencode.ai/docs/server/), [Claude MCP](https://code.claude.com/docs/en/mcp), [Crush 0.87.0 renewal implementation](https://github.com/charmbracelet/crush/blob/v0.87.0/internal/agent/tools/mcp/init.go). Client APIs are versioned external dependencies, not guarantees about future releases.

## Native service

Linux uses a user systemd unit, macOS a LaunchAgent, Windows a per-user Scheduled Task. Startup is at user login; explicit stop remains stopped until started or the next login. Restart-on-failure uses the native manager. Definitions run the installed interpreter in the foreground and share an ownership lock. No embedded per-client database owner is started.

`contextopus tui` remains usable when MCP is stopped; Start/Stop/Restart use local service control. Access-denied, unreachable, stopped and connected-server/client-error states are distinct. Native definition tests run cross-platform; the release notes list actual runtime checks.

References: [systemd service restart](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html), [Apple LaunchAgents](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html), [Windows task settings](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset).

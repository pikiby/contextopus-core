# Native client integrations

Contextopus runs one loopback MCP owner at `http://127.0.0.1:8765/mcp`. Install its native user service with `contextopus service install`; use `service start|stop|restart|status` afterwards. Native skills contain routing only; procedures come from `guide(procedure=...)` on the installed service.

Preview `contextopus integrate <client> --project <directory>`, then add `--apply` to merge. Supported project configurations:

| Client | Config | Skills | MCP form |
|---|---|---|---|
| Codex | `.codex/config.toml` | `.agents/skills` | `mcp_servers.contextopus.url` |
| Claude Code | `.mcp.json` | `.claude/skills` | `mcpServers.contextopus`, HTTP |
| OpenCode | `opencode.json` | `.opencode/skills` | `mcp.contextopus`, remote |
| Crush | `crush.json` | `.agents/skills` | `mcp.contextopus`, HTTP |

Hermes uses a native user or profile home rather than project configuration:
`contextopus integrate hermes --user [--hermes-home <directory>]` previews
`config.yaml` and `skills/` under `$HERMES_HOME` (default `~/.hermes`). Add
`--apply` after reviewing the paths. Its `mcp_servers.contextopus.url` connects to
the same HTTP owner; its seven native skills are invoked as `/w`, `/w-search`,
`/w-create`, `/w-settings`, `/w-context`, `/w-analyze` and `/m`.
See the [Hermes installation and verification guide](integrations/hermes.md)
for release/source checks, profile placement and recovery.

Existing unrelated values survive. A differing `contextopus` server or short skill name stops integration. OpenCode files with genuine JSONC comments/trailing commas require native editing rather than destructive rewriting; JSON-compatible `.jsonc` files merge in place. Preview output lists affected paths and never prints existing configuration contents. Clients may require project trust and MCP approval; restart/reload and verify tools from the actual client before declaring a connection ready.

Primary references checked during implementation:

- [Codex MCP](https://developers.openai.com/codex/mcp/), [Agent Skills](https://developers.openai.com/codex/skills/) and [plugin packaging](https://developers.openai.com/plugins/build/plugins).
- [Claude Code MCP and project configuration](https://code.claude.com/docs/en/mcp).
- [OpenCode local and remote MCP](https://opencode.ai/docs/mcp-servers/) and [skills](https://opencode.ai/docs/skills/).
- [Crush MCP and skill configuration](https://github.com/charmbracelet/crush/blob/main/README.md).
- [Hermes stable source](https://github.com/NousResearch/hermes-agent/tree/v0.22.2)
  and [Hermes integration guide](integrations/hermes.md).

Configuration schema support is implemented; live compatibility remains subject to the installed client version and verification. Existing 0.14.0 plugin cache remains available to active sessions during transition.

## MCP protocol and transition

The default advertised tools are `guide`, `read`, `write`, and `finish`. Obtain an applicable procedure with `guide(procedure="workspace")` once for an ordinary task, or a single unknown registry signature with `guide(operation="workspace.search")`. `guide(catalog=true)` is opt-in. Queries and mutations retain stable module-qualified operation names inside `read` / `write`; coordinates stay outside `arguments`. Both default to `detail="compact"`; explicit `detail="full"` preserves the complete operation response. Presentation runs after operation journaling, so compact search does not discard candidate evidence.

`finish` closes only the named work cycle after pending work and exact cleanup-revision checks. It uses the independent `cleanup_approval_required` policy; native clients can authorize this bounded tool separately from general writes. Host permissions still apply.

An old client can deliberately use temporary compatibility: launch the service with `CONTEXTOPUS_LEGACY_TOOLS=1`, or embed `create_server(..., legacy_tools=True)`. This advertises the four current tools plus `contextopus_query`, `contextopus_execute`, `pcw_query`, `pcw_execute`, whose full response contract remains intact. Default clients never enable aliases automatically. The Python CLI/TUI facade uses current `read` / `write` with full detail; `RemoteApplication(..., legacy_tools=True)` explicitly selects an older server. Upgrade the client or deliberately enable compatibility when protocols disagree; never retry a failed mutation under a guessed alias, because the first attempt may have committed.

A tool call proves that client/transport path for the tested root. It does not prove a model obtained or followed the procedure; behavioral checks need actual model-operation evidence. Procedure reuse/rereading is per-agent conversation state, never a shared server flag.

## User installation and transition

`--user` selects native user configuration instead of a project file. `--config-only` reuses an already discoverable shared skill copy. `--legacy-skills <directory>` removes only recognized unchanged old manually installed entrypoints; edited/unknown files are preserved and reported, and plugin caches are refused. The retained source/cache 0.14.0 entrypoints are represented by packaged content hashes.

For literal `$w`, `$w-search`, `$w-create`, `$w-settings`, `$w-context`, `$w-analyze`, `$m`, use `contextopus integrate codex --user --apply`. This direct native integration installs user skills and one HTTP MCP entry. Keep the Contextopus plugin disabled when using this method to avoid duplicate skills and tools. The rollout selected this direct method.

Optional Codex plugin users first run `codex plugin marketplace add <checkout>` and `codex plugin add contextopus@contextopus`, then preview/apply `contextopus integrate codex --user --native-plugin`. This cutover requires the installed new cache, disables the exact old plugin flag, removes its obsolete marketplace declaration and an exactly matching duplicate Contextopus manual HTTP entry, and preserves old cache files. Other servers are retained; a conflicting Contextopus definition fails. No plugin uninstall command is used.

Use `contextopus root --set <chosen persistent root>` only for an explicitly selected root; it writes the persistent default binding, creates no data root and never selects/switches a Workspace. `--root` and `CONTEXTOPUS_ROOT` override this default.

The complete repeatable installation/data/skills sequence is fetched with `guide(procedure="upgrade")`; `w` routes upgrade requests to that canonical resource.

## Recovery of an existing client session

| Client | Mechanism | Checked boundary |
| --- | --- | --- |
| Codex 0.162.1 / 0.163.0 | `contextopus reconnect codex [--thread ID]`, existing app-server proxy and `config/mcpServer/reload` | Queues reload for **all loaded threads and MCP servers**. With a thread ID verifies an actual `core.status` call in that thread. No replacement conversation. |
| OpenCode 1.18.32 | `contextopus reconnect opencode --client-url URL --directory PROJECT` | Inspects the running client's `/doc`, then disconnects/connects Contextopus in that project. HTTP status is not a model tool-call check. Basic auth uses existing `OPENCODE_SERVER_USERNAME/PASSWORD` environment variables. |
| Claude Code 2.1.126 | Existing session's `/mcp` menu, Contextopus, Reconnect | Native user action; this release does not remotely control an existing Claude conversation. |
| Crush 0.87.0 | Native renewal on use of a previously established connection | Initial connection failure has no verified external retry adapter here. Resume the saved session after restarting its workspace if needed. |

Codex's action affects more than Contextopus; TUI labels its loaded-thread scope. Its existing daemon's proxy carries WebSocket frames, handled with wsproto; JSON-lines stdio is a different transport. A queued action is reported separately from successful discovery and a real call. If the native aggregate status call times out, the result remains unverified; a read call in the existing session can establish recovery. A new native process cannot prove an old session recovered. OpenCode requires the URL of the **existing** client server; the adapter never launches a substitute.

`scripts/verify_client_recovery.py codex|opencode` runs isolated native clients against temporary loopback MCP instances, with no model calls. Codex: two failed initializations → reload → successful tool calls in the same two threads; persisted nonempty history survives, as does subsequent server restart. OpenCode: failed initialization and restart recover through its native API; nonempty messages survive. Its test verifies connection, not tool execution by a model. The isolated Codex recovery check passed with 0.163.0: two existing test threads retained nonempty history after failed initialization/reload and server restart; automatic renewal succeeded. This does not verify already-open user conversations or model compliance.

Primary contracts: [Codex app-server](https://learn.chatgpt.com/docs/app-server#api-overview), [OpenCode server and live OpenAPI](https://opencode.ai/docs/server/), [Claude MCP](https://code.claude.com/docs/en/mcp), [Crush 0.87.0 renewal implementation](https://github.com/charmbracelet/crush/blob/v0.87.0/internal/agent/tools/mcp/init.go). Client APIs are versioned external dependencies, not guarantees about future releases.

## Native service

Linux uses a user systemd unit, macOS a LaunchAgent, Windows a per-user Scheduled Task. Startup is at user login; explicit stop remains stopped until started or the next login. Restart-on-failure uses the native manager. Definitions run the installed interpreter in the foreground and share an ownership lock. No embedded per-client database owner is started.

`contextopus tui` remains usable when MCP is stopped; Start/Stop/Restart use local service control. Access-denied, unreachable, stopped and connected-server/client-error states are distinct. Native definition tests run cross-platform; the release notes list actual runtime checks.

References: [systemd service restart](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html), [Apple LaunchAgents](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html), [Windows task settings](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset).

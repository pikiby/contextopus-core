# Client installation packages

## Shared implementation

`distribution/build.py` builds a verified starter from an explicit Core wheel and
module folders. `distribution/build_clients.py` wraps that same bundle per client.
The bundle includes module-owned skills; optional modules keep their normal lifecycle.
No client-specific database, model or copy of Core logic is introduced.

```console
python distribution/build.py --core-wheel /path/to/core.whl --module /path/to/workspace --module /path/to/agents --bundle-version 1.8.0 --output /tmp/starter.zip
python distribution/build_clients.py /tmp/starter.zip /tmp/contextopus-claude-code.zip --client claude-code
```

Use `--platform windows` for the Windows-labelled package. Both shell and PowerShell
launchers are included, sharing one Python installer. This does not establish Windows
or macOS runtime acceptance from Linux tests.

| Client | Delivery | Local verification |
| --- | --- | --- |
| Codex | Portable manifest with OpenAI extension; skills + HTTP MCP | Package structure and native file adapter tests |
| Claude Code | `.claude-plugin/plugin.json`, skills, `.mcp.json` | Native plugin validator passed; package/adapter tests |
| Cursor | `.cursor-plugin/plugin.json`, skills, `.mcp.json` | Package structure and native file adapter tests |
| Hermes | Portable `plugin.json`, skills, `mcp.json` | Native Plugin Doctor passed discovery, parsing and registration; package/adapter tests |
| OpenCode | Shared installer + native MCP/skill files | Package structure and native file adapter tests |
| Crush | Shared installer + native MCP/skill files | Package structure and native file adapter tests |

Native plugin loading, marketplace acceptance, clean dependency download and
Windows/macOS installation are separate acceptance checks, not implied by archive validation. See the release notes for the executed test matrix. Cline and other clients are
not claimed as implemented adapters.

## First setup and reuse

Run the client package's `install.sh` or `install.ps1`; preview with `--plan`.
Missing Python can be obtained through uv during approved setup, never preview.
Choose a durable data folder outside plugin caches. Use `--module` to select
modules and `--skip-model` to defer embeddings. Plugin packages deliver skills
through the plugin, so fresh setup selects no duplicate native file integration.

Existing Core is reused. The installer checks service state and an explicitly
selected root before connecting a file client. Missing selected bundled modules are installed through Core with source revision checks.
Existing module data and model settings are preserved. Setup verifies module operations
and procedures and fails on disabled or incompatible modules instead of claiming success.
Use explicit Core/module update operations for upgrades.

Plugin packages include a `setup` skill to guide this step. No silent installation
occurs merely because an MCP connection is attempted. The HTTP endpoint is shared
by all packages. Plugin removal leaves Core and its durable data intact.

## Before publishing origin

Compare all affected repositories with origin, preserve unrelated local edits,
run relevant tests, build from the reviewed sources and update README/install docs.
Generate immutable client artifacts and checksums. Replace old release links only
when the new assets actually exist. Do not claim unexecuted native-client tests.

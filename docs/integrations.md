# Connect clients to Contextopus

One shared Core service runs at `http://127.0.0.1:8765/mcp`. Data and model state
remain outside client/plugin folders. Installing a client connection does not
create a separate database.

## Client packages

See [client packages](client-packages.md) for native plugin layouts and the
verification matrix. The installer detects an existing Core and preserves its
modules/model; fresh setup uses the shared Python installer. Existing stopped or
incompatible services need explicit repair/update, not a second installation.

## Native file delivery

```console
contextopus integrate claude-code --user
contextopus integrate claude-code --user --apply
```

Supported adapters: `codex`, `claude-code`, `cursor`, `opencode`, `crush`, `hermes`.
Use `--project DIRECTORY` for project scope (Hermes supports user/profile scope).
Hermes supports `--hermes-home DIRECTORY`; see [profiles](integrations/hermes.md).

Default names are full and namespaced: `contextopus-modules`,
`contextopus-workspace`, `contextopus-workspace-search`, `contextopus-agents`,
`contextopus-skills`, `contextopus-sessions`. Only enabled modules contribute skills.
Procedure identifiers remain unchanged when an invocation is renamed.

Select entrypoints and optionally choose short aliases:

```console
contextopus integrate codex --user --skill workspace --skill workspace-search --alias workspace=w
contextopus integrate codex --user --skill workspace --skill workspace-search --alias workspace=w --apply
```

Omitted options reuse the saved per-client selection and aliases. `--all-skills`
resets selection; `--reset-aliases` restores full names. Supplying `--alias`
replaces the saved alias map. `--config-only` changes no delivered skills.
Preview lists canonical identities and installed names without exposing unrelated
configuration secrets. Known file/name collisions stop before changes. A host's
entire plugin command namespace is not necessarily enumerable: native plugin
collisions still require checking in that client.

Integration receipts track installed bytes. Updates retire unchanged owned files;
modified files survive. Source package directories and active plugin caches are
never edited by alias delivery. JSONC requiring comment-preserving edits is refused.

## Plugin delivery

Plugin skills use full names under the plugin namespace, such as
`contextopus:workspace`. Do not also copy the same skills into ordinary client
folders. User aliases for plugin skills must use supported client mechanisms;
Contextopus does not promise an alias API in every host.

Plugin installation is distinct from Core setup. The packaged setup skill can
run the installer after reviewing the user's choices. Until Core is installed and
running, its HTTP MCP connection is unavailable. Plugin activation must not silently
download a model or select a new data directory.

Reload the actual client and verify skill loading and a real MCP read. Written
configuration or a passing package test alone is not client acceptance.

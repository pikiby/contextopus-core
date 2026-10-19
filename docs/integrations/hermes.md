# Hermes native integration

Contextopus connects Hermes to the same loopback HTTP MCP owner used by the
other clients. Core installs its `m` routing skill in Hermes' native skill
directory. Enabled modules contribute their own skills; an installed Workspace
adds its six `w` skills through the same integration preview/apply. Procedures, Workspace settings, storage, approvals and work
cycles remain in Contextopus. Hermes' own memories and sessions remain managed
by Hermes; this integration needs no additional memory provider.

## Verified upstream contract

The compatibility target is the official
[NousResearch/hermes-agent v0.22.2 release](https://github.com/NousResearch/hermes-agent/releases/tag/v0.22.2),
commit `d923a5eb487a17c0a68801bba9ef0f56c81040a8`. Check the release and resolved
tag before running an installer. The moving `main` branch can expose a different
contract. In this stable source, configuration is read from
`$HERMES_HOME/config.yaml`, skills from `$HERMES_HOME/skills/`, and remote MCP
servers from `mcp_servers`. The default home is `~/.hermes` on Linux/macOS and
`%LOCALAPPDATA%\hermes` on Windows; without `LOCALAPPDATA`, Windows falls back to
`~/AppData/Local/hermes`.

Primary source references:

- [Stable installation instructions](https://github.com/NousResearch/hermes-agent/blob/v0.22.2/README.md#quick-install)
  and [reviewable installer](https://github.com/NousResearch/hermes-agent/blob/v0.22.2/scripts/install.sh).
- [Stable configuration](https://github.com/NousResearch/hermes-agent/blob/v0.22.2/hermes_cli/config.py),
  [native home resolution](https://github.com/NousResearch/hermes-agent/blob/v0.22.2/hermes_constants.py),
  [profiles](https://github.com/NousResearch/hermes-agent/blob/v0.22.2/hermes_cli/profiles.py)
  and [MCP lifecycle](https://github.com/NousResearch/hermes-agent/blob/v0.22.2/tools/mcp_tool_lifecycle.py).
- [Stable native reload implementation](https://github.com/NousResearch/hermes-agent/blob/v0.22.2/hermes_cli/cli_info_mixin.py).

## Install and select the native home

Install Contextopus from the verified wheel using the normal
[installation and upgrade sequence](../../README.md#start-from-source). Preserve an
existing data root and selected inference extras. Install Hermes separately
from its reviewed official stable source. Its installer prepares a managed
runtime and dependencies; installing the checkout with an ordinary editable
Python install does not reproduce that runtime.

Review the installer and its runtime downloads before executing it. For this
integration, optional browser and computer-use components are unnecessary;
the stable installer supports `--skip-browser --skip-computer-use`. Configure a
Hermes model/provider using the native setup workflow. Credentials stay in
Hermes configuration; do not copy them into Contextopus, release bundles or
verification reports.

For the verified stable source, download a pinned installer to a file, compare
its SHA-256 below and read it before execution:

```console
curl --fail --location --output hermes-install-v0.22.2.sh https://raw.githubusercontent.com/NousResearch/hermes-agent/d923a5eb487a17c0a68801bba9ef0f56c81040a8/scripts/install.sh
sha256sum hermes-install-v0.22.2.sh
micro hermes-install-v0.22.2.sh
```

Expected installer SHA-256:
`f4cdb0e20f1aca2c3871a76b962fd4db61510f549cf973759c753ac13349beb5`.
Inspect the matching stable repository's runtime manifests as part of the review.
The reviewed Linux command targets the default home:

```console
bash ./hermes-install-v0.22.2.sh --branch release/0.22.2 --commit d923a5eb487a17c0a68801bba9ef0f56c81040a8 --hermes-home "$HOME/.hermes" --dir "$HOME/.hermes/hermes-agent" --non-interactive --skip-browser --skip-computer-use
```

The branch is the verified `release/0.22.2` release branch; the commit pin fixes
the installed checkout even if that branch moves. This installer downloads its
managed runtime, publishes `~/.local/bin/hermes`, and can update shell startup
files to put that directory on `PATH`. `--non-interactive` skips model setup and
gateway service installation. Run the native setup/model selection explicitly
after installation. Preserve an existing Hermes home and review its upgrade
before using these commands against it. Other operating systems need their
corresponding official installer and separate native validation.

If the Linux web build fails, the stable source supports a bounded build mode:
repeat the same pinned installer command with `HERMES_WEB_BUILD_LIGHT=1` before
`bash`. This limits Rolldown to one thread and the V8 heap to 1 GiB for that
invocation. Local verification recovered an initial Node `SIGSEGV` (exit 139)
with this mode, rebuilt the installed web assets and completed the full official
installer successfully. That recovery does not establish the crash's underlying
cause. Keep the original failure log and verify the installer's final exit
status and native diagnostics; there is no need to persist the variable or
change the pinned runtime/source versions.

The adapter requires `--user`. Preview and review affected paths before applying:

```console
contextopus integrate hermes --user
contextopus integrate hermes --user --apply
```

Home selection is `--hermes-home <directory>`, then a nonblank `HERMES_HOME`,
then the platform default above. Explicit and environment paths expand `~` and
environment variables. `HERMES_DATA_DIR_SUFFIX`, when set, appends its literal
value to the platform-default directory name, such as `.hermes-test` or
`hermes-test`; it does not alter an explicit home or `HERMES_HOME`.
To target a named Hermes profile, pass its actual native home directory
explicitly to both commands:

```console
contextopus integrate hermes --user --hermes-home /absolute/path/to/hermes/profiles/work
contextopus integrate hermes --user --hermes-home /absolute/path/to/hermes/profiles/work --apply
```

Hermes can remember an active profile. An integration written into the default
home does not automatically apply to a different active profile. Select the same
home/profile when launching Hermes; `hermes --profile default` explicitly
selects the default profile. Use Hermes' native profile selection for a named
profile. The adapter never changes the active Hermes profile.

The generated configuration is:

```yaml
mcp_servers:
  contextopus:
    url: http://127.0.0.1:8765/mcp
    tools:
      resources: false
      prompts: false
```

The two tool flags disable Hermes' generated resource and prompt wrappers.
Contextopus exposes its four native operation tools; no extra wrappers are
needed for resources or prompts. These are Hermes client settings, not changes
to the shared MCP service.

The adapter writes `<hermes-home>/config.yaml`, canonical
`<hermes-home>/skills/<name>/SKILL.md` files, and its own ownership receipt at
`<hermes-home>/.contextopus/hermes-integration.json`. Native skills are `/w`,
`/w-search`, `/w-create`, `/w-settings`, `/w-context`, `/w-analyze` and `/m`.
`--config-only` is available when those skills are already discoverable.
Each profile keeps its own configuration, skills and receipt.

## Preserve existing configuration

Previewing creates no integration files. Applying preserves unrelated YAML
settings, comments, MCP servers and custom skills. Repeating an unchanged
installation is idempotent. Recognized unchanged managed skills can be upgraded;
custom or edited files with the same short names cause a collision rather than
being overwritten. An existing URL-only `contextopus` entry with the same URL
receives the two tool flags while retaining its existing YAML. A different
`contextopus` MCP definition, including custom tool filters, stops the update.
Changes made after a preview require a fresh preview.

Malformed or ambiguous YAML is refused. When a YAML form cannot be safely
updated, preserve the original and edit it with Hermes' native configuration
workflow, then retry the preview. Do not delete credentials or unrelated
configuration to make integration pass. This adapter creates neither a new
Contextopus data root nor a replacement Workspace.

## Start and verify

Start the shared Contextopus service for the intended existing root using the
normal `contextopus service install` / `contextopus service start` workflow.
Use the same root as other clients. A running service alone does not prove a
Hermes connection.

Launch Hermes in the integrated home/profile. In an already running Hermes
conversation, use `/reload-mcp` and approve its native reload prompt, or restart
Hermes. Stable v0.22.2 reload disconnects and reconnects all configured MCP
servers and refreshes the model's tool list; it can invalidate prompt caches.

Verify all four tools from the actual Hermes session: `guide`, `read`, `write`
and `finish`. Hermes may qualify their names with the server name. Then make a
real bounded read such as `read(operation="core.status")` and check that the
returned root is the intended Contextopus root. For behavioral verification,
after installing Workspace and applying its skill integration, invoke `/w-search` with an explicit request to find and read a known record in
a named disposable context; inspect the actual `guide` and subsequent read
calls. Successful tool discovery does not establish that a model followed the
Workspace procedure. Workspace writes and cleanup continue to follow the
selected context's policy and native client permissions.

If tools are absent, first check the selected Hermes profile, native config
path and service endpoint, then reload. If configuration is correct but a
connection remains stale, restart the same native client and repeat a real
read. Contextopus does not provide a `reconnect hermes` command in this release.

The Core release verifier checks the Hermes client ZIP, the Core `m` skill,
this guide and `SHA256SUMS`. The native verifier explicitly reads the Core
`modules` procedure and resolves `m`; module-specific acceptance is owned by
the corresponding module repository. Python tests and bundle checks do not establish
native OS startup or model behavior. Record local Linux installation and client
test evidence separately; native macOS and Windows Hermes integration have no
live verification recorded by this guide.

The [local Hermes acceptance report](../implementation/hermes-integration.md)
records native tool/skill checks and separately verified model-driven retrieval
and update, including observed mistakes and verification limits.

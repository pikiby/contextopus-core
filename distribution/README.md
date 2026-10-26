# Install Contextopus

Choose the package for **Codex, Claude Code, Cursor, Hermes, OpenCode or Crush**.
Core 1.8 packages use the same runtime and data directory. Download the archive
for your client and platform from the release page.

1. Download the package from the official release and extract it.
2. Run `sh install.sh` on Linux/macOS or `powershell -File install.ps1` on Windows.
3. Review the data directory, modules and model setup; confirm installation.
4. Install the included native plugin where supported, reload the client and
   verify a real Contextopus read. OpenCode/Crush receive native files instead.

`--plan` previews without changes and requires existing Python 3.12+.
`--module ID` selects bundled modules; `--module none` installs only Core.
`--skip-model` defers downloads, leaving semantic search unavailable.
`--yes` accepts the selected setup without interactive confirmation.

Existing Core and model settings are reused. Missing selected bundled modules
are installed through Core; existing modules are checked, not silently upgraded. A stopped,
incompatible or partial installation needs explicit repair/update. A fresh setup
can install uv and Python, but does not install the coding assistant itself.
Dependencies and model weights require network access; the bundle is not offline.
Data must live outside source repositories and plugin caches.

For the shared starter (before client wrapping), `--client NAME` selects native
file integration. Client packages select their own integration automatically;
plugin packages avoid duplicate file delivery.

[Client packaging and verification](../docs/client-packages.md) ·
[Native integration, full names and aliases](../docs/integrations.md)

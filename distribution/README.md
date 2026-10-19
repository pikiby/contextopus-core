# Install Contextopus

The [**Contextopus 1.5.0 starter**](https://github.com/pikiby/contextopus-core/releases/download/v1.5.0/contextopus-starter-1.5.0.zip)
combines Core 1.5.0, Workspace 1.5.0 and Session Search 0.8.0 in one download.
The smaller [**Core-only bundle**](https://github.com/pikiby/contextopus-core/releases/download/v1.5.0/contextopus-core-1.5.0.zip)
uses the same installer with no bundled modules. Both let you choose a data
folder and coding assistants, then use Core's ordinary lifecycle mechanisms.

Download checksums from the [same release](https://github.com/pikiby/contextopus-core/releases/tag/v1.5.0).
Version 1.4.0 assets belong to the earlier combined distribution.

## Start here

1. Download the starter ZIP and its checksum from the same Contextopus release.
2. Verify the checksum and extract the archive into a regular local folder.
3. Open a terminal in its `contextopus` folder and run:

   **Linux or macOS**

   ```sh
   sh install.sh
   ```

   **Windows PowerShell**

   ```powershell
   .\install.ps1
   ```

   If Windows blocks downloaded scripts, inspect the files and follow your
   machine's script policy. The installer does not change that policy.

4. Choose the data folder and clients, review the installation plan and confirm.
5. Reload the selected client and ask it to list Contextopus modules and read an installed
   module procedure. Successful configuration alone does not prove that an
   already-open client has connected.

The installer can obtain Python through **uv**. If uv is missing, the launcher
offers its official, versioned installer before proceeding. Existing uv must be
0.13.1 or newer. **Git must already be installed and available on PATH** when choosing bundled
modules (including Workspace's local history). Core-only setup does not require Git. This starter does not install Git or client
applications. No administrator account is required for the starter itself; a
working user-service manager is required for Core's background service.

## What the bundle prepares

- The exact Core wheel and module files listed in `bundle.json`, checked against
  their SHA-256 hashes before installation.
- A separate Python tool environment with local CPU inference dependencies.
  The CPU backend is selected during dependency installation, as well as during
  model setup.
- Your chosen persistent data folder, Core's user service and selected modules,
  installed through the same lifecycle available to third-party modules.
- The default embedding model through Core's explicit setup procedure, unless
  you choose to defer it.
- Configuration and available module skills for the selected clients: Codex,
  Claude Code, OpenCode, Crush or Hermes. Choosing no client is also supported.

**Internet access is required** for dependencies, Python if needed, and model
weights. These downloads are not included in the ZIP. The bundle pins Core and
module artifacts; it is not a fully offline or universally locked dependency
environment. Package dependencies are resolved by uv for the target platform.

Session Search starts without a transcript source and does not index your
history automatically. Choose a supported source and start indexing separately.
Client applications themselves are not installed by this bundle.

## Preview and explicit options

With an existing Python 3.12 or newer, inspect a plan without installing anything:

```console
python install.py --plan --root /absolute/path/to/Contextopus --client codex
```

Use `python3` where that is the interpreter's name. The launchers also accept
`--plan`; this mode refuses to download a missing Python or uv.

For an unattended installation with an explicit choice of data folder and client:

```sh
sh install.sh --yes --root /absolute/path/to/Contextopus --client codex
```

Repeat `--client` to connect several clients. `--skip-model` defers model download
and setup; an installation made with this option is **not ready for semantic
search**. Run the installed Core's `setupmodel --device cpu` preview and apply
when ready. This does not imply GPU acceleration; configure that separately.

Select only part of the full starter with repeated `--module` flags:

```sh
sh install.sh --module workspace --client codex
sh install.sh --module none --client none
```

The default installs every module present in the archive. `--module none`
installs Core only; unknown IDs and combinations of `none` with other IDs fail
before installation. The Core-only archive needs no module flag. You can add
modules later with `contextopus modules install ID --source /path/to/module.zip`.
The native command also accepts a built folder; append `--plan` to inspect it.

## Existing installations and interrupted setup

This first starter installs into a **new location**. It refuses to overwrite an
existing Core tool, nonempty data folder or another active owner on Core's port.
An existing installation needs the normal reviewed update procedure, preserving
its data, module state, rules and inference configuration.

If a step fails, the installer reports the failed step and retains its receipt
and completed work. It does not erase data, uninstall another application or
claim that the remaining steps succeeded. Automatic recovery of a partial
installation is not provided by this installer; use the recorded steps to
inspect and complete or reverse only that installation.

Linux, macOS and Windows are target platforms. Native service installation,
model downloads and client loading must be verified on each target before they are advertised as tested. Local mocked command tests are not a
substitute for that verification.

## For release maintainers

Build Core and any selected modules using their own repositories. Use a fresh output
directory and add each module's license and notice to its prepared module folder.
The bundle builder takes these explicit artifacts; it neither downloads an
unqualified `latest` version nor reads a user's installed data.

From the Core checkout:

```console
python distribution/build.py --core-wheel /path/to/contextopus_core-1.5.0-py3-none-any.whl --module /path/to/workspace --module /path/to/session_search --bundle-version 1.5.0 --output /path/to/contextopus-starter-1.5.0.zip
```

Omit every `--module` to build the Core-only installer; `scripts/build_release.py`
builds that asset as part of Core releases. The builder writes a deterministic archive, an exact file manifest and an
external `.sha256` file. It rejects incompatible module requirements, duplicate
module identities, unsafe paths and existing outputs. The installer checks the
manifest again before acting. Checksums detect corruption; obtain the archive
and expected checksum from a trusted release.

Before publishing, verify the extracted artifact against an installed Core wheel,
run real module operations, and complete native platform/service/client checks.
Publish the ZIP and checksum together and keep download links tied to that
exact release. Module repositories remain independent; the starter
bundle is a curated installation set.

Core, Workspace and Session Search use Apache-2.0; their license files accompany
the bundled artifacts. Installer command tests and module tests do not establish
that an extracted combined archive installs successfully. The isolated artifact
check is provided in `tests/verify_starter_runtime.py`; it uses a disposable root
and port, with an optional labelled embedding fixture, and does not replace
native installer/model/client acceptance.

uv references: [installation](https://docs.astral.sh/uv/getting-started/installation/),
[installer options](https://docs.astral.sh/uv/reference/installer/),
[PyTorch backends](https://docs.astral.sh/uv/guides/integration/pytorch/).

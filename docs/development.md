# Develop and verify Core

This repository owns the Core runtime, CLI/TUI/MCP, native client adapters,
module SDK, generic examples and the `m` skill. Workspace and Session Search
own their source, domain tests, procedures, skills and module artifacts in
independent repositories. No sibling checkout is required for Core tests or builds.

Core **1.6.0**, Workspace and Session Search have independent release artifacts.
Agents **0.3.0** requires Core `>=1.6,<2`; consult each module manifest for its
compatibility range. Published 1.4.0 assets describe
the earlier combined distribution. Use fresh build output directories and verify
the exact artifacts before installation.

## Install from source

Use Python **3.12+** and [uv](https://docs.astral.sh/uv/). Core alone can be
installed from a clean checkout with `uv tool install --python 3.12 .`. For local
CPU embeddings, use uv **0.13.1+** and include the local extra:

```console
uv tool install --python 3.12 --torch-backend cpu ".[local]"
contextopus --version
```

Choose a persistent data directory outside source and plugin caches. For a new
installation, explicitly select that root when initializing Core:

```console
contextopus --root /absolute/path/to/contextopus-data init
```

`init` prepares Core and installs/starts its native user service. It does not
install optional modules or load embedding weights. A working user-service
manager is required. An existing installation needs the backup and migration
review described [below](#existing-installation).

Build optional modules from their own repositories or download their exact
release ZIP. Inspect the source before running its code through the common lifecycle:

```console
contextopus --root /absolute/path/to/contextopus-data modules install MODULE_ID --source /path/to/module.zip --plan
contextopus --root /absolute/path/to/contextopus-data modules install MODULE_ID --source /path/to/module.zip
```

`--source` also accepts a built folder containing `module.json` and `package/`.
It rejects raw checkouts, unsafe paths, symlinks, mutable state and identity or
compatibility mismatches. Source installation refuses existing module folders
or installation records. For an existing module use the explicit update flow;
for a failed first installation inspect the retained state and retry ordinary
`modules install MODULE_ID` without copying a second source.

Replace `MODULE_ID` with the manifest's ID. Install your chosen modules before
model setup so their setup hooks can run. With the local extra installed:

```console
contextopus --root /absolute/path/to/contextopus-data setupmodel --device cpu
contextopus --root /absolute/path/to/contextopus-data setupmodel --device cpu --apply
```

The first command previews the embedding profile and device. `--apply` performs
setup and an index rebuild and can download model weights. The base installation
also supports an explicitly configured API provider and compatible tokenizer;
see [model setup](architecture.md#explicit-embedding-setup).

After verifying the selected root and installed modules, bind the default root
and open the terminal interface:

```console
contextopus root --set /absolute/path/to/contextopus-data
contextopus tui
```

`--root DIRECTORY` or `CONTEXTOPUS_ROOT` overrides the persistent binding. Keep
one root across clients and inspect integration previews before applying them.
Source installation does not update an existing root's format automatically.

## Tests

```console
uv sync --locked --extra test
uv run --locked pytest -q
```

Tests use temporary data roots. Deterministic test embeddings exercise real
LanceDB storage without downloading models. Integration tests start disposable
local owners and module child processes; network-restricted sandboxes may block
loopback/socket checks. Native Windows behavior runs only on Windows. Core's CI
matrix declares Linux, macOS and Windows on Python 3.12/3.13; local test results
apply only to the environment actually used.

Workspace behavior and historical format/client migration coverage moved to the
[Workspace test suite](https://github.com/pikiby/contextopus-workspace). That
suite requires an explicitly supplied compatible Core checkout or installation.
The real old-writer upgrade check also needs its pinned older writer. Session
Search has its own module tests and optional standalone compatibility checks.

## Build independent Core assets

Build from a clean checkout or a fresh temporary source copy. An older checkout's
ignored `build/` may contain files from the former combined distribution; do not
mix those generated files into a new candidate. Preserve prior artifacts in their
existing location and choose a new output directory for this build.

```console
uv build --no-sources --out-dir /absolute/path/to/new-core-candidate
uv run --locked python scripts/build_release.py --output-directory /absolute/path/to/new-core-candidate
uv run --locked python scripts/verify_release.py --output-directory /absolute/path/to/new-core-candidate
```

The exact asset set is the Core wheel/source archive, five client ZIPs and
`SHA256SUMS`. Client bundles contain Core's `m` skill, license files and connection
instructions. Optional modules and their `w` or session skills are obtained from
their own repositories and installed through the generic module lifecycle.
`verify_release.py` checks source identity, archive membership, license metadata,
CLI entrypoints, resources and hashes. It rejects optional module code in Core
artifacts.

## Verify an installed candidate

Use a disposable environment and the exact local wheel; do not replace a live
installation just to verify packaging. Run its Python interpreter in isolated
mode against this checkout's verifier:

```console
/path/to/disposable/bin/python -I scripts/verify_installed.py --expected-version 1.5.0 --prefix /path/to/disposable
```

On Windows use the environment's `Scripts/python.exe`. The verifier checks the
installed package/CLI/resources, bare-Core MCP surface and a generic folder module
through real child handlers, SQL and owner restart. All data is temporary. It
does not install an OS service, change client configuration or load model weights.
Module repositories provide their own explicit integration checks against Core.

## Existing installation

Back up the whole root coherently before an accepted upgrade. Preserve records,
IDs, sources, user rules/settings, pending work, module enablement and inference
extras. Test migration on an isolated copy; inspect client integration previews
before applying them. Building source artifacts or passing a temporary check
does not prove a live upgrade or a successful end-to-end model/client workflow.

Historical [release notes](releases/1.4.0.md) and implementation assessments
record their original release conditions. They are not current instructions for
building the separated repositories.

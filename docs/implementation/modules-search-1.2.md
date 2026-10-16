# Modules and search update: implementation evidence

## Implemented scope

The 1.2.0 checkout implements folder-module lifecycle and native skill contributions; independent instruction approval; `w-context` discovery; five shared selection algorithms with scoped settings; derived algorithm discovery; bounded search evidence/replay; and bundled Workspace documentation with recovery-aware setup and updates.

The work used delegated implementation and independent integration review. Existing working-tree changes were preserved. The local implementation checks below preceded publication; they did not migrate the live data root or replace installed clients.

## Local verification

Verified on Linux with Python 3.12:

- Full pytest run: **549 passed, 64 subtests passed, 6 skipped, 1 failed**. The sole failure was a native integration fixture hardcoding plugin cache version 1.1.0 after the application became 1.2.0. It was changed to use installed distribution metadata. The corrected test and the complete delivery/instruction-policy/module lifecycle/interface subset then passed: **52 passed**. No application behavior was weakened for the fixture.
- Build and release verification: wheel, source archive and four client bundles; SHA256 manifest; exact wheel code/resource comparison; guides and module examples present in the source archive.
- Isolated wheel installation: CLI reports 1.2.0; installed-package API lists five algorithms and six skills; new instruction procedure and base plan are available. Read-only discovery does not create a root, and explicit init without a model reports `model_setup_required`.
- Public temporary-root integration: module discovery/prepare/enable/update/disable; cross-context operation reconciliation; unchanged user data/configuration; failed-update recovery; enabled module skills with custom-file preservation; algorithm catalog refresh/change/removal and stale reporting; settings replacement after provider disable; base-context indexing, changed/deleted-document conflicts, partial-apply recovery and model-profile changes.
- Search checks distinguish fragments and materials, retrieval and evidence limits, instruction eras, request-only settings, and labelled replay from unestablished answer quality. Tests use explicit offline providers; they are not semantic-quality benchmarks.
- The Synk example performed only the installed command's version lookup, not synchronization.

The logs used for this check are local temporary artifacts, not a permanent project history. Re-run the documented checks for another revision; this report records their scope and outcome.

## Publication checks and delivery boundaries

Publication review fixed case-insensitive module skill collisions and resolved bundled executable paths before subprocess launch on Windows. The module lifecycle/native suite passed all 20 tests. New actual Textual screenshots use explicitly synthetic fixtures; their capture helper and PNG renderer completed successfully outside the restricted sandbox.

The first [publication CI run](https://github.com/pikiby/contextopus-core/actions/runs/38844011702) exposed a test fixture reading the removed `w-find` file from `HEAD`: 551 other tests and 64 subtests passed on Linux. The fixture now uses exact shipped bytes with a fixed digest and exercises both LF and CRLF, independently of checkout history. Windows also exposed a POSIX-only test path comparison; it now checks containment with `Path.is_relative_to`, preserving the assertions for the original environment and fingerprint. These corrections do not weaken production checks.

Publication requires all six [CI matrix jobs](https://github.com/pikiby/contextopus-core/actions/workflows/ci.yml) to pass on the release revision: Linux/macOS/Windows with Python 3.12/3.13, tests, package build, asset verification, wheel installation and CLI. The workflow's recorded result is the evidence for that revision. Native OS startup and model-driven client turns are not covered on all hosts. Publishing the release does not upgrade the user's working installation.

Prepared assets are under `dist/`. See [1.2.0 notes](../releases/1.2.0.md) for the upgrade sequence and [base context](../base-context.md) for setup outcomes and conflict handling.

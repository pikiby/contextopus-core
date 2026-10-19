# Contextopus 1.0.0 transition

> Historical document: release/verification conditions below apply to the named
> version or dated check. The independent repository layout is unreleased; see
> [current development instructions](../development.md).

## Source baseline

The transition began from the preexisting dirty 0.14.0/v4 working tree, whose Git
HEAD was 0.13.0. That is the original baseline, not the current release state.
The tracked patch, status and preexisting package/document copies were preserved
in the delivery baseline before implementation.

## Accepted delivery

- [x] Contextopus identity: `contextopus-core` distribution, `contextopus` import/CLI, private `pikiby/contextopus-core` repository.
- [x] Python 3.12+ standalone application with one loopback HTTP MCP resource owner; persistent data lives outside client caches.
- [x] Shared Application/operation registry, Workspace module, settings, model setup and TUI use the same service/API.
- [x] Canonical progressive procedures retain selection, implicit-update, source-reading, review/approval and migration constraints.
- [x] Native integrations preserve unrelated configuration, reject collisions/stale previews and retain edited skill files for review.
- [x] Literal Codex `$w` and seven other bare skills use direct native integration; optional plugin delivery exposes namespaced skills. Both plugin caches remain preserved and disabled in the selected direct installation.
- [x] All four native clients connected. Fresh Codex read status/procedure and discovered eight bare skills; OpenCode/Crush independently discovered the shared eight skills.
- [x] Authorized migration verified 27 contexts, 235 cards and the file receipt, preserving originals, IDs, links, instructions, Current/tmp, pending approvals and history. Default root binding uses the migrated root.
- [x] Existing pinned Qwen CPU profile/cache preserved; real search/read succeeded after migration.
- [x] Current project knowledge and PROJECT were applied through the new MCP and read back by the lead. Post-restart selected Workspace contains 43 materials (36 reviewed records updated), pending/outstanding work is zero, and the active cycle/task survived owner restart.
- [x] Linux/macOS/Windows × Python 3.12/3.13 full tests, build, artifact verification and wheel installation passed.
- [x] Final standalone wheel and four client bundles built; resources and SHA256SUMS checked; outside-checkout installation verified.
- [x] Installed TUI passed a real 79×24 PTY smoke: selected Settings remained visible; Settings → Q back → Q exit succeeded; owner and settings revision stayed unchanged.
- [x] Final documentation records the accepted behavior, performed checks and material limits. GitHub tagging/publication follows the lead's final release gate.

## Evidence and limits

The full CI matrix passed for implementation commit `615669e7b56ad037cbdcd61f0dca667bbc27c7ea`:
[run 38671106182](https://github.com/pikiby/contextopus-core/actions/runs/38671106182).
Linux/macOS jobs each reported 372 passed, 6 skipped and 64 subtests passed;
Windows jobs each reported 351 passed, 27 skipped and 53 subtests passed.
Windows retains portable Core/Workspace/LanceDB/HTTP tests; extra skips cover
legacy POSIX shell launchers and POSIX access-mode checks. External Codex/model
fixtures require their explicit opt-in provisioning.

Headless TUI media uses synthetic EXAMPLE data. Five legacy contexts still need
complete human-reviewed instructions before initialization. Session search uses
an independently running compatible service and reports unavailable when absent.
Fake-hardware/model tests prove device propagation and atomic failure handling,
not real GPU inference. Native discovery/connection checks do not establish a
model-driven full workflow in every host. GraphFrontier and the skill registry
remain future integrations. No PyPI publication is part of this delivery.

## Repeated upgrade and release

Fetch the canonical `upgrade` procedure through `wu` (MCP `procedure` operation).
It reuses format upgrade, bounded durable relocation plans/receipts/rollback,
index namespace upgrade, default-root binding and managed native integrations.
It preserves the selected direct/plugin mode, refuses unknown/user-edited skill
collisions and retains active-session caches.

Release verification uses the locked environment, full tests, `uv build`,
`scripts/build_release.py`, `scripts/verify_release.py` and an outside-checkout
wheel installation. The release wheel must match the installed artifact. The
lead coordinates the final tag/publication gate after those checks.

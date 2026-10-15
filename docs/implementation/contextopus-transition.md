# Contextopus 1.0.0 transition

The existing 0.14.0 working tree is the source, including uncommitted v4 work. HEAD is 0.13.0; comparing only HEAD loses that distinction. Delivery baseline: `/tmp/contextopus-delivery-baseline` (tracked patch, status and preexisting package/doc copies).

## Acceptance and ownership

- [x] Identity: Contextopus; distribution `contextopus-core`; import `contextopus`; command `contextopus`; target private repository `pikiby/contextopus-core`.
- [x] Root Python 3.12+ package; optional local embeddings; canonical resources included in wheel.
- [x] Core/Application/registry and Workspace reuse the existing implementation (core owner).
- [x] One loopback HTTP MCP owner; thin native Codex/Claude Code/OpenCode/Crush configuration adapters.
- [x] Canonical procedures retain selection, implicit-update, source-reading, review/approval and migration constraints; native skills fetch them progressively.
- [x] Integrations preview affected paths, preserve unrelated configuration, refuse naming collisions and stale previews, avoid printing existing secrets.
- [x] TUI implementation and actual headless captures with synthetic data; live readiness remains separate (UI owner).
- [x] Shared test environment and initial wheel/sdist clean installation. Delivery/settings/backend: 16 passed including two-client HTTP MCP; native host verification remains pending.
- [x] Final build and isolated wheel check completed. Full suite: 337 passed/6 skipped, followed by 34 targeted tests and both repaired stdio subtests; CI remains the cross-platform gate.
- [ ] Linux/macOS/Windows CI passes; release assets and SHA256SUMS checked.
- [x] Private GitHub rename, local directory rename with compatibility symlink, and CPU-only uv tool installation verified outside checkout.
- [ ] Data/native rollout and GitHub Release publication. Do not publish to PyPI. Current user authorization covers GitHub rename, local rename, card updates and installation; the lead coordinates execution after validation.

## Delivery sequence

1. Preserve the working tree; agree module/API/resource boundaries.
2. Build standalone Application and common operations; adapt transports to that API.
3. Test semantic invariants, migration, relocation receipts, central service ownership and configuration collision handling.
4. Build wheel/sdist and versioned client bundles; inspect package resources and install wheel in an isolated environment.
5. Gather genuine TUI captures and validation evidence; finalize release notes.
6. After the internal validation gate, rename private repository and local checkout, install from verified wheel through uv, merge native configurations, verify each actual client and publish GitHub Release only after CI passes.

## Current evidence boundaries

A generated config does not establish that a client connected. A built artifact does not establish clean installation. A TUI snapshot does not establish model readiness. Unknown metrics stay unknown. GraphFrontier is a future integration; an external skill registry is an idea; session search depends on the independently installed indexer and must be reported unavailable when absent.

## Final release lane (after the lead's code-freeze gate)

```console
uv lock --check
uv sync --locked --extra test
uv run --locked pytest -q
uv build --no-sources
uv run --locked python scripts/build_release.py
uv run --locked python scripts/verify_release.py
```

Then install the exact verified wheel into isolated temporary uv tool/bin directories and verify the installed command from outside the checkout. The first clean-wheel check already passed; rerun for the final artifact because Core/TUI subsequently changed. Record the final full-suite totals and CI URLs in release notes. Live installation, private GitHub rename and publication follow the lead's quality gate.

Additional implemented checks: explicit model setup diagnoses CPU/CUDA/MPS without weights, preserves the active pinned profile, delegates switching to Core's atomic rebuild and refuses stale/unavailable-device plans. Fake-hardware/provider tests exercise both actual Application API and HTTP MCP with real LanceDB; they establish configuration propagation and atomic failure behavior, not real GPU inference.

# Contextopus 1.3.1 patch evidence

## Scope and reproduced layout

The actual migration after the 1.3.0 cutover was blocked by vault discovery:
the selected root and an ancestor both contained `.obsidian`. The isolated copy
used for prior migration acceptance did not have that ancestor. The patch
prioritizes the selected root's own vault boundary while retaining the other
ambiguity and path guards. No user directory deletion is part of this fix.

## Acceptance boundaries

The 1.3.0 baseline commit `69023683766c9aea217e2391b7a6dc1ccffdac03`
passed all seven CI jobs. Its published tag, assets and original receipts remain
historical evidence for that package.

The focused source checks passed eight distinct cases. Seven passed in the
scoped batch; the remaining new unit fixture was corrected to declare its open
layout and passed separately. This is not a full-suite or native-platform pass.
The pre-fix MCP reproduction returned `ready=false` for the same nested-vault
blocker. After the fix, the standard SDK in-memory MCP transport completed
preview/apply/read/replay, retaining Unicode aliases, stable IDs, graph endpoints,
content/revisions and both vault directories without document reembedding.
Evidence: `/tmp/contextopus-v131-nested-vault-fix-evidence.json`.

The packaged 1.3.1 patch completed its installed-wheel nested-vault MCP check and
[all seven platform CI jobs](https://github.com/pikiby/contextopus-core/actions/runs/39002613425)
at `4107050440054c9eaa43f58a54c920fdfac1d3d8`. Its wheel SHA-256 is
`39a0aa09ccc256f50001bcfd907367eb767fe0b2db9a17f3069d3f919313bce9`.
[Release 1.3.1](https://github.com/pikiby/contextopus-core/releases/tag/v1.3.1)
was published and installed after a second verified whole-set snapshot. The live
migration then completed with the existing root, CPU profile, both vault markers,
rules, IDs, graph and pending work preserved. Source, installed-wheel and native
platform counts remain separate; the focused counts above are historical.

The [delivery record](contextopus-1.3.md#final-delivery-released-and-installed-131)
records preservation and native-client outcomes, including the remaining model
behavior limits. Live still runs 1.3.1 at this delivery checkpoint. The later
1.3.2 runtime has separate technical verification and independently reviewed
controlled-corpus OpenCode/Crush model checks. Those bounded results are recorded
in the delivery record; they do not replace or relabel the 1.3.1 evidence.

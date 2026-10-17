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

The 1.3.1 change requires its own focused link/migration checks, an installed-wheel
MCP reproduction with a nested vault and ancestor vault, and the existing
platform CI. Source test counts must remain separate from installed-wheel and
native platform results. Unchanged model scenarios are not rerun automatically.

This file currently records preparation, not completed 1.3.1 acceptance. Exact
source/artifact identities, executed checks and any live result will be recorded
after the reviewed fix is packaged. Publication and live installation remain
separate steps.

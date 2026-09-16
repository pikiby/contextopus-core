# Persistent Context Workspace

Version 0.7.0 defines one `$pcw` skill and a persistent local MCP server. This plan records the adopted design and the acceptance boundaries for its implementation.

## Responsibilities and workflow

User instructions define role authority. PCW belongs to the primary: it reads memory, prepares assignments, manages models/reasoning, saves substantive returns, applies Current/knowledge/links/compaction and authorized memory Git operations. Workers receive only complete standalone task text with needed facts and explicitly allowed sources. They must not use PCW or discover/read/change `.pcw` through files, shell or scripts. The current scope is an assignment-level prohibition, not technical isolation.

The primary launches native agents in separate contexts and binds actual session IDs. PCW does not dispatch agents or intercept completion. Worker-side `pcw_assignment_get` is removed. Only `handoff.launch_message` is sent; IDs, memory coordinates, environment/map and bookkeeping remain primary-only. Environment changes require the primary to refresh the model map.

## Results and preparation

Contentful work/check assignments receive separate MCP-generated filename IDs, including continuations. Primary saves exact raw Markdown, UTC time and executor session metadata, reads it and assesses it. An identical retry is idempotent. Conflicting actual/saved text is outstanding work until explicitly resolved. Compaction need not retain provenance.

Semantic helpers receive source text with end positions and return only boundaries. Primary calls `pcw_submit_boundaries`; original parts are reconstructed with full coverage and revision checks, then the existing provider/LanceDB path indexes them. Boundaries and operation evidence remain service state, not knowledge. Current and checkpoints do not require worker assignments or technical knowledge reports.

## Persistent task state and verification

The independent control store retains the request, assignments, actual sessions, result processing, check plan and discrepancies across compaction or index loss. Current focus is taken from the registered request. Explicit `pcw_task_update` requires its request revision and a reason, preserving unfinished work. Default checkpoint policy is `not_authorized`; an actual permission/prohibition is distinguished and respected.

Primary records intermediate/final factual checks by complexity, and adds checks for unexpected mismatches. A return alone never causes another checker. Observations of real sources/behavior, including no-change research, inform acceptance. `finish` checks the saved plan, outstanding assignments/discrepancies, Current, affected indexed materials and required authorized checkpoints.

## Validation boundaries

Test content preservation, new IDs, metadata, conflicts, service handling, Current synchronization, recovery, planned checks and checkpoint authority using temporary state and test vectors. Exercise the MCP schema/stdio contract separately. Run bounded native assignments to inspect the actual handoff and return. An instruction-compliant run is not proof of technical access isolation.

Existing search/provider mechanics and the [search assessment](docs/search-assessment.md) remain unchanged. Historical reports about workers applying memory changes describe the old design and are not acceptance evidence for this change. Existing user knowledge is not migrated or cleaned by this update. Release, installation and publication are separate from these local implementation changes.

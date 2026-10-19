# Workspace temporary memory

> Historical document: release/verification conditions below apply to the named
> version or dated check. The independent repository layout is unreleased; see
> [current development instructions](../development.md).

## Accepted behavior

Temporary memory is optional. Use `.tmp` for shared assignments, reusable inputs,
intermediate evidence and handoff between agents. Direct knowledge corrections
do not require a temporary report. Native agent messages carry assignments and
references; Contextopus does not schedule agents or choose their models.

Text materials reuse Markdown cards, stable YAML IDs, descriptions and links.
Readable names describe their content. Ordinary links and required sources use
the existing mechanisms. Temporary materials may reference temporary or
permanent materials; permanent knowledge must not depend on temporary files.

Keep the user's original request and relevant clarifications verbatim, separate
from interpretation. At a new task or cycle, inspect unfinished work and decide
which materials to reuse, update, preserve as verified knowledge or remove.
Update obsolete working text or delete it. No mandatory report-disposition
ledger or obsolete comments are introduced.

Completion cleans the selected work's remaining temporary data after necessary
knowledge changes and indexing. Pauses and handoffs preserve needed materials;
cleanup must respect other work and incoming links. A separate
`cleanup_approval_required` controls user approval. New contexts default to false;
users can enable it. Existing explicit values and the legacy fallback are preserved.
It does not change existing knowledge or instructions approval choices. Expose
`finish` as its own MCP tool so native clients can authorize that operation
independently of the universal write tool.

Permanent records receive a derived `context/<name>` YAML tag for visualization.
The owning context remains the source of truth and search category. Preserve
other tags. One normalized name rule prevents context-name collisions across
creation and migration; never merge existing collisions silently.

## Implementation sequence

1. Reuse card parsing, naming and links for optional temporary materials. Add
   bounded cycle discovery, verbatim requests/clarifications, safe edits/deletes
   and cleanup previews. Retain independent work and exact revision checks.
2. Derive context tags and enforce portable name uniqueness under existing
   storage locks. Keep reads non-mutating.
3. Migrate format 4 to 5 with recoverable snapshots. Preserve unfinished work,
   IDs, reviewed proposal bytes/approval bindings and original instructions.
   Update temporary paths and identify invalid permanent-to-temporary links.
4. Update the shared operation registry, MCP, CLI/TUI access, policy defaults,
   procedures, short skills, built-in documentation and package validation.
   Remove contradictory active procedures; mark old design documents historical.
5. Verify direct edits without fake reports, worker handoff, required-source
   reading, stale revisions, dependency-aware cleanup, both cleanup policies,
   name collisions, custom tags and retryable migration with pending proposals.
   Run the relevant existing suite and package smoke checks. Report native model
   behavior separately from transport and deterministic tests.

## Delivery boundary

The user authorized implementation and verification. Publication, remote pushes
and deletion of unrelated live cycles are not part of this implementation task.
Preserve existing working-tree changes and record actual verification outcomes.

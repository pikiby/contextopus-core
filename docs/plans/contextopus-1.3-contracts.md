# Contextopus 1.3 implementation contracts

These contracts implement the [accepted plan](contextopus-1.3.md). They describe
the target implementation; passing tests and delivery evidence establish completion.

## MCP entrypoints

The default advertised tools are `guide`, `read`, and `write`. The MCP server is
named Contextopus; the host adds its namespace. Do not duplicate the brand in
the tool names.

- `guide(procedure=..., operation=..., catalog=false, work_root=..., context=...)`:
  choose one of procedure, operation, or catalog. With no selector, return the
  Workspace procedure. `operation` returns one registry-generated signature;
  `catalog=true` explicitly requests the operation catalog. Module procedures
  retain their existing addresses. This tool never performs the described action.
- `read(operation, arguments, work_root, context, workspace, detail="compact")`:
  dispatch a query through the existing registry.
- `write(operation, arguments, work_root, context, workspace, detail="compact")`:
  dispatch a mutation through that same registry and its approval checks.

`context` and `workspace` are equivalent coordinates; conflicting values fail.
Module-qualified operation names remain stable. `detail="full"` returns the
complete operation response. Unknown signatures are obtained directly through
`guide(operation=...)`, without first downloading the general procedure/catalog.

Old MCP tool names can be enabled explicitly for transition; they are not added
to the default tool list. Integration adapters and probes must use the new tools
and handle an older server deliberately, not retry a failed mutation speculatively.

## Response presentation

Compact presentation runs after the operation and observation/journaling. It must
not mutate the internal result or discard the evidence retained for analytics.
Presentation is shared by the new MCP entrypoints. Full internal operation data
remains available to other interfaces and explicit detailed inspection.

- Search material results have metadata and author-written description, no excerpt.
  Explicit fragment output and full detail preserve the requested text.
- Read/startup/apply material objects expose one `links` list of labelled target
  objects, replacing the raw-ID plus `link_targets` duplication. Proposal inputs
  continue to accept IDs and `@key` references.
- Keep ID, path, owning context, revision needed for writes, type, nonempty status,
  body on reads, required sources, meaningful warnings and actionable errors.
- Omit empty optional material metadata, empty problem lists and normal success
  receipts for analytics/indexing. Preserve failures, incomplete writes, pending
  indexing and history failures. Do not remove false/0 from settings or diagnostics.
- Search diagnostics retain scope, algorithm, effective limits, counts, boundary
  reasons and completeness. Candidate snapshots stay in full detail and analytics.

## Authoring and graph

YAML `id` is the stable identity. YAML `links` contains quoted Obsidian wikilinks
with real vault-relative paths. Aliases are display names, not invented descriptions
or assertions about an edge. Normalized runtime graph edges remain stable IDs.
Legacy plain-ID links remain readable during migration.

Resolve the complete catalog before resolving links. Missing/ambiguous targets
produce explicit diagnostics; never invent identity from a title. The common data
root is the default vault root; an unambiguous enclosing configured Obsidian vault
may establish its actual root. Hidden legacy PCW paths are migration inputs, not
promised Obsidian-visible storage.

Rename proposals include affected local inbound links in review. A foreign-context
inbound link prevents an unreviewed cross-context rewrite and identifies the action
needed to resolve it. Migration preserves graph endpoints and IDs.

New records require a nonempty author-supplied description. An actual body change
requires the author to submit its reviewed description, which may equal the old
description. Identical body submission and metadata-only edits do not force legacy
repair. Existing records remain readable; audit identifies description gaps.
There is no generated title/excerpt fallback and no separate acknowledgement flag.
The body-size limit applies to creation and actual body changes; metadata, link or path edits preserve an unchanged oversized legacy body without requiring a split.

Required sources retain reference/instruction and fresh checking on every receipt.
They are not replaced by ordinary graph links.

## Settings and migration

The new Workspace format is 4; the package release is 1.3. These are independent
versions. Existing Core JSON configuration is the canonical machine-settings store.
Migrate the six existing policy values with their effective legacy defaults intact.
Remove only recognized policy frontmatter keys from INSTRUCTIONS; preserve unrelated
metadata and the full free-form body. Never leave ignored settings looking active.

Add `reread_instructions=false`. An optional explicit agent/model profile may
override rereading only. Do not infer the model from the environment or share a
server-side "already read" flag. Lightweight settings reading returns selected
effective values and their origins without loading instructions or project text.

Policy writes use the Workspace settings review/apply procedure under the current
instructions-approval policy. Generic Core settings/request overrides cannot bypass
that policy. Effective settings revisions bind new proposals to their review basis.

Settings previews and application receipts survive owner restart in the existing
Workspace control store. Retry verifies the exact before/after configuration and
does not include a later edit in an earlier approval or Git snapshot.

Git stores historical effective settings and their origins at the virtual path
`.contextopus-settings.json`. This is a historical representation, not another live
configuration file. The history index marks that path skip-worktree so a missing
physical copy is not reported as a deletion. Settings changes receive the same
captured-snapshot retry guarantees as knowledge; disabling history records the
last change when the previous policy enabled it. Analytics references the observed
historical settings separately from free-form instructions. Missing old evidence
remains unknown, never reconstructed from current defaults.

Preserve pending cycles and immutable proposal bytes/revisions. Translate legacy
technical paths/policy representation through a validated execution overlay. Do not
silently ignore a pending proposal's policy changes or transfer approval to different
meaning. A non-equivalent conflict blocks only the affected apply with an explicit
reprepare path. Interrupted application remains recoverable.

## Retrieval

For material output, group fragments by document identity before relevance-boundary
calculation and the material cap; the nearest fragment represents that document.
Fragment mode operates on fragments with explicit units. Apply this consistently
to all applicable built-in algorithms and version changed semantics.

Distinguish retrieval candidate caps, relevance cuts and result caps. Diagnostics
must not call a capped result complete or call a result cap an observed gap.
Historical replay checks the recorded algorithm version and snapshot coverage.
The selected algorithm/default is not changed as a side effect of these fixes.

## Module installation and storage

An author supplies a root-local module following the shipped guide. The user puts
it under modules and requests installation through one short skill. Core owns the
single install path used by MCP, CLI and TUI: dependencies, schema preparation,
compatibility checks and operation activation. Inspection never performs those writes.

The optional manifest storage contract declares sqlite, the target schema version,
an ordered migration directory and explicitly supported schema versions. Ordinary
SQL migrations ship with the module. Core owns the shared domain catalog at
core/storage/modules.sqlite3; it is separate from analytics. Table namespaces and
the applied-version/checksum ledger prevent accidental collisions and silent edits
to applied history. Pending SQL and its ledger commit atomically. No implicit
downgrade, disable-time data deletion or per-module vector database is introduced.

Root-local handlers obtain a scoped Core storage API through an optional versioned
parent/child protocol. Legacy handlers keep their existing JSON interface. Read
operations cannot use write access, and the storage API cannot modify another
module's objects. Trusted module execution remains outside an OS security sandbox.
Native modules use the same service; shared vectors remain in Core RAG.

Activation requires a compatible committed schema. Failed updates and interrupted
switches must not restore old code over an incompatible new schema. Durable state
and explicit recovery distinguish prepared data, enabled operations and unresolved
errors. Existing native/daemon ownership conflicts are reported, not silently
replaced. The example tests the shared installer, not an unrequested migration of
the user's external session-search catalog.

## Procedure lifecycle

One concise Workspace procedure contains the complete ordinary work sequence and
the direct addresses of independent procedures. Never perform an action without
obtaining its applicable procedure. Ordinary stages do not require guide calls.

Read complete free-form INSTRUCTIONS for a new independent task, an explicitly
selected context, changed rules, or lost rule text. Refresh used procedures after
a plugin update. In forced-rereading mode, also reread on each invocation. Repeated
`$w` and follow-up questions do not by themselves create a new task/cycle.

Read-only retrieval does not start a write cycle. Work still requires result
comparison, actual change review, applicable approval, verified persistence and
proper completion. Pass applicable cross-cutting rules to delegated workers.

## Delivery acceptance

Verify direct 1.1 → 1.3 and 1.2 → 1.3, idempotent retry, interruption and rollback.
An isolated migration must preserve IDs, rules, sources, settings, graph endpoints,
history and pending work. Semantic description repair is separately reviewed.
Release, installation, process restart and a real client operation are distinct
checks. Do not claim one from another.

# Contextopus 1.4 implementation and verification

## Delivered behavior

Workspace temporary memory is optional. Reusable assignments, inputs, findings
and handoff use Markdown cards in `.tmp`; direct knowledge corrections need no
fabricated report. Stable YAML IDs, descriptions, ordinary links and required
sources reuse the existing record mechanisms. Temporary evidence is outside
permanent search and Git history.

The procedure preserves the original request and relevant follow-ups, reuses
active work, and reviews existing temporary materials before starting another
task. Agents update or remove obsolete working text rather than accumulating a
disposition ledger. Native agent communication carries references to shared
materials; Contextopus does not schedule agents.

The dedicated MCP `finish` tool and `workspace.tmp_delete` use the independent
`cleanup_approval_required` policy, false by default for new contexts. Existing
explicit choices and the legacy fallback remain unchanged. Exact revisions, pending
proposals, indexing and incoming dependencies still protect the selected data.
The setting does not override the host client's permission system.

Permanent records receive the derived `context/<owner>` tag without replacing
user tags or introducing a second ownership filter. Context creation and
migration use NFKC/case-insensitive name uniqueness under the common root lock.

## Compatibility and migration

Format 5 preserves IDs, instructions, existing policy values, unfinished work,
immutable proposals and review/approval bytes. Recoverable snapshots and
execution overlays relocate temporary paths. Binary attachments retain their
bytes. Portable temporary filenames avoid Windows reserved names and Unicode
or case collisions. Interrupted relocation can resume at each tested boundary.

New migration snapshots use the hidden control directory `.backups`. Recovery
continues to accept existing receipt paths under `backups`. Both directory names
are excluded from recursive control snapshots. The hidden-directory and legacy
recovery tests passed (four focused cases and 58 related regression tests).

Migration does not execute a previously blocked instructions proposal. A
proposal-specific restriction remains attached to that proposal. Historical
malformed source declarations retain their text and receive a precise diagnostic
instead of blocking unrelated contexts. An unresolved external `tmp/...` source
is not sufficient evidence of a Contextopus temporary dependency.

Active procedures, defaults, packaged documentation, legacy skill redirects,
the shared operation registry, MCP and release/install checks are updated
together. User-authored instructions are preserved, not silently overwritten.

## Verification record

This section records the original pre-Hermes checkpoint. The Hermes follow-up
below records the later client, package and installed-file inventories.

- Linux regression run before the final creation-default adjustment: 875 tests
  passed, 10 skipped, 64 subtests passed in 358.65 seconds, including fixes
  discovered on the real-data rehearsal.
- Final creation-default adjustment: 86 runtime/default tests passed; 30 contract
  and base-context tests plus two subtests passed; 19 Workspace settings tests
  passed. Delivery and legacy-adoption tests passed. Explicit-approval scenarios
  now choose true, and a new base-context test verifies automatic cleanup under
  the false creation default. The final wheel passed isolated MCP/module smoke
  and the installed creation-default check.
- Clean wheel environment: version 1.4.0, four advertised MCP tools, seven native
  skills, five algorithms and the matching base-documentation bundle.
- Installed module test: schema installation through MCP, linked rows through
  the packaged child bridge, and preserved rows after owner restart.
- Historical release packaging: wheel, source archive and four client ZIPs verified against
  their manifest and canonical packaged resources.
- Physical-data rehearsal: 29 contexts migrated, 429 permanent IDs and bodies
  preserved, every context tagged, all 29 instruction files and cycle registries
  unchanged, 56 unfinished cycles retained and 174 prior policy values preserved.
  Independent verification checked 503 temporary files, 240 immutable
  proposal/review files and 6,716 recovery-backup hashes with no errors.
- Fresh native Codex connection: four tools and seven bare skills discovered;
  real Core status and upgrade-procedure calls reached the selected data root.
- At that checkpoint, all 123 installed source/resource files matched the source
  bytes. Existing
  Codex, Claude Code, OpenCode and Crush integration previews require no changes.
- Independent live-data verification: all 29 contexts reached format 5 with
  complete migration receipts. All 429 permanent IDs, bodies and custom tag sets,
  29 instruction files, 174 prior policy values and 56 active cycles were retained.
  All 429 records have their derived context tag. Verification checked 507
  temporary files, 262 temporary bodies, 242 immutable proposal/review files and
  6,720 recovery-backup hashes with zero errors. These counts describe migration
  preservation before the subsequent, separately reviewed documentation updates.
- Real MCP search and reads after migration returned indexed project records and
  readable temporary cards, with no pending, unregistered or correction records
  in the selected development context. Base documentation was updated to 1.4.0.

This original checkpoint records Linux runtime and transport evidence, before
the later cross-platform CI work and release preparation below. It is not a claim
that every model follows the procedure or a statement about final publication.

## Local deployment checkpoint

The verified wheel is installed locally as 1.4.0 with the prior CPU inference
extra and all 79 dependency pins retained. The single shared service restarted
against the existing data root. A coherent data/configuration backup and the
prior 1.3.3 wheel were retained before replacement. Live format conversion and
its independent post-check completed successfully for all 29 contexts.

Nine existing development-context records were updated through reviewed MCP
proposals to describe the installed behavior, settings, completed implementation
and verification limits. Rules remained unchanged; Git history is disabled for
that context, so these saves did not create context-history commits.

The user approved cleanup of this delivery's completed development cycle
(101 temporary files) and base-documentation update cycle (two applied proposal
files). Both closed through the dedicated MCP `finish`; their temporary
directories are absent and their permanent records remain. Other unfinished
work was preserved. The final creation-default adjustment is installed: the live
MCP returned `cleanup_approval_required=false` for creation, all 123 installed
source/resource files matched that checkpoint's source, and the 29 existing context
configuration files remain byte-identical. The packaged rule template was also
updated in the base documentation context.

The user deferred cleanup of the final defaults-adjustment cycles: four applied
proposal files in the development context and two in the base context remain.
No knowledge save or indexing work is pending in those cycles; their six
temporary files are retained by explicit user choice.

## Hermes follow-up

The native Hermes adapter reuses the single HTTP MCP owner and canonical skills.
It preserves unrelated YAML, edited skills and the existing Contextopus root;
native home/profile selection follows the verified stable Hermes 0.22.2
contract. This follow-up adds no separate Core storage or memory provider.

- The final targeted regression run passed 127 tests. A new clean-wheel smoke
  check passed independently of the existing local installation. The native
  verifier also covers explicit UTF-8 handling, required Windows home variables
  and relative interpreter paths across working-directory changes.
- The verified local artifact set contains five client ZIPs and seven manifest assets in
  total: the wheel, source archive and those ZIPs. Release verification checks
  their checksums, package identity and canonical resources. The four-ZIP count
  above belongs to the earlier checkpoint.
- At the Hermes checkpoint, all 124 runtime/resource files matched across source,
  wheel and the installed package. The local inference installation retained all
  79 dependency pins. The earlier 123-file checks remain historical evidence.
- Final verification in Hermes' actual native default home resolved all seven
  canonical skills and discovered exactly `guide`, `read`, `write` and `finish`
  through the shared service. Initial connection and native reload were checked
  again against the existing owner without restarting the service.
- Model-driven retrieval and update ran separately in disposable storage. The
  resulting read, saved body, metadata, reciprocal links and cleanup were
  independently checked. The [Hermes acceptance report](hermes-integration.md)
  records the calls, successful results and observed schema/routing mistakes.

These are local Linux results. Clean-wheel, transport and model checks establish
their respective tested paths; they do not establish native Windows/macOS
behavior, general model compliance, approval-required-policy behavior or
recovery during an in-flight model call. The Hermes web build required the
supported bounded-build retry described in the [setup guide](../integrations/hermes.md);
successful recovery does not establish the original Node crash's cause.

## Release preparation and final verification

The documentation/base-context regression run passed 30 tests. The managed guide
bundle expanded from seven to eleven records; upgrade verification retained the
seven existing record IDs while adding the four new topics and their navigation
links. Product guidance describes current behavior and scenarios separately from
bounded run reports and operation history.

A clean archive of commit `c81687e22cd80a44a8d84f8e9ea6650fddf52e32` passed
wheel/source build, five-client bundle generation and seven-asset verification.
An isolated Python 3.12 installation with hash-checked locked dependencies passed
the installed MCP/module smoke checks. All 128 runtime/resource files matched
between that commit's source, wheel and clean installation. These local artifact
results precede the subsequent platform fixes and do not claim that later source
changes were already packaged.

Cross-platform validation exposed CRLF-sensitive temporary filenames and source
declarations, and native Windows absolute-path matching in dependency checks.
The corrections retain authored body bytes, source conditions and comments while
matching dependencies against the actual inventory. Regression fixtures now write
their intended UTF-8/newline bytes explicitly. Context-name tests count actual
directory entries on case-insensitive filesystems; the uniqueness guard remains
unchanged. These changes do not require a separate Windows product version.

Module-child cleanup also preserves the original operation failure when the OS
denies process-group termination. Cleanup still attempts to reap the direct child; a bounded
error log explicitly marks descendant termination as unverified. A successful
operation does not become successful overall if cleanup fails. This reports the
failure without a speculative signal retry after reaping and possible PID reuse.

Final cross-platform acceptance uses the executed results for the release commit in
[GitHub Actions](https://github.com/pikiby/contextopus-core/actions/workflows/ci.yml)
for final CI evidence. Earlier checkpoint counts and local package checks are
separate from those results and from release publication; native service/client
and model-behavior limits remain as recorded above.

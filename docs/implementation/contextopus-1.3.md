# Contextopus 1.3 implementation and delivery evidence

> Historical document: release/verification conditions below apply to the named
> version or dated check. The independent repository layout is unreleased; see
> [current development instructions](../development.md).

This document records implementation and delivery history. The [accepted plan](../plans/contextopus-1.3.md) and [implementation contracts](../plans/contextopus-1.3-contracts.md) define acceptance. The historical 1.3.1 delivery section retains its platform and client-behavior results; the 1.3.2 section records bounded synthetic native-model acceptance. The final 1.3.3 section records the current released/installed runtime and registered-data audit. Earlier run counts and temporary-artifact evidence below retain their original scope; they do not certify later rebuilt bytes.

## Earlier candidate and cross-platform corrections

The first authorized platform CI found that macOS SQLite omits the optional
`enable_load_extension` API. The correction checks for that API before disabling
extension loading; SQL authorization remains enforced, with both API variants
covered by regression tests. The `a38…` installation, model and data-copy receipts
below describe the preceding package and do not certify rebuilt bytes. The
corrected artifact had a separate identity receipt and, at that stage, still
required its own successful platform CI and live-installation acceptance.

That CI also exposed Windows test fixtures using the platform default encoding
and newline conversion. The correction supplies UTF-8 and preserves fixture bytes,
with explicit body/revision assertions; production link and migration code did
not change. Both Windows jobs passed the native empty/seeded-file lock tests,
but their full suites were cancelled after four fixture failures while still
making progress. They are incomplete runs, not Windows suite passes.

The next full matrix passed Linux and macOS, but both Windows jobs completed
with two remaining fixture failures. The migration fixture now records exact
UTF-8 rule bytes for both LF and CRLF; the snapshot fixture explicitly closes
its SQLite destination before deleting WAL sidecars. Both targeted files passed
their local checks. These corrections change tests only; the next complete
platform CI remained the acceptance gate at that stage.

The third matrix again passed five jobs; both Windows full suites finished with
731 passed, 30 skipped and one WinError 5 failure in the snapshot fixture's
Git-object deletion. The original log did not record that file's attributes.
The fixture now diagnoses permissions and permits cleanup only for an actually
read-only object in an owned Git store; other permission failures propagate. Its coherent full restore,
pending-work continuation and indexed-search assertions remain in place.

A separate audit confirmed production readers that decoded persisted UTF-8 with
the OS default: base-context records/state, settings configuration and receipts,
native link aliases, and public module/algorithm metadata. These paths now read
UTF-8 explicitly; byte-sensitive revision/Git comparisons preserve LF/CRLF, and
Python algorithm sources retain their declared source-encoding semantics. This
was a production dataflow gap, not solely a fixture issue. Linux checks forcing
the implicit default to CP1252 reproduced failures before the corrections.

The optional SQLite API guard, explicit production UTF-8 readers and later
nested-vault boundary correction are product fixes. SQLite fixture connection
closure, restricted read-only Git-object cleanup and byte-preserving test
expectations repair the test scaffold without weakening production checks.

The earlier focused set collected 35 cases: 33 passed on Linux and two native
Windows lock cases were skipped. Ten additional dataflow cases failed before
and passed after their fixes. That candidate's Windows-only early gate collected
45 cases and preceded the unchanged full suite/build/installed checks in both
existing Windows jobs. Collection is not execution; these local results are
not a native Windows pass or an aggregate 45-case pass. The corrected wheel has
separate installed UTF-8/MCP evidence; historical model/copy receipts retain
their original attribution rather than certifying new runtime bytes.

## Version domains

| Domain | Target |
| --- | --- |
| Python package and client manifests | 1.3.3 released and installed |
| Workspace storage format | 4 |
| Builtin search algorithms | 2.0.0 |
| Shared selection/evidence contracts | 2 |

The configured algorithm and inherited parameter defaults are preserved. Provider algorithms retain their own versions; the shared unit contract is independently recorded.

## Verified implementation

Search regression fixtures cover repeated fragments from one document, limits and pagination in material/fragment units for every builtin, inter-document jumps evaluated before N, technical candidate caps, invalid distances, bounded historical snapshots and honest replay labels. MCP tests cover exactly three default tools, explicit old-tool compatibility, actual HTTP dispatch, full/compact separation, exact review preservation, custom metadata, faults and candidate journaling before presentation. Settings/records/migration evidence is maintained by the corresponding test suites; read-only observation cannot silently reload rules to assess a single policy.

Executed bounded search/MCP/native/Core run: **113 passed, 1 skipped, 9 subtests**. Final registration/native subset after durable settings-preview semantics: **50 passed, 1 skipped, 9 subtests**. Six packaged skills passed the skill validator. These counts identify bounded runs, not the complete project suite.

The complete 57-file test inventory subsequently ran as three disjoint groups:
124 passed; 208 passed with 5 skipped and 2 subtests; 325 passed with 1 skipped
and 62 subtests. Aggregate: **657 passed, 6 skipped, 64 subtests, zero failures**.
The optional real-host/model checks are not implied by skipped tests. This was a
Linux run, not the declared cross-platform CI matrix.

A later bounded procedure/schema correction used one `ProposalChange` contract
for both the runtime allowed-field check and the generated nested operation
schema. It documents that the title comes from content, routes verify-and-save
requests through Work initially, and uses `workspace.status` for cycle state.
Its affected tests were rerun: **45 passed** in `test_mcp_v13.py`/`test_cycles.py`
and **30 passed plus 2 subtests** in `test_mcp_router.py`/`test_contracts.py`.
These repeat checks are not additional unique project-test counts.

A subsequent real metadata repair exposed an unchanged oversized legacy body
being rejected by the body-size limit. The narrow correction skips that limit
only when the parsed body is identical. Nine targeted tests passed: description,
status, links, path and identical-body edits preserve text and embedding calls;
new/actually changed oversized bodies still require splitting. An additional
combined run reached its 180-second timeout without a final summary; it is not
reported as a pass. The preceding full-suite totals predate this narrow change.

## Newly authorized module installation extension

The user added module-owned schemas/migrations and one-skill installation to 1.3.
The source extension is implemented; the earlier full-suite totals do not
establish it. Core storage, module lifecycle/child protocol, and the shared
MCP/CLI/TUI/skill path had separate implementation owners. A bounded integrated
run passed 165 tests across MCP, module installation, lifecycle, storage,
interfaces, native skills and release readiness. Real SQLite tests cover
namespace isolation, migration transactions/checksums, retry, schema compatibility,
preserved data and WAL-aware relocation backup. The folder example performs linked
record writes and JOIN/COUNT queries through the Core parent process, including
restart/reinstall. An isolated module venv has no Core installation of its own.

Independent review reproduced and owners corrected two defects: named parameter
maps were converted to keys by the child client, and a post-COMMIT deadline check
could falsely report failure after saving. Both regression cases passed. Native
entrypoints receive the common storage service before registration. Actual HTTP
roundtrips also exposed FastMCP expanding list results into multiple text blocks;
the transport now retains a single JSON value for arrays and scalars, preserving
empty lists, multiple results, false, zero, null and existing dictionaries.
Windows child cleanup uses Job Objects and had not run on this Linux host at
that stage; its platform CI result was still required. See the accepted plan's module section.

The complete 59-file inventory was subsequently covered by three disjoint runs
and a targeted retry of one migration case that failed with `database or disk
is full`. The retry passed with at least 6.92 GB free. After the Windows
lock correction, that inventory contained 759 unique tests: **751 passed,
8 skipped, no unresolved failures**, with 64 passing subtests counted separately.
These are combined latest outcomes, not one uninterrupted run. The eight skips
include two native Windows locking cases; Linux results do not establish Windows
or macOS acceptance. The other skips are five opt-in Codex/model scenarios and
one virtualenv user-site case. The file and unique-case inventory is retained in private local evidence;
line/branch coverage was not measured.

The Windows correction removes the unsynchronized seed write before byte-zero
lock acquisition. CRT permits locking beyond EOF, so an empty lock file needs no
initial write. Cursor restoration, blocking/nonblocking modes and error
propagation are retained. Focused portability, relocation, journal, history and
module-lock tests passed (33 tests, two native Windows skips). The former CI
failure occurred at that removed write; its exact process scheduling was not
recorded. New native tests cover mutual exclusion and reacquisition for empty
and legacy-seeded files.

The isolated Codex 0.163.0 recovery script verified two existing test threads after failed initialization/reload and server restart; nonempty history survived and automatic renewal succeeded. It performed no model turn and did not access active user conversations. One first handshake failure did not recur in the next two isolated runs; no speculative protocol change was applied.

Inside the execution sandbox, local LanceDB.connect stalled before table creation. The same minimal connect outside sandbox completed in 0.77 seconds. Integration tests therefore ran outside sandbox against temporary roots; this is an environment boundary, not evidence that production indexing failed.

## Packaging checks

Run against the preceding coordinated candidate source tree:

```console
uv lock --check --offline
uv build --offline --no-sources
.venv/bin/python scripts/build_release.py
.venv/bin/python scripts/verify_release.py
```

The verifier checks the exact six assets and SHA-256 digests, package/version/license/CLI metadata, every canonical application resource, skill inventories and plugin version. Client bundles reference the matching wheel and current tools. Canonical plugin short-skill copies are compared byte-for-byte with packaged skills. The sdist includes release tooling, lock metadata, canonical plugin resources and fixtures required by the newly shipped release tests; verification compares their actual bytes as well. Previous released 1.1/1.2 skill bytes are retained as recognized hashes; arbitrary edits are not recognized as managed originals.

Offline build and release verification checked all six assets and their canonical
resources. A temporary venv contains the wheel and runtime dependencies. Its isolated interpreter (`-I`)
resolves Application inside that venv, not the editable checkout. The CLI reports
Contextopus 1.3.0; installed inspection finds guide/read/write, seven short skills,
five version-2.0.0 algorithms and base-context 1.3.0 without loading a model. These
local artifacts do not identify a published revision until publication records
that association.

The rebuilt candidate wheel has SHA-256
`a38cc808978b8f04c377dd30b934ac13cced119d979674d2562656879645e5c6`.
Its isolated installed interpreter passed actual MCP installation of catalog-demo,
linked inserts, reads and owner restart. The module's own venv contains no Core
package. All 119 application files, including 32 resources and seven skills,
match source and wheel; 125 installed wheel members match exactly. The verifier
also passed from an extracted sdist. This is temporary-installation evidence;
it predates the retrospective documentation delivered separately below.
The corresponding candidate receipt is retained privately.

## Bounded payload comparison

The coordinator measured raw versus compact presentation of the same backend operation result, with identical UTF-8 JSON serialization (ensure_ascii=False and compact separators), on one temporary fixture containing three knowledge and two project records across two contexts. The fixture used deterministic offline embedding vectors.

| Operation | Raw bytes | Compact bytes | Reduction |
| --- | ---: | ---: | ---: |
| Material read | 1131 | 958 | 15.3% |
| Material search | 5300 | 2171 | 59.0% |

The local payload-size receipt is retained privately. This measures those two serialized result objects. It does not establish total conversation tokens, end-to-end latency, model compliance or answer quality.

## Isolated migration and Obsidian application evidence

CI additionally declares a dedicated Linux/Python-3.12 transition job. It checks out the verified peeled v1.1.0 commit `ff711966921c562f22aa7bcdb9358a871c8d4282`, installs it noneditable in a separate venv, supplies CONTEXTOPUS_V11_PYTHON, then runs the current migration test without model downloads. At that stage this declaration was not a completed GitHub job; the final CI section records its later successful execution.

Both real old writers were installed noneditable and executed with `-I`, outside
the new editable source tree. The final suite passed **1.1 → 1.3 and 1.2 → 1.3**
through the current runtime and MCP on isolated fixture copies. Tests check
stable IDs, text, custom metadata, sources, settings, graph endpoints, Git,
SQLite and immutable pending proposals, including their later authorized apply
and repeated upgrade. The 1.2 case also preserves configured search algorithms,
inherited parameter values and existing algorithm-catalog rows, reporting their
staleness until explicit refresh. Separate regression cases cover interruptions,
policy conflicts and restoration of the coherent snapshot. None of these tests
migrated the user's actual root.

### Copy of the actual selected context

A coherent private snapshot of the existing root was retained. Its 30,099 files
remained immutable.
The root guard covered the 10.727-second capture; source content and service state
were unchanged. Active SQLite main/sidecar bundles were copied, checked for
stability and backed up from isolated staging. Integrity checks and table counts
matched. This does not establish one global event timestamp across databases.

The exact `a38…` candidate wheel above migrated a separate copy of the selected context from
format 3 to 4, then repeated the operation successfully. All 77 records retained
bodies, paths, types, statuses, descriptions, revisions, graph endpoints and
source fields; 377 native YAML links resolved. Free rules and effective policies
were preserved while machine settings moved out of instructions. All 810 shared
index rows were unchanged, including text, vectors and metadata: 122 belonged to
the selected context and 688 to other contexts. No document embedding was called.

The open cycle, 20 tmp/review/proposal files and four already-applied proposal
revisions were retained. Those proposals were only read and compared; no pending
proposal was applied in this copy test. Prepared-proposal application/recovery
has separate old-writer fixture coverage. Existing Git files elsewhere in the
root were unchanged; the selected context has Git disabled. The other 26 contexts
were not migrated: their 328 cards and format markers remained unchanged.

The copy used an explicit offline provider for one query-access check, so it
does not establish real semantic ranking quality. Its records declared no formal
sources; required-source behavior has separate fixture and model evidence. The
transport check used actual in-process MCP handlers, not a deployed native client.
The corresponding private summary retains its exact artifact association.

On Linux, the coordinator exercised the installed Obsidian Flatpak **1.12.7** in an isolated temporary profile/vault. Runtime-created YAML wikilinks to two equally named records in different contexts resolved as two distinct edges in metadataCache/frontmatterLinks/resolvedLinks. Both links rendered in the DOM; clicking the beta link opened its exact file. The application-fixture receipt is retained privately. Existing user vaults/configuration were untouched. This verifies that application/path fixture, not every OS or all migration variants.

The final packaging/legacy-skill/stdio/tmp subset passed **28 tests and 2 subtests** in 19.76 seconds. Actual tagged 1.1/1.2 skill bytes were tested with LF and CRLF, without an earlier managed manifest; arbitrary user edits remained protected. The renamed 1.1 w-find becomes w-context only when recognized as unchanged. The latest release guards passed 27 tests; after adding the malformed-revision guard, three targeted tmp regressions passed in 3.23 seconds.

The earlier archived-HEAD baseline's two launcher subfailures were interpreter contamination: the copied compatibility shim intentionally ignored PYTHONPATH and imported the shared editable standalone package, whose live registry already had 47 operations. Its fixture still expected 44. The source archive alone did not isolate that child interpreter. Final launcher tests now compare the actual operation inventory and exercise the current explicit machine settings/descriptions over real stdio; both implicit/explicit Python-selection subcases passed. This does not establish a historical runtime defect.

## Tmp conflict boundary

Temporary writes compare the exact current text revision before replacement. Malformed revision, missing material and well-formed stale revision have separate messages directing the caller to tmp_list or tmp_read with the same cycle/ID. Regression tests must show that failed updates retain the current bytes and that a fresh read permits an authorized retry. This preserves concurrent-update protection. The coordinator subsequently verified the historical event sequence: the issued revision had 64 characters; the failed update submitted 65 after inserting one zero; tmp_read returned the original 64-character revision and retry with it succeeded. The cause was corrupted expected_revision input, not established concurrent editing or deletion. Public evidence omits personal cycle/material identifiers. The new format guard rejects malformed revisions before CAS, tells the caller to copy tmp_read's exact 64 lowercase hexadecimal characters, and never repairs or accepts a guessed revision.

## Bounded model behavior

Six real GPT-6.1 Sol turns used temporary data and an isolated MCP endpoint.
Initial scenarios demonstrated independent retrieval without a cycle, reuse with
rereading disabled, explicit rereading enabled, and fresh source acquisition on
each received declaration. Native host approval blocked two attempted writes;
those attempts did not establish a saved result. With the correctly configured
per-tool approval and a wrapper limited to the test coordinates and five ordinary
write operations, a complete review/apply/finish cycle succeeded.

That earlier successful cycle also revealed late startup, a shell read of internal
cycle state and an unsupported title field. After the narrow procedure/schema
correction, one fresh natural-language verify-and-save scenario completed in
52.85 seconds. Startup preceded search/read; the declared external JSON was read
freshly twice; compact output was assessed explicitly; the first proposal was
valid; text, description and link effects were shown before apply; the new record
was indexed and the cycle closed. Internal Workspace files were not read directly.

This last turn used the installed older short `$w` dispatcher before retrieving
the new procedure through `guide`. It validates the new procedure/runtime path,
not exclusive model use of the newly packaged skill. Packaged skill identity has
separate byte-level verification. Native authentication copies were temporary and
removed, and original credentials and user contexts were unchanged. The observed
passes and deviations are bounded evidence, not a claim that every model follows
the procedure or that total token consumption decreased.

Private model-review outcomes and corresponding raw JSONL traces retain call
and review ordering.

One additional native Codex GPT-6.1 Sol turn used the `a38…` candidate wheel and its
packaged `$m` skill, with a temporary root and a wrapper allowing only installation
of the supplied catalog-demo. The model read the skill and modules procedure,
inspected pending storage, installed through MCP, and checked the enabled module
and its query. The turn passed in 22.652 seconds without a retry. A separate
installed-runtime observer confirmed the schema, ledger, SQLite integrity and
query after restart. No direct installer or SQL command was used by the model.
The example declared no dependencies and the queried table was empty; dependency
preparation and inserted-data behavior have separate contract/API evidence. This
is one observed install turn, not general model compliance. Temporary credentials
were removed and the source credentials remained unchanged. The corresponding model-install receipt is retained privately.

## Earlier project memory reconciliation

Before live delivery, thirteen thematic records were corrected against the implemented source contract
and explicitly distinguish candidate 1.3 from the installed 1.1 runtime. The
published-version installation instructions retain their 1.2 commands and now
label that scope. One historical task remains unchanged because current source
does not establish completion of that separate assignment. The goal, plan and
migration state were also updated. All 16 changed records were read back through
the existing MCP with matching bodies, descriptions, revisions and links; all
were indexed. Git history is disabled in that selected context. No future live
installation was recorded as completed. In the earlier selected-context inventory,
69 missing descriptions had been reviewed and applied; 75 of that original
76-record inventory had descriptions. One unchanged oversized historical record
still needed a metadata-only description through the corrected runtime. These
counts describe that earlier inventory, not the final delivered memory state.

## Final delivery: released and installed 1.3.1

The authorized rollout first installed the published 1.3.0 release without an
intermediate 1.2 installation. Its full platform matrix passed. Before any live
format conversion, upgrade planning exposed a separate nested-vault defect:
both the selected root and an ancestor contained `.obsidian`. Patch 1.3.1 makes
an explicitly selected root with its own `.obsidian` the vault boundary. Without
that marker, multiple enclosing vaults still require an unambiguous root.
Neither vault was removed or renamed.

The installed patch has source commit
[`4107050440054c9eaa43f58a54c920fdfac1d3d8`](https://github.com/pikiby/contextopus-core/commit/4107050440054c9eaa43f58a54c920fdfac1d3d8)
and wheel SHA-256
`39a0aa09ccc256f50001bcfd907367eb767fe0b2db9a17f3069d3f919313bce9`.
All 119 installed application files matched that wheel. The existing `local`
extra, CPU PyTorch, persistent root and one native service owner were retained.
The patch's [platform workflow](https://github.com/pikiby/contextopus-core/actions/runs/39002613425)
completed successfully for that exact source: **7/7 jobs passed**. This includes
Linux/macOS/Windows on Python 3.12/3.13 and the separate real 1.1-writer transition
job. The two Windows jobs completed their native early gate, unchanged full suite,
build, release verification, exact-wheel installation and installed MCP checks:

| Native Windows job | Early gate | Full suite |
| --- | --- | --- |
| Python 3.12 | 48 passed in 177.52 s | 754 passed, 30 skipped, 53 subtests in 1307.71 s |
| Python 3.13 | 48 passed in 167.72 s | 754 passed, 30 skipped, 53 subtests in 1359.96 s |

Early cases also occur in the full suite; these counts must not be added as
unique tests. Skips and subtests are reported separately. This is native Windows
execution, not a simulated CP1252-only or Linux collection result.

[Release v1.3.1](https://github.com/pikiby/contextopus-core/releases/tag/v1.3.1)
was published as the latest stable release from that exact commit. All seven
assets, including SHA256SUMS, were downloaded and matched the approved bytes and
GitHub API digests. The installed wheel matches the published wheel above.
Retrospective documentation changes are separate from this runtime commit and
do not rebuild, retag or replace the immutable release artifacts.

### Coherent backup and live preservation

Two fresh private whole-set snapshots were verified: the old 1.1 installation
before 1.3.0, and the changed 1.3.0 state before the patch. They retain the package
prefix/extras, data, configuration, native integrations and service controls as
a coherent recovery set. Source fingerprints and every regular/symlink archive
member were checked, together with 76 logical SQLite backups in each snapshot.
Private snapshot locations and recovery receipts are retained outside public
documentation. An old runtime must not be started against incompatible migrated
data; rollback restores the coherent set.

The actual selected context then migrated from Workspace format 3 to 4 through
the new service's public MCP. Apply completed and a fresh repeat plan was
compatible with no further changes. Read-only comparison with the migration
backup established:

- All 77 cards retained IDs, paths, types, statuses, descriptions, bodies, sources
  and other metadata. All 377 ordered graph edges retained their target YAML IDs
  and became resolving native vault-relative wikilinks.
- The complete free-text instructions and unrelated frontmatter were unchanged;
  only recognized machine settings moved into canonical Core configuration.
  Effective permissions and settings matched the reviewed transition.
- All 47 temporary/review/proposal files remained byte-identical, with two active
  cycles, 29 temporary materials and nine proposals preserved. Cycle/request/ID
  controls were unchanged apart from the expected format marker.
- Before base-document delivery, all 27 other contexts were unchanged: 4,911
  workspace files and 9,559 control files matched the pre-patch snapshot. All 83
  captured `active.json` pointer files were unchanged. These are file counts,
  not a claim of 83 distinct active models.

This establishes bounded file/graph preservation, not semantic ranking quality
or GUI navigation on every platform. The earlier isolated Obsidian application
fixture retains its separate scope.

### Product documentation, catalog and model cache

Explicit public `core.base_plan` / `core.base_install` delivery installed eight
managed base records at version 1.3.1 and indexed 12 fragments. Exact content and
description readback matched the reviewed module guide and template; the repeat
plan was current with no changes or conflicts. `core.algorithms_refresh`
refreshed the five builtin catalog entries at version 2.0.0. Bounded semantic
retrieval returned base documentation and the algorithm catalog through the
configured CPU provider. Active project rules and settings were preserved.
Package replacement and workspace migration alone do not perform these steps.

The active Qwen3-Embedding-0.6B configuration, including its pinned revision,
matched the pre-patch snapshot byte-for-byte. The first live model use populated
the selected Hugging Face cache, including a 1.19 GB weights file; download and
reconstruction completed before inference continued. No model/profile change
was required. The available evidence does not establish why an earlier complete
cache was unavailable, and does not attribute its absence to the update.

### Native clients and remaining acceptance

Codex and Claude retained seven managed short skills each; OpenCode and Crush
used config-only integration rather than duplicate skill copies. All four patch
previews were no-ops, and controlled configurations, manifests and skill hashes
matched their reviewed state. Configuration preservation is separate from a
fresh native MCP request and from the model following the whole procedure.

The first OpenCode and Crush runners sent literal `$w` as ordinary text. Those
turns were incorrectly described as native skill activation checks. Their
observed actions remain evidence of literal-text routing only; in particular,
the first Crush result did not establish failure of its native activation path.
Claude's runner did use native `/w`. Correctly activated OpenCode and Crush
checks subsequently established the following separate results:

| Client | Current bounded result |
| --- | --- |
| Codex | `$w` passed: actual guide, rules, project, search and full read. |
| Claude Code | Native `/w` retrieval passed; guide was repeated. `project_read` is conditional on need, so its absence alone does not establish a procedure violation. |
| OpenCode | Native `opencode run --command w` performed guide/settings/search and full reads, with zero argument errors and default compact responses. It skipped the initial full INSTRUCTIONS and supplied `N=15` rather than inheriting the selected search settings. Technical retrieval worked, but those procedure requirements were not met. Project reading remains conditional. |
| Crush 0.87 | Native ReadSkill supplied the exact released skill through a text/markdown attachment to AgentMessage. Bytes were verified in the native user-message attachment; prompt inclusion was established from the client implementation, not an outbound provider-request capture. MCP was connected and its tools advertised, but the model used grep/glob/view and made zero MCP calls. This validly activated behavior check failed. |

The separate earlier Crush capability turn allowed only the two read-only MCP
tools and disabled non-MCP builtins. It passed schema/search/read after argument
errors and recovery, proving technical retrieval under that constraint rather
than ordinary skill behavior. The valid native activation above is a separate
failure; a connected endpoint or verified skill attachment does not prove that
the model will use it. The evidence does not establish the cause of that choice.

One bounded temporary A/B turn added explicit Contextopus MCP guidance to a
candidate skill and used the same native activation path. It also made zero
MCP calls. This candidate was not accepted or installed; the released skill and
product runtime remain unchanged. Harness/method corrections and this temporary
experiment do not establish a shipped product fix or universal model compliance.

All four clients demonstrated technical native retrieval under the stated
conditions. OpenCode's missing INSTRUCTIONS and search-setting override, and
Crush's correctly activated behavior failure, remain separate acceptance
limitations of that package. The follow-up 1.3.2 runtime clarifies initial-rule
and native MCP routing instructions; its later controlled-corpus results are
recorded separately below and do not relabel these earlier observations. Project-memory
reconciliation must retain these limits. Native Windows CI does not establish
Windows/macOS GUI behavior, GPU inference, or complete model scenarios on every
host. Historical model/copy receipts above remain attributed to their original
packages.

[Upgrade and restore instructions](../releases/1.3.0.md) describe the operational
sequence. Private host paths, backup locations and client-session identifiers
are intentionally absent from this delivery summary.

## Follow-up 1.3.2: routing and legacy identities

The [1.3.2 release notes](../releases/1.3.2.md) separate first complete rule
reading from conditional project reading and make native MCP routing explicit.
The initial search inherits the selected algorithm and limits unless the user
provided alternatives. Protocol tests can establish delivery of these
instructions, not model compliance. The native 1.3.1 observations above retain
their own scope. Exact artifacts and final native checks have their own source
binding below; local installation remains a separate delivery step.

An earlier synthetic OpenCode model turn on 1.3.2 source `2add7fa` made five
successful main provider requests and retrieved the fixture record, but skipped
the ordinary procedure, policy settings and full INSTRUCTIONS, using N=10
instead of the configured N=2. This observation motivated the `8b00620`
help/schema-description reminder. The early synthetic Crush attempt on
`2add7fa` never reached the provider because of the harness transport and has no
model-behavior verdict. These are separate from the earlier 1.3.1 observations.

The candidate also adds reviewed context/path mappings for colliding legacy
format-0/1 filename identities. Format-2-and-later canonical YAML IDs remain
authoritative. Original pending proposal/review bytes and approval revisions
are preserved; technical overlays adapt identities and paths. Foreign contexts
are not migrated implicitly, and ambiguous references block.

Independent review reproduced a graph-preservation defect: an exact foreign
native link resolved to its canonical ID, but a second local-alias lookup could
redirect it when that ID matched a local legacy filename. The correction uses
the decoded canonical target directly. Pending `link_ids` must match the
reviewed graph; explicit foreign `link_targets` keep their owner, ID and path.
Changed or ambiguous reviewed targets block before migration. The same isolated
reproducer passed after correction, preserving the foreign path and ID.

The targeted migration run passed **17 new cases plus five historical cases**
in 75.30 s, covering local/foreign identities, unchanged approvals, interruption
and retry, retained-map conflicts and root relocation. Those counts identify
one bounded source run and must not be added to full-suite totals as unique
tests. Normal record lookup reads the local retained-map receipt rather than
running the migration-wide catalog scan; no lookup timing benchmark was run.

The combined candidate's complete Linux suite finished with **792 passed, two
failed, 10 skipped and 62 passed subtests** in 930.44 s. Both failures concerned
version consistency: the hidden native-plugin manifest and installed metadata
in the test interpreter still reported 1.3.1 against project version 1.3.2.
The full run's 257 inspected source/test file fingerprints remained unchanged.
After the hidden manifest was aligned and only the repository's editable project
metadata rebuilt as 1.3.2, the complete contract and release-readiness files
passed: **40 passed and two passed subtests** in 19.35 s. Non-project dependencies
and the host installation were unchanged. This focused run closes those two
version failures without rerunning or relabeling the earlier full suite.
That earlier full run remains recorded with its two version failures. Later
[cross-platform CI](https://github.com/pikiby/contextopus-core/actions/runs/39037424175)
passed all seven jobs at runtime commit
`2add7faab18da4333ab7d8ab314142d27cc6ab57`: each Windows full-suite job passed
777 tests with 30 skips, each macOS job passed 796 with 11 skips, and each Linux
job passed 797 with 10 skips. The Windows early gates and all six build,
release-verification, exact-wheel installation and installed MCP checks passed;
the seventh job exercised the real 1.1 writer transition.

The intermediate `8b00620b9a8a1c07672bda0eebbb0e9110d59d27` wheel, SHA-256
`d4e83f2bdacc3e95c813131beb443808e1ed9dfedb5815efaee8bc461231b7f0`,
passed 28 MCP tests for its metadata-only help/schema-description change and
two Core/release checks. Independent review found all 47
operation argument schemas unchanged except the search N description, with
unchanged validation and dispatch. Its exact installed wheel passed MCP,
module-storage write/read/restart and guide-metadata checks; all 120 application
members matched the wheel. The full OS matrix belongs to `2add7fa`, not this
later SHA. A separate real installed 1.2 writer transition against that
intermediate wheel passed one test in 25.81 s, preserving two temporary contexts,
pending approval bytes and search settings without model calls.

The final runtime source is `f0578ce1734af2b516cbfe8175b8f991d9fd8acf`,
wheel SHA-256
`f8d47a8ea562532138c04b869cc1b8e8f008993e0cb683eae6183c7b2b076b1a`.
Its only later product delta makes the independent retrieval sequence explicit:
policy settings, complete INSTRUCTIONS, then search with inherited settings.
Three targeted procedure/MCP/release checks passed. The exact installed wheel
passed guide/procedure and module-storage write/read/restart smoke checks, with
all 120 application members matching. This delivery-text delta did not change
storage, dispatch or validation. Its focused acceptance does not reattribute the
`2add7fa` platform matrix or the `8b00620` real-1.2 transition to a later SHA.

Two independently reviewed native model turns used this final wheel with a
controlled synthetic corpus. OpenCode 1.18.32 with DeepSeek Flash and Crush 0.87
with DeepSeek Pro both obtained policy settings, read the complete rules,
inherited N=2, fully read the requested fact and grounded the answer in the
returned evidence. OpenCode also fully read the related plan. Neither bypassed
MCP through files nor wrote context data. Crush
recovered from one guessed-ID argument error by obtaining the read signature and
retrying with `material_id`. OpenCode made nine successful MCP calls and nine
HTTP-200 provider requests in 25.154 s; Crush made seven MCP attempts, six
successful, and ten HTTP-200 provider requests in 34.010 s. Provider-reported
input/output totals including title generation were 70,905/1,830 and
109,815/2,133 tokens respectively. These are observed per-turn totals, not a
paired causal token-economy comparison.

These checks establish the bounded fresh-task path on controlled retrieval,
not production ranking, every model/client combination or enforced compliance.
Earlier partial/failing traces retain their original package and fixture scope.
Observed proof is still missing for delegation, context switches, lost rule
text and plugin refresh. GUI/GPU behavior and model scenarios on every OS remain
outside the native platform CI claim. At that pre-1.3.2 checkpoint, live was
1.3.1; later installation and final data-preservation checks are recorded below. Final documentation changes affect only the sdist: accepted wheel/client
ZIP bytes retain their runtime-source attribution and are not rebuilt as though
a documentation-only commit had rerun the platform or model checks.

## Final delivery: 1.3.3

[Release 1.3.3](https://github.com/pikiby/contextopus-core/releases/tag/v1.3.3)
was published and installed from immutable source/tag commit
`9873157dde6f5f6c4c3fbda263c6b7e0bef12114`, wheel SHA-256
`81c7aba6560129658d5f6201154bdffb6816730ae7c557afc6efe6ff812879c9`.
All seven published assets matched fresh downloads and GitHub digests. The
installed 120 application members matched the wheel; the existing root, local
CPU extras and 79 non-project dependency versions were retained. Coherent private
whole-set backups were verified before cutovers using archive content, modes,
links and logical SQLite integrity checks. No full extraction/restore drill is
claimed. No private backup paths or context identities are published here.

The narrow guard handles legacy pending work with no earlier INSTRUCTIONS body;
it does not invent prior rules approval. The affected source set passed 30 tests,
including two new cases; version/release checks passed 40 tests and two subtests,
and the MCP-contract file passed 28 tests. Both changed-path cases then passed
against the isolated installed wheel with all 52 loaded runtime modules outside
the checkout. Compared with the accepted 1.3.2 wheel, only the migration guard
and two packaged base-version fields changed among application members. All
seven skills and the Workspace procedure were byte-identical. The complete OS
matrix remains attributed to `2add7fa`; controlled-corpus native model results
remain attributed to 1.3.2 `f0578ce`. No new model turn or full matrix is claimed
for 1.3.3.

One existing service owner serves the retained root. Fresh public MCP returned
the expected procedure and packaged version. The reviewed managed-base update
changed only its installed-version document; a full read and empty replan verified
version 1.3.3, followed by algorithm-catalog refresh and semantic retrieval.
Custom rules, settings and the selected base role were preserved. Existing
Codex/Claude user integrations retained 14 managed files matching the seven
shipped skills. Existing OpenCode/Crush HTTP integrations were retained; all four
previews were no-ops. These checks do not claim automatic reload of every open
session or replacement of its configured model.

Full public-MCP pagination audited 29 registered Workspace contexts: all use format 4,
all 425 records have descriptions, and all 425 are represented in the index,
with no unregistered/unindexed records or structural issues. Established
canonical identities, source bodies and graph semantics were preserved under
the migration contract; legacy filename collisions used explicit scoped maps.
User text and effective policies were retained, while previously uninitialized
legacy rules were supplied through the reviewed initialization path. Existing
pending work was preserved except for two separately authorized cancellations.
Record-description coverage is separate from project-purpose completeness:
five PROJECT documents remain absent and six remain placeholders. This structural
audit is not a semantic truth check of every historical statement or a fresh
verification of every external source. Fragment totals are not used as stable
record counts.

This later documentation-only status update does not rebuild or relabel the
immutable 1.3.3 tag, wheel or other release assets. Earlier package/test/model
receipts retain their original source and fixture scope.

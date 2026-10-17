# Contextopus 1.3 implementation and delivery evidence

This is source/build readiness evidence, not a publication or live-installation receipt. The [accepted plan](../plans/contextopus-1.3.md) and [implementation contracts](../plans/contextopus-1.3-contracts.md) define the remaining acceptance.

The first authorized platform CI found that macOS SQLite omits the optional
`enable_load_extension` API. The correction checks for that API before disabling
extension loading; SQL authorization remains enforced, with both API variants
covered by regression tests. The `a38…` installation, model and data-copy receipts
below describe the preceding package and do not certify rebuilt bytes. The
corrected artifact has a separate identity receipt and still requires its own
successful platform CI and live-installation acceptance.

That CI also exposed Windows test fixtures using the platform default encoding
and newline conversion. The correction supplies UTF-8 and preserves fixture bytes,
with explicit body/revision assertions; production link and migration code did
not change. Both Windows jobs passed the native empty/seeded-file lock tests,
but their full suites were cancelled after four fixture failures while still
making progress. They are incomplete runs, not Windows suite passes.

## Version domains

| Domain | Target |
| --- | --- |
| Python package and client manifests | 1.3.0 |
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
Windows child cleanup uses Job Objects but has not run on this Linux host; the
platform CI result is still required. See the accepted plan's module section.

The complete 59-file inventory was subsequently covered by three disjoint runs
and a targeted retry of one migration case that failed with `database or disk
is full`. The retry passed with at least 6.92 GB free. After the final Windows
lock correction, the current inventory contains 759 unique tests: **751 passed,
8 skipped, no unresolved failures**, with 64 passing subtests counted separately.
These are combined latest outcomes, not one uninterrupted run. The eight skips
include two native Windows locking cases; Linux results do not establish Windows
or macOS acceptance. The other skips are five opt-in Codex/model scenarios and
one virtualenv user-site case. The file and unique-case inventory is retained in
`/tmp/contextopus-v13-full-test-coverage-evidence.json`; line/branch coverage was
not measured.

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

Run against the final coordinated source tree:

```console
uv lock --check --offline
uv build --offline --no-sources
.venv/bin/python scripts/build_release.py
.venv/bin/python scripts/verify_release.py
```

The verifier checks the exact six assets and SHA-256 digests, package/version/license/CLI metadata, every canonical application resource, skill inventories and plugin version. Client bundles reference the matching wheel and current tools. Canonical plugin short-skill copies are compared byte-for-byte with packaged skills. The sdist includes release tooling, lock metadata, canonical plugin resources and fixtures required by the newly shipped release tests; verification compares their actual bytes as well. Previous released 1.1/1.2 skill bytes are retained as recognized hashes; arbitrary edits are not recognized as managed originals.

Offline build and release verification checked all six assets and their canonical
resources. The temporary venv at `/tmp/contextopus-v13-wheel-gkqCOi/venv`
contains the wheel and runtime dependencies. Its isolated interpreter (`-I`)
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
the final source archive must incorporate the completed acceptance documentation.
Evidence: `/tmp/contextopus-v13-final-candidate-evidence.json`.

## Bounded payload comparison

The coordinator measured raw versus compact presentation of the same backend operation result, with identical UTF-8 JSON serialization (ensure_ascii=False and compact separators), on one temporary fixture containing three knowledge and two project records across two contexts. The fixture used deterministic offline embedding vectors.

| Operation | Raw bytes | Compact bytes | Reduction |
| --- | ---: | ---: | ---: |
| Material read | 1131 | 958 | 15.3% |
| Material search | 5300 | 2171 | 59.0% |

Evidence: `/tmp/contextopus-v13-obsidian-oxrqg8tf/payload-sizes.json`. This measures those two serialized result objects. It does not establish total conversation tokens, end-to-end latency, model compliance or answer quality.

## Isolated migration and Obsidian application evidence

CI additionally declares a dedicated Linux/Python-3.12 transition job. It checks out the verified peeled v1.1.0 commit `ff711966921c562f22aa7bcdb9358a871c8d4282`, installs it noneditable in a separate venv, supplies CONTEXTOPUS_V11_PYTHON, then runs the current migration test without model downloads. This declaration is not a completed GitHub job.

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

A coherent snapshot of the existing root was retained under
`/tmp/contextopus-live-copy-et5ikjnq/baseline`. Its 30,099 files remained immutable.
The root guard covered the 10.727-second capture; source content and service state
were unchanged. Active SQLite main/sidecar bundles were copied, checked for
stability and backed up from isolated staging. Integrity checks and table counts
matched. This does not establish one global event timestamp across databases.

The exact final candidate wheel above migrated a separate copy of project-update from
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
Summary: `/tmp/contextopus-live-copy-et5ikjnq/final-artifact-copy-acceptance-summary.json`.

On Linux, the coordinator exercised the installed Obsidian Flatpak **1.12.7** in an isolated temporary profile/vault. Runtime-created YAML wikilinks to two equally named records in different contexts resolved as two distinct edges in metadataCache/frontmatterLinks/resolvedLinks. Both links rendered in the DOM; clicking the beta link opened its exact file. Evidence: `/tmp/contextopus-v13-obsidian-oxrqg8tf/obsidian-evidence.json`. Existing user vaults/configuration were untouched. This verifies that application/path fixture, not every OS or all migration variants.

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

Evidence: `/tmp/contextopus-model-acceptance-8xn0xd3x/reviewed-outcomes.json` and
`/tmp/contextopus-model-postfix-xiqdtem6/work-turn-postfix/reviewed-outcome.json`;
the corresponding raw JSONL traces retain call and review ordering.

One additional native Codex GPT-6.1 Sol turn used the exact final wheel and its
packaged `$m` skill, with a temporary root and a wrapper allowing only installation
of the supplied catalog-demo. The model read the skill and modules procedure,
inspected pending storage, installed through MCP, and checked the enabled module
and its query. The turn passed in 22.652 seconds without a retry. A separate
installed-runtime observer confirmed the schema, ledger, SQLite integrity and
query after restart. No direct installer or SQL command was used by the model.
The example declared no dependencies and the queried table was empty; dependency
preparation and inserted-data behavior have separate contract/API evidence. This
is one observed install turn, not general model compliance. Temporary credentials
were removed and the source credentials remained unchanged. Evidence:
`/tmp/contextopus-v13-m-skill-model-acceptance-summary.json`.

## Project memory reconciliation

Thirteen thematic records were corrected against the implemented source contract
and explicitly distinguish candidate 1.3 from the installed 1.1 runtime. The
published-version installation instructions retain their 1.2 commands and now
label that scope. One historical task remains unchanged because current source
does not establish completion of that separate assignment. The goal, plan and
migration state were also updated. All 16 changed records were read back through
the existing MCP with matching bodies, descriptions, revisions and links; all
were indexed. Git history is disabled in that selected context. No future live
installation was recorded as completed.

## Remaining acceptance

- Execute the declared platform CI jobs after publication work is authorized.
- Retain the exact final-source artifact identities, approved publication and installation receipts.
- Retain a fresh coherent whole-set backup before live migration; the accepted
  copy predates later context updates and is not a snapshot of their final state.
- After separate authorization, update the actual single runtime and managed clients; verify their fresh tools, procedure, context search/read and process/root identity.
- Check the requested Obsidian navigation in the actual vault. In selected
  project-update, 69 missing descriptions have already been reviewed, applied and
  read back unchanged in all other fields; 75 of that original 76-record inventory have descriptions.
  One unchanged oversized historical record awaits the corrected runtime. The
  fourteen flagged body/version cases have been reconciled as described above.

[Upgrade and restore instructions](../releases/1.3.0.md) describe the operational sequence without claiming it has already been performed.

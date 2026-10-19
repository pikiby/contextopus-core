# Contextopus 1.3: goal and delivery plan

> Historical document: release and verification conditions below apply only to
> the named version or dated check. For the current repository layout, see
> [development instructions](../development.md).

Delivery status: 1.3.3 was published and installed with the previous root, local
CPU profile and one service owner. Managed base documentation and the algorithm
catalog were updated through normal MCP operations. All 29 registered contexts
use format 4; all 425 registered Workspace records have descriptions, all 425
objects are indexed, and no structural errors were found. This does not establish
PROJECT completeness: five documents remain missing and six are placeholders.
Historical data, user rules and other unfinished work were preserved. Two old
cycles were cancelled separately with explicit user authorization. Platform and
model verification limits remain documented below; universal procedural compliance
by every model is not claimed.

The user authorized execution of this goal. Exact execution contracts are in the
[separate contract document](contextopus-1.3-contracts.md). Changes are accepted
through checks; publication and installation stay within the authorized scope.

## 1. Goal

Prepare Contextopus 1.3 so an agent receives enough information to choose search,
reading and memory updates without repeatedly loading large procedures or
duplicate data. Restore readable Obsidian links, meaningful card descriptions,
selection of distinct documents and a clear mandatory workflow. Deliver a direct
upgrade from installed 1.1 to 1.3, preserving user data and verifying the actual
running MCP and client skills.

A module author follows the documentation and places a package in `modules/`.
The user requests installation through one short skill. Core prepares dependencies,
applies module-supplied migrations and publishes operations after schema checks.

The goal is achieved only when every criterion in section 8 is met, with evidence
for one consistent release across source, published artifacts, installed package,
running process and connected client.

## 2. Verified starting state

- Source was marked 1.2.0. The working package checked during planning was 1.1.0;
  that installed copy had no `archivist` implementation.
- Source 1.2 had a common registry of five algorithms and search diagnostics.
  Older algorithms limited fragments before grouping documents. Having
  `archivist` did not automatically repair the other algorithms.
- Ordinary search returned `excerpt`. `read` and some receipts returned both
  IDs in `links` and descriptions of the same targets in `link_targets`.
  Inspected new cards lacked `description`, producing empty response strings.
  This was a creation/validation gap, not merely a presentation issue.
- `links` stored IDs; `sources` held separate mandatory references with retrieval
  instructions. Restoring Obsidian presentation must preserve that distinction.
- `$w` required a large Workspace procedure. A work cycle required startup;
  independent search also required instructions and project. Repeated skill
  invocation could easily repeat all preparation.
- Machine settings lived in INSTRUCTIONS frontmatter. Reading one permission
  returned the whole text. Arbitrary user rules still genuinely needed to be
  available to the agent in full.
- MCP exposed `contextopus_query`, `contextopus_execute` and older aliases.
  A full operation catalog was already optional: targeted `describe` existed.
- A reportedly missing search response was present in the combined output of a
  parallel call. This did not prove that the server had lost a result.

Primary verification locations:

- [MCP transport](https://github.com/pikiby/contextopus-core/blob/v1.3.0/src/contextopus/interfaces/mcp/server.py),
  [registry](https://github.com/pikiby/contextopus-core/blob/v1.3.0/src/contextopus/core/operations.py).
- [Workspace procedure](https://github.com/pikiby/contextopus-core/blob/v1.3.0/src/contextopus/resources/procedures/workspace.md),
  [search](https://github.com/pikiby/contextopus-core/blob/v1.3.0/src/contextopus/resources/procedures/search.md),
  [memory operations](https://github.com/pikiby/contextopus-core/blob/v1.3.0/src/contextopus/resources/procedures/reference/memory-operations.md).
- [Default instructions](https://github.com/pikiby/contextopus-core/blob/v1.3.0/src/contextopus/modules/workspace/default_instructions.md),
  [policies](https://github.com/pikiby/contextopus-core/blob/v1.3.0/src/contextopus/modules/workspace/policies.py),
  [cycles](https://github.com/pikiby/contextopus-core/blob/v1.3.0/src/contextopus/modules/workspace/cycles.py),
  [shared records](https://github.com/pikiby/contextopus-core/blob/v1.3.0/src/contextopus/modules/workspace/shared.py).
- [Selection](../search-selection.md), [search analysis](../search-analysis.md),
  [migration](https://github.com/pikiby/contextopus-core/blob/v1.3.0/src/contextopus/modules/workspace/migration.py),
  [integration](../integrations.md).

## 3. Accepted decisions and boundaries

### Accepted

1. Ordinary search returns metadata and a meaningful description. Text excerpts
   are excluded from the default response; explicit fragment retrieval remains.
2. Descriptions must be created and maintained. Missing descriptions are repaired
   from card bodies; a title or truncated opening is not a substitute.
3. The material limit applies to distinct documents. Repeated fragments of one
   document must not displace others. Older algorithms are repaired too.
4. Remove duplicate link representations, empty optional fields and routine
   technical receipts from ordinary responses. Preserve path and context ownership.
5. Compact search diagnostics remain mandatory and inform sufficiency assessment.
   Distance is not confidence.
6. Links must work in Obsidian again. The YAML ID remains the stable card identity.
   A card description differs from an explanation of a relationship.
7. Move machine settings out of free-form INSTRUCTIONS into common configuration.
   Keep user rules as one free-form text.
8. Continuous rereading defaults to off and may be enabled explicitly for an
   agent/model. This does not relax mandatory fresh reading of sources.
9. Repeated `$w` does not mean a new task or cycle. Independent retrieval requires
   no tmp, change proposal or cycle finish.
10. One short common procedure contains the complete ordinary workflow. Creation,
    migration, audit, rework and settings have separate procedures with explicit
    pointers. Ordinary phases do not each require another help call.
11. An agent must obtain and read an applicable procedure before acting. It must
    not replace mandatory steps with guesses.
12. The technical workflow does not force every ordinary worker to manage
    Workspace independently. Delegation retains applicable user rules.
13. Module installation includes storage preparation. Modules supply schemas and
    versioned migrations; Core owns connections, execution and version tracking.
    Users do not run SQL or assemble installation from multiple technical commands.
    Updates preserve data and check schema compatibility before activation or
    returning to previous code.

### Execution contracts

- MCP exposes `guide`, `read`, `write` by default. `guide` directly returns a named
  procedure or operation signature; a catalog is explicitly requested. Old names
  are available only in a separately enabled compatibility mode.
- YAML retains stable `id` and real Obsidian wikilinks with vault-relative paths.
  The internal graph uses IDs. Link labels do not replace target descriptions and
  are not presented as relationship explanations.
- Settings use Core JSON; `reread_instructions=false` by default. An explicit
  agent/model profile may change only rereading. `detail=full` preserves complete
  responses; ordinary responses are compact.
- Workspace format is 4; the main package is 1.3.0, with correction 1.3.1; changed
  built-in algorithms are 2.0.0. Git retains settings history separately from the
  free-form rules text.

Details and limits are in the [contracts](contextopus-1.3-contracts.md).
Tests establish implementation; installed version and a genuine client call
separately establish delivery.

### Excluded

- Automatically splitting free-form instructions by phase or selecting them with vectors.
- Having agents send known revisions to validate every rules read.
- A server-wide "instructions already read" flag shared by agents with different conversations.
- Mandatory `guide` between search, reading, writing and finish.
- A full catalog before every call or dozens of dynamic MCP tools.
- Switching a user's algorithm to Archivist without their choice.
- Cancelling other unfinished cycles to facilitate migration.
- A new comparative benchmark project, changes to the general concurrency model,
  a TUI redesign or new modules beyond the contracts needed for this update.

## 4. Implementation plan

### Stage 0. Capture the baseline

1. Check source version, Git revision, installed package path/version, running
   service, selected root, tool inventory and skills of every target client.
2. Inventory contexts, formats, IDs, links/sources, descriptions, settings, Git,
   analytics, unfinished cycles/proposals, model and algorithm catalog.
3. Save bounded control responses for search, read, startup, proposal/apply,
   permission reads and repeated `$w`. Anonymize public fixtures.
4. Distinguish Contextopus defects, agent errors and shell presentation of tool
   output. Investigate a stale-revision `tmp_write` error against the particular
   material and log; retain concurrent-change protection.

Outcome: a verifiable baseline matrix and regression fixtures.

### Stage 1. Define 1.3 contracts

1. Specify one compact format for responses, description, links and diagnostics.
2. Define three short tools and operation addresses. Core/modules share a registry;
   CLI/TUI retain the same domain operations.
3. Define compatibility for previous clients and stored proposals. Do not add all
   older names to the ordinary catalog without a clear, bounded transition mode.
4. Separate package version, Workspace format, algorithm version and analytical
   evidence format. Package 1.3 does not automatically imply data format 1.3.
5. Define a testable common workflow and explicit procedure pointers.

Outcome: implementation and tests need no guessed format.

### Stage 2. Settings and user instructions

1. Reuse Core configuration and its scopes, without a second settings database.
   Migrate `allow_implicit_updates`, `knowledge_approval_required`,
   `instructions_approval_required`, `git_history_enabled`, `material_max_tokens`
   and `create_required_sources`, retaining old contexts' effective values.
2. Read only requested effective settings and origins. Permission checks must not
   load rules or project bodies.
3. Add continuous rereading with default false. An explicit agent/model override
   changes neither other profiles nor writing permissions. Do not infer model
   identity from unreliable environment information.
4. INSTRUCTIONS retains the complete user text, including requirements spanning
   phases such as delegation, messaging and search limits. Do not automatically
   split or summarize it.
5. Preserve approval of rules/settings changes under current policy. Moving flags
   must not create a bypass through generic `settings_apply`.

Outcome: one settings source, preserved user rules and unchanged authorization.
Context creation offers updated defaults and individual choices.

### Stage 3. Short procedures, skills and MCP

1. Condense the main procedure to the full ordinary workflow: select context/mode,
   obtain rules, search/read, perform the task, compare results with memory,
   review/apply changes when needed, and finish.
2. Independent retrieval explicitly ends with an answer; reading creates no duty
   to write. An unfinished authorized task continues; a user question does not end it.
3. Explicitly forbid action without an applicable procedure. The common procedure
   covers ordinary operations and names the exact specialized procedures. Once
   obtained, reuse the procedure without rediscovering its pointer.
4. Require rereading for a new independent task, explicit context change, changed
   rules, lost complete text, and used procedures after a plugin update. In true
   mode, also reread at every `$w` invocation.
5. Remove arbitrary examples such as N=3 that change behavior without a reason.
   Inherit parameters; justify changes through the task or diagnostics.
6. Retrieve help only for an unknown operation. Generate required signatures from
   the registry rather than maintaining contradictory manual copies.
7. Update w, other existing entry points, wheel resources, native integrations,
   managed manifests and help. Ordinary work requires neither background client
   tool search nor `guide` at each ordinary phase.
8. Delegate with the necessary rules in the assignment. A cycle lead reads the
   context personally; an ordinary worker returns their result.

Outcome: a new agent follows a short instruction. Repeated `$w` creates no second
cycle and reloads no unchanged rules without a reason. A written prohibition is
not technical proof that a model understands it.

### Stage 4. Descriptions and links

1. Include description explicitly in author instructions, proposal preparation and
   API schemas. It explains content/applicability rather than repeating the title.
2. Require nonempty descriptions for new records. Authors review descriptions on
   substantive body changes. List legacy gaps separately; do not block old-memory
   reading because a description is missing.
3. An agent repairs descriptions after reading the complete material, with ordinary
   review/application under policy. Technical migration invents no facts and does
   not substitute a truncated opening.
4. Restore Obsidian wikilinks, including YAML. Preserve IDs and graph identity.
   Cover duplicate names, spaces, Unicode, vault-relative paths, cross-context links,
   renames and deletion.
5. Show links affected by a rename. Never silently change another context; the
   transaction respects its authorized write set.
6. Separate target descriptions from relationship reasons. If a relationship label
   is needed, define its own contract rather than repurposing description.
7. Preserve `sources` with reference/instruction and mandatory fresh reading on
   every receipt. Ordinary navigation links do not become mandatory sources.

Outcome: new materials are described, linked and navigable in MCP/Obsidian; old
materials receive a verifiable repair plan.

### Stage 5. Compact responses

1. Ordinary search returns ID, title, description, type/nonempty status, context,
   path, ranking information and compact diagnostics. It excludes excerpt.
2. Explicit fragment mode retains useful bounded reading; full read returns the
   body and the conditions needed to use it.
3. Read/startup/apply retain one list of related targets without duplicated IDs.
   Preserve path, context owner and nonempty sources.
4. Remove empty optional description/status/sources and empty problem lists. Do
   not universally remove false/0: settings/diagnostics need them. Preserve a
   populated status, including completed.
5. Move successful analytics receipts and routine indexed status to full detail.
   Keep index errors, incomplete writes, Git/analytics problems and other
   next-step-changing conditions visible.
6. SQLite retains observed operations and their Git relationships independently
   of response compactness. History and bounded analysis remain targeted operations.

Outcome: measurably smaller ordinary responses without losing decision inputs
or journal evidence.

### Stage 6. Selection and search assessment

1. With output=materials, group fragments by document key before the material
   limit and before inter-document boundary calculation. The representative is
   the nearest fragment. Cover distance_jump, distance_threshold, nearest_n and
   none, not only Archivist. Fragment mode retains explicit units/rules.
2. Distinguish technical candidate_limit, relevance cutoff and response size.
   Report technical incompleteness; do not promise to recover documents omitted
   from the candidate set.
3. Fix distance_jump applying N before jump assessment. Distinguish a result
   limit, no jump and insufficient data. Bump the changed algorithm version while
   preserving interpretation of old events.
4. Compact diagnostics include scope, algorithm, effective limits, considered
   fragments/distinct documents, returned materials, cutoff/incompleteness reasons.
   The full candidate snapshot is separate.
5. Make result assessment mandatory in the ordinary procedure. Distinguish wrong
   scope, technical limits, duplicates, cutoff and missing knowledge. Few results
   alone do not justify broadening search.
6. Choose reading by the task, description, type/status and applicability. A
   historical task may help; low distance proves neither freshness nor correctness.
   Read the card body before relying on it.
7. Update registry descriptions, derived RAG cards, guides, diagnostics and replay.
   State replay limits when older snapshots are incomplete.

Outcome: repeated fragments do not displace documents. The agent understands
what constrained selection and can justify reading or another query.

### Stage 7. Migration and recovery

Implement and verify section 5 on a data copy. Version 1.3 includes all required
transformations, including skipped 1.2 steps. Users need not install/run 1.2 first.

### Stage 8. Checks, documentation and delivery

1. Run section 6 checks; finish documentation, built-in base context, templates,
   manifests and client bundles.
2. Once publication is authorized, build 1.3, run CI, check wheel, sdist, client
   bundles and SHA256SUMS, and publish the exact verified commit.
3. Once installation is authorized, update the actual runtime, migrate, refresh
   managed skills, restart one shared MCP and verify clients.
4. Report saved, indexed, committed to Git, published, installed, running and
   connected separately. Never mark an unverified item complete.

### Pre-delivery addition: module installation and storage

1. Extend `module.json` with optional SQLite storage: target schema version,
   ordinary sequential SQL migrations and code-compatible schema versions.
   Modules without tables keep working.
2. Add a common Core service for domain tables in `core/storage/modules.sqlite3`.
   Module namespaces are separate; the analytics journal is not a domain catalog.
   Vectors stay in shared RAG under module/collection.
3. Validate migrations without execution during discovery. Installation applies
   missing steps transactionally with a version/checksum ledger. Identical retries
   do not repeat work; changed previously applied SQL is detected.
4. Provide the common storage API to handlers, including separate-process folder
   modules. They do not create their own connections to use Core tables. Queries
   cannot write or arbitrarily access another module's tables through this API.
   This is an API contract, not an OS sandbox.
5. `core.module_install` prepares dependencies/schema and activates as one task.
   Updates account for database state; failure never enables previous code against
   an incompatible schema. Disable retains tables, data and settings.
6. A short `$m` loads installation/update guidance. MCP, CLI and the existing
   Modules Install button call one implementation; no interface-specific installer
   or session-search special case is introduced.
7. Ship author guidance, a template and a runnable session-catalog example. Verify
   folder installation, API reads/writes, retry, updates retaining rows, checksum
   conflict, migration failure and incompatible rollback. The example does not
   automatically import existing external session-search databases.

Sol 6.1 workers split Core storage, lifecycle/protocol and interfaces/documentation.
The coordinator checks the integrated flow and records it in the active `$w`
cycle. Final artifacts are built after this addition is integrated; an earlier
build is not considered final.

## 5. Direct upgrade 1.1 -> 1.3

1. **Inventory/preview.** Identify exact executable/service/client paths, root,
   extras, model, formats and user settings. Find old managed skills/aliases and
   conflicts. Package version and data format are distinct.
2. **Recoverable snapshot.** Preserve configuration, cards, instructions, Git,
   SQLite, shared RAG, cycles/tmp/proposals, client configs and installed-version
   manifest from a consistent state. Use a coordinated backup for open databases,
   not arbitrary copies of changing files.
3. **Test a copy.** Exercise the same transition on an isolated root, checking IDs,
   permissions, links, search, pending records, repeat and rollback.
4. **Install 1.3.** Preserve root, profile and extras. Coordinate stopped/paused
   writes during cutover, replace the package and restart the single service;
   create no second owner of the shared database.
5. **Transform data.** Migrate settings/links and synchronize RAG metadata, format
   version and service contracts. Preserve user text, IDs, types, statuses and
   sources. Do not re-embed unchanged bodies without cause. If descriptions enter
   embedding input, explicitly version that decision and required reindexing.
6. **Descriptions.** List records without descriptions. Repair through separate
   substantive proposal work while reading remains available. Report format
   readiness and description completeness separately.
7. **Pending work.** Preserve cycle IDs, tmp, proposals and approved revisions.
   Approval never transfers to changed meaning. Compatible work continues;
   conflicts block only the relevant action and provide a repair path. Cancellation
   requires a separate user decision.
8. **Product materials.** Deliver new base context, algorithm descriptions,
   procedures and templates, preserving user edits and exposing conflicts.
9. **Clients.** Update only recognized managed skills/manifests for Codex, Claude
   Code, OpenCode and Crush. Preserve unrelated/user-edited files. Refresh each
   connection using the mechanism supported by that shell.
10. **End-to-end check.** From a fresh client, invoke new tools, obtain the
    procedure, search/read the selected context. Test a complete write cycle in a
    separate test context with explicit authorization.
11. **Rollback/retry.** Restore package, data and client configuration as an agreed
    set. Do not simply run 1.1 on already-incompatible 1.3 data. Repeated migration
    must not duplicate records or changes.

Separate test routes: 1.1 -> 1.3, 1.2 -> 1.3, repeat 1.3, interrupted migration,
user conflict and recovery from a snapshot.

## 6. Verification

| Area | What the check establishes |
| --- | --- |
| Selection | Repeated nearest fragments from one file plus other files yield distinct documents up to the limit; boundary and technical incompleteness are labelled correctly. |
| Modes | Materials/fragments have explicit units; pagination neither loses nor duplicates documents through mixed hidden units. |
| Responses | No default excerpt or duplicate ID list; description, path, context, meaningful status, sources and necessary errors remain. |
| Descriptions | Missing new descriptions are detected; changed content triggers review; legacy repair invents no facts. |
| Links | Wikilinks work in a real Obsidian vault; renames, cross-context links, duplicate names and migration retain the ID graph. |
| Settings | Migration retains explicit and absent old values; approval cannot be bypassed; false/0 survive serialization. |
| Procedures | A new agent obtains applicable guidance before acting; ordinary cycles need no guide at each phase; retrieval starts no writing. |
| Rereading | Both modes cover new task, context change, changed/lost rules and plugin update; agents share no already-read flag. |
| Delegation | A general user requirement, such as a worker's completion report, reaches that worker regardless of procedure phase. |
| Modules | One documented folder and Install call create tables and working operations; retry/failure/update preserve schema/code/data consistency. |
| Sources | Every repeated receipt requires a fresh check; unavailable/circular dependencies are not reported as verified. |
| Migration | IDs, rules, effective settings, pending work and analytics survive; retry/interruption/rollback are checked. |
| Delivery | Version matches across artifact, package, process and genuine client call; managed skills are updated. |

Automated tests establish contracts/state. Separate model scenarios and call logs
check behavior; a written prohibition does not prove compliance. Telegram tests
use a test recipient/stub, never send to user channels as part of software tests.

Compare MCP call counts, repeated rules retrieval, JSON size and available token
measurements on the same anonymized fixtures. Response size alone proves neither
overall token savings nor answer quality. This bounded update check is not a
separate benchmark project.

Platform matrix: Linux/macOS/Windows and supported Python versions. CI does not
replace verification of a particular installed client, OS startup or model call.

## 7. Execution and acceptance order

Dependencies: baseline -> contracts -> settings/cards/search -> common procedure
and MCP -> migration -> copy-based checks -> docs/build -> authorized publication
and installation -> real client verification.

After contracts, independent work may be delegated across disjoint ownership.
The coordinator retains the selected context, assignment scope, applicable rules
and acceptance criteria, and verifies returns. Previously user-selected Sol 6.1
is an explicit execution choice, not a Core capability.

Use the existing `$w` until the new contract is installed. After a significant
stage, save tmp, compare with memory and update the plan's state. During planning,
do not mark requirements implemented or replace factual records with future plans.

## 8. Goal completion conditions

- Accepted section 3 requirements are implemented; working options have exact contracts.
- All relevant section 6 checks pass, with explicit limits.
- Direct transition from 1.1 is verified without intermediate 1.2 or memory loss.
- Users see compact results and working Obsidian links; agents receive descriptions
  and diagnostics rather than noise in place of selection.
- Older algorithms are repaired; ordinary repeated `$w` does not repeat preparation.
- Approval policies, mandatory sources and result preservation are not weakened.
- A module installs from its documented folder through one skill; Core prepares
  dependencies/schema and operations genuinely read/write through the shared API.
  Retry, update and incompatible rollback are verified.
- The agreed release is installed and actually used by target clients. Publication
  alone does not complete the goal.
- Context/docs reflect verified state. A recoverable snapshot and rollback path
  exist; unresolved conflicts are not hidden under "complete".

Previous local acceptance covered 59 files through required runs/repeats:
751 unique tests passed, 8 skipped, 64 subtests passed. This is historical aggregate
Linux evidence for that candidate. Direct upgrades from genuine writers 1.1/1.2
passed on isolated data; Obsidian was checked in a separate vault and the module
example through one model `$m` call. This evidence does not automatically apply
to later artifact bytes.

Delivery: source was pushed; 1.3.0 passed full CI, was published and installed with
a recoverable consistent snapshot. Before the format change, nested vaults were
detected. Correction 1.3.1 preserves both `.obsidian` directories and selects the
explicit root's own boundary. After a second verified snapshot, exact 1.3.1 was
installed with one owner of the previous root.

The selected context's real 3->4 migration completed and retry was compatible.
It preserved 77 cards, 377 YAML-ID links, complete free-form rules, effective
settings and pending work. Before base-document delivery, 27 other contexts were
verified unchanged. Explicit `core.base_plan` / `core.base_install` and
`core.algorithms_refresh` delivered eight base cards and a catalog of five
algorithms 2.0.0 without changing active rules or model.

Full 1.3.1 CI completed: seven Linux/macOS/Windows and genuine-writer-1.1 upgrade
checks succeeded. [Release 1.3.1](https://github.com/pikiby/contextopus-core/releases/tag/v1.3.1)
was published as latest stable. All seven downloaded files matched verified
artifacts and GitHub digests. Codex ran `$w` with guide, rules, project, search and
reading. Claude runner used native `/w`; search/reading completed and guide was
called again. `project_read` is conditional: its absence alone proves no violation.

Early OpenCode/Crush probes passed `$w` as ordinary text and were incorrectly
called native activation checks. The observations remain, but that conclusion
was withdrawn. Correct `opencode run --command w` obtained guide/settings/search
and full reading without argument errors, using normal compact responses;
INSTRUCTIONS was not read.

In Crush 0.87, native ReadSkill supplied the exact released skill as a text/markdown
attachment in AgentMessage. Bytes were checked in the native user-message
attachment. Client source established inclusion in the prompt; the outgoing
provider request was not captured. MCP tools were connected. The model used
grep/glob/view and made zero MCP calls. This is a valid behavioral failure for
that scenario; its cause is unresolved. An earlier read-only-MCP-only scenario
established technical guide/schema/search/reading, not ordinary behavior.
One temporary A/B candidate explicitly naming Contextopus MCP also produced zero
MCP calls; it was neither accepted nor installed, and the released skill stayed
unchanged. GUI/GPU and every model scenario on every OS were not verified.
Detailed evidence/limits: [implementation verification](../implementation/contextopus-1.3.md).

Historical runtime 1.3.2 check:
`f0578ce1734af2b516cbfe8175b8f991d9fd8acf`, wheel SHA-256
`f8d47a8ea562532138c04b869cc1b8e8f008993e0cb683eae6183c7b2b076b1a`.
The seven-job successful CI matrix belongs to `2add7fa`. Subsequent metadata-only
`8b00620` passed 30 targeted tests plus exact installed-wheel, MCP and module-storage
checks. Genuine-writer-1.2 upgrade to wheel `8b00620` was checked separately:
one test in 25.81 s. Later reading-order refinement `f0578ce` passed three targeted
tests and exact-wheel MCP/guide/module-storage smoke. No repeated complete OS
matrix is attributed to that SHA.

Independent controlled-corpus model checks of the final wheel established
policy/full-INSTRUCTIONS reading, search inheriting N=2 and full retrieval of the
required fact in OpenCode 1.18.32 with DeepSeek Flash and Crush 0.87 with DeepSeek
Pro. OpenCode also read the linked plan completely. There were no filesystem
bypasses or writes. Crush recovered from one guessed ID-argument error by
requesting the signature and repeating a correct read.

These are two bounded scenarios, not proof of production ranking or universal
procedural compliance. Delegation, context changes, lost rules text and plugin
updates still lack separate observed evidence; no paired causal measurement of
call/token savings was performed. These results belong to the specified 1.3.2
runtime. Publication and technical access do not replace upgrade preservation or
a final data audit.

## Final 1.3.3 delivery

Immutable [release 1.3.3](https://github.com/pikiby/contextopus-core/releases/tag/v1.3.3)
corresponds to `9873157dde6f5f6c4c3fbda263c6b7e0bef12114`; wheel SHA-256:
`81c7aba6560129658d5f6201154bdffb6816730ae7c557afc6efe6ff812879c9`.
All seven published artifacts were downloaded and verified. Exactly 120 application
files were installed; local CPU dependencies, rules, settings and root were
preserved. Fresh MCP returned the current procedure. Managed base version is
1.3.3, its repeat plan is empty, and the algorithm catalog was refreshed/read.
Four existing client integrations produced unchanged previews: 14 managed
Codex/Claude files matched seven supplied skills; OpenCode/Crush retained their
previous HTTP configuration. Open sessions may need reconnecting or rereading.

The patch fixes migration planning when initial INSTRUCTIONS is absent and
proposals are retained, without treating missing old rules as approval of new
ones. Checks covered 30 affected cases, 40 version/release contracts with two
subtests, 28 MCP contracts and two cases on an isolated installed wheel.
The full OS matrix remains tied to `2add7fa`; model scenarios to 1.3.2 `f0578ce`.
Skills and procedure in 1.3.3 are byte-identical to those checks. This patch is
not credited with repeated model checks or measured token savings.

The final 29-context audit covers the complete registered set, descriptions,
link structure and index synchronization. It establishes neither freshness of
every historical external statement nor PROJECT completeness.

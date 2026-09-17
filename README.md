# Persistent Context Workspace

Version 0.7.2 provides one explicit `$pcw` skill, readable Markdown knowledge, a compact Current, and local semantic search. The primary agent remains the user-facing decision maker. The primary alone reads and changes PCW memory, Current, links and authorized memory history. Native subagents investigate or change explicitly authorized real sources and return findings; the semantic helper returns only embedding boundaries inside topic materials already divided by the primary. The current prohibition on worker access to PCW is implemented in the assignment, not by a technical sandbox. PCW is an MCP memory interface: it does not run a Controller, dispatch agents, or intercept their completion.

## Update the Codex plugin

For an existing `persistent-context-workspace` Git marketplace tracking this repository's `main` branch:

```bash
codex plugin marketplace upgrade persistent-context-workspace
codex plugin add persistent-context-workspace@persistent-context-workspace
```

The first command refreshes the marketplace checkout; the second installs the plugin version from that checkout. Start a new Codex thread after installation to load the updated skill and MCP tools.

See [release notes](CHANGELOG.md). Existing UUID-addressed knowledge requires an explicitly requested migration through `pcw_migrate_legacy_ids`; installing the plugin does not migrate it automatically.

The [0.7.2 verification report](docs/return-cycle-assessment.md) distinguishes protocol checks from end-to-end native latency. The earlier [0.7.1 report](docs/compact-memory-assessment.md) remains historical evidence.

## Use PCW

```text
$pcw Prepare context for the validator project at /path/to/project. Record its architecture and task constraints.

$pcw Continue the validator task using its existing context.
```

Everything after `$pcw` is natural language. Preparing or refining context does not execute a task saved in Current. Execution needs an explicit user request; it includes necessary preparation without another run command.

## Work cycle

The primary calls `pcw_startup` once to obtain task, Current, memory status and the saved model-map state. It resumes an unfinished request or opens a new one. Rules are available through `pcw_rules_get` and the skill references when needed; rule retrieval is separate from operations and has no operation side effects. There is no mandatory rules call before every action.

The primary reads relevant full materials, selects necessary facts and prepares a complete standalone assignment. `pcw_assignment_prepare` validates prerequisites and the exact published model profile. Launch only after `ready: true`, sending only `handoff.launch_message` in a clean native context without inherited conversation. Workers receive no memory coordinates, IDs, Current, ledger or PCW instructions. Their task prohibits PCW access through MCP, filesystem tools, shell and scripts. This is an assignment-level restriction, not an OS or tool-access guarantee.

The primary itself discovers current native model/reasoning capabilities and publishes the tools map. It reuses the map while actual capabilities remain unchanged. A new session or diagnostic warning is not a capability change; neither belongs in the environment version. Choose a sufficient profile and supported reasoning settings for the actual task, explaining the choice without inventing provider rankings.

On a substantive work/check return, the primary immediately divides its text into large, independently meaningful topic materials. It preserves actual facts, conditions, implementation detail, tables, code and uncertainty, and links related materials. It does not mechanically split by heading or fixed size, and no additional giant unmodified return file is required.

`pcw_result_store` saves those bodies and explicit links, verifies disk read-back and returns observed content and `split_sources` in one call. MCP generates each filename-ID and UTC save metadata. The primary inspects that response, assesses through `pcw_result_assess` and uses the returned revisions for the boundary helper. It does not repeat reads/links/preparation for unchanged state. Lower-level operations remain available for recovery.

`pcw_return_record` stores incomplete/error responses and completed operational evidence in control, without knowledge files. Incomplete work permits a continuation but cannot be accepted as complete; accepted evidence must explicitly resolve it. New knowledge contains reusable topic facts, not missing-content reminders or duplicate full artifacts. Completed assignment history is omitted from startup and remains available through `pcw_task_status`. `pcw_current_set` verifies its own disk read-back.

Bind executor identity from native launch/metadata evidence, never inherited shell variables. `pcw_assignment_rebind` repairs an evidenced mistaken binding and result metadata while preserving history; unresolved conflicts or interrupted repairs block completion. Evidence is recorded, not authenticated by the host. Prepared-message forwarding requires actual host support: text-only launchers still need the prepared text transferred. PCW does not add a dispatcher to bypass that limitation.

Identical saves are idempotent; conflicting changes require explicit revision-checked correction. Known incorrect active knowledge must be updated or replaced. A linked clarification and a closed discrepancy record do not correct the old body. Uncorrected invalidated knowledge is excluded from active search and direct reads warn about it. See [Memory operations](plugins/persistent-context-workspace/skills/pcw/references/memory-operations.md).

Factual checks are chosen for task complexity, at planned intermediate/final moments or after a mismatch requiring attention. They are not automatic for each return. A checker observes real sources or reproduces behavior, including research without changes; its findings are saved, read and assessed. Bind a planned check by passing `check_id` to assignment preparation without rewriting the plan.

The primary uses `pcw_transition` and `pcw_finish` to record actual operation state, then judges factual conformity with the user's full requested outcome. A `ready` response does not by itself mean the task is complete. Remaining authorized work continues until completion or a concrete blocker.

## Memory layout

Each semantic workspace is stored below its source project:

```text
<work-root>/.pcw/<workspace>/
├── current.md
├── knowledge/
│   └── <filename-id>.md
├── .pcw-runtime/
│   ├── active.json
│   └── lancedb/
└── .git/
```

Knowledge is free Markdown: it can contain prose, tables, code, facts, sources, conditions, and uncertainty. MCP generates each new ID and uses it as the filename; creation accepts content, not an agent-chosen name. The filename, including `.md`, is the material ID; path is separate. `links` stores these exact IDs. A move preserves the generated basename and updates search paths without re-embedding unchanged text. Existing materials remain readable and are migrated only by explicit request.

The separate `<work-root>/.pcw/.control/<workspace>/` store retains task state, models, assignments, actual executor sessions, return blocks, check plans and discrepancies independently of the derived index. The primary owns this state; workers receive only the prepared task text. Technical receipts and semantic-helper boundaries stay in control state rather than becoming knowledge reports.

Default checkpoint policy is `not_authorized`; `required` and `forbidden` need an actual authority reason. `pcw_task_update` corrects the active request with its revision without losing assignments. `pcw_task_checks_set` preserves planned factual checks; assignment preparation can bind their `check_id`. `pcw_finish` checks outstanding work, the check plan, corrected discrepancies, Current, affected preparation and authorized required checkpoints.

Current is readable Markdown with five sections: Goal, Constraints, Completion, Current step, and Blocker. It stays compact. The primary changes the step or blocker when the decision or obstacle changes, rather than after every return.

New or changed bodies remain readable while `pending_preparation`. **After** the primary saves the topic materials, `pcw_prepare_many` prepares them for a cheap suitable semantic helper. It receives only literal numbered text and returns arrays of embedding-block endings without tools. The primary submits them through `pcw_submit_boundaries_many`; MCP reconstructs unchanged parts and checks revisions. Single-material APIs remain available. The helper does not decide which knowledge files to create.

Links-only changes and moves do not re-embed. Consolidation changes actual materials and preserves useful conditions, exceptions, uncertainty, tables and code. Initial assignment/session/time accounting is retained in control state; source attribution and provenance metadata need not survive in consolidated knowledge.

## Search and embeddings

LanceDB stores literal semantic parts, their vectors, material filename-IDs, and current paths. Search returns a bounded set of whole topic-material candidates; the primary reads full selected bodies and follows useful links. Indexed parts help select those materials; they do not become a new snippet-search interface. Semantic search and knowledge consolidation solve different problems. Empty search output does not prove that knowledge is absent.

The bundled default is local `sentence-transformers` with `Qwen/Qwen3-Embedding-0.6B`; Qwen documents use literal parts and queries use its configured retrieval instruction. Ollama `/api/embed` and explicitly configured OpenAI-compatible `/v1/embeddings` are supported alternatives. Connection details are separate from the vector-space profile. A provider switch rebuilds vectors from stored literal parts into an inactive table, and activates source/profile/table together only after success. No provider fallback, fabricated vector, silent truncation, or re-splitting on a pure provider change is allowed.

Search cutoffs and profile values are provisional engineering defaults. They are not claims about measured quality, price, latency, storage, or CPU/RAM use. See [embedding configuration](plugins/persistent-context-workspace/skills/pcw/references/embeddings.md) for exact supported configuration and failure behavior.

The [project search assessment](docs/search-assessment.md) records actual local Qwen measurements and a calibrated starting profile for its frozen eight-document corpus. Its held-out questions recovered complete answers for 6 of 8 positive cases and rejected all 4 negative cases; Russian positive cases recovered 2 of 4. These results do not calibrate the bundled defaults or establish performance on another corpus. Local encoding processes one text at a time within a call, reusing the loaded model; the assessment records the memory failure that motivated this change and the verified repeat.

## Setup and permissions

PCW uses an existing Python 3.11+ interpreter, required package distributions, and Git for memory checkpoints. It does not create a virtual environment, install packages, or download model weights at startup. If a component is missing, the primary reports the exact interpreter, packages, destination, and failure. The primary asks the user for installation or model-download authority with that concrete scope, then performs the authorized repair and recheck. Refusal, lack of permission, or a failed installation remains a reported blocker.

The portable root `plugin.json` and `mcp.json` let the host resolve `${PLUGIN_ROOT}/scripts/launch.sh`. A successful standalone check or stdio handshake does not prove that an already-running host reconnected. After repair, retry only a supported host reload and verify the pending PCW operation. If the host needs a session restart, preserve the task and next action for continuation.

## History and verification

The primary, with actual authority, can create a local checkpoint with `pcw_checkpoint` for exactly the Current and knowledge paths changed by the request. Source commits, pushes, external changes, package installation, and model downloads have separate authority. Restore and reconciliation make derived search state match restored knowledge; Git does not reverse external effects.

Run the contract suite from the checkout root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_contracts.py -v
```

Static contracts check packaging, references, and documented invariants. They are not evidence of live host connection, real native-agent behavior, local-model quality, latency, resource use, or factual source checks. Those need their own real execution evidence.

The runtime suite also includes pytest tests; use the existing Python with PCW's dependencies available:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests -q -p no:cacheprovider
```

The following opt-in checks require an installed candidate matching the checkout. The host check compares the runtime, manifests, skill, and references before testing MCP through a fresh Codex process:

```bash
PCW_TEST_CODEX=1 python3 -m unittest tests.test_codex_host -v
PCW_TEST_CODEX=1 PCW_TEST_QWEN=1 python3 -m unittest tests.test_codex_host -v
PCW_TEST_NATIVE=1 python3 -m unittest tests.test_native_workflow -v
```

`PCW_TEST_QWEN` uses already cached model weights in offline mode. `PCW_TEST_NATIVE` makes actual model turns and selects the installed skill through Codex's native skill selector. It preserves process and thread IDs, selected model capabilities, and streamed events under `.pcw/project-update/.pcw-runtime/verification/native/`. Its trace must be assessed separately for instruction compliance, actor responsibilities, topic-block save/read/assessment order, executor sessions, and factual checks; a completed model turn or a returned marker alone is not acceptance.

The [implementation assessment](docs/implementation-assessment.md) records changes, checks, and acceptance status. The [regulation assessment](docs/regulation-assessment.md) checks the written instructions, and the [independent coverage assessment](docs/final-coverage-assessment.md) maps the guide's requirements to evidence and its limits.

Select a fixture with `PCW_NATIVE_SCENARIO`:

| Value | Intended observation |
| --- | --- |
| `simple` (default) | Bounded factual source check. |
| `prepare-context-only` | Consolidate context without executing the saved future task. |
| `multistage-normalize-cli` | Checks of interacting components and the complete pipeline. |
| `fault-after-saved-return` | Planned check after a temporary artifact is deliberately changed following a real saved return. Messages and product behavior are unchanged; a missed injection is inconclusive. |
| `mismatch-before-planned` | Contradictory real input during a prepared implementation task. The trace must establish an additional check before the planned output check. |
| `stale-environment-map` | Recovery from explicitly harness-authored prior state seeded through real MCP. This does not simulate an actual Codex upgrade. |

`PCW_NATIVE_TIMEOUT_SECONDS` sets a positive per-turn timeout (default 600). `PCW_NATIVE_REASONING_EFFORT` defaults to `high` and must match Astra's actual advertised reasoning options. `PCW_NATIVE_FOLLOWUP=1` selects the separate same-thread clarification check. Collector success alone is not semantic acceptance of any scenario.

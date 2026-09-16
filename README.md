# Persistent Context Workspace

Version 0.6.0 provides one explicit `$pcw` skill, readable Markdown knowledge, a compact Current, and local semantic search. The primary agent remains the user-facing decision maker. Native subagents investigate real sources, make authorized changes, perform factual checks, write Current, apply knowledge changes, and perform Git operations. PCW is an MCP memory interface: it does not run a Controller, dispatch agents, or intercept their completion.

## Update the Codex plugin

For an existing `persistent-context-workspace` Git marketplace tracking this repository's `main` branch:

```bash
codex plugin marketplace upgrade persistent-context-workspace
codex plugin add persistent-context-workspace@persistent-context-workspace
```

The first command refreshes the marketplace checkout; the second installs the plugin version from that checkout. Start a new Codex thread after installation to load the updated skill and MCP tools.

See [0.6.0 release notes](CHANGELOG.md). Existing UUID-addressed knowledge requires an explicitly requested migration through `pcw_migrate_legacy_ids`; installing the plugin does not migrate it automatically.

## Use PCW

```text
$pcw Prepare context for the validator project at /path/to/project. Record its architecture and task constraints.

$pcw Continue the validator task using its existing context.
```

Everything after `$pcw` is natural language. Preparing or refining context does not execute a task saved in Current. Execution needs an explicit user request; it includes necessary preparation without another run command.

## Work cycle

Before each meaningful action, the primary calls `pcw_action_requirements` with one of `prepare_assignment`, `process_result`, `transition`, or `finish`. It then acts within the user request, submits the applicable result, and gets requirements for the next action. This short loop supplies detailed instructions at the time they apply.

Before a native launch, the complete assignment must pass `prepare_assignment` with `ready: true` and an exact profile ID from the current tools map. A `ready: false` response still supplies instructions; the primary corrects the missing prerequisites and repeats the call before launching.

The primary reads Current and knowledge through MCP, determines scope, itself obtains native model/reasoning capabilities from environment tools, descriptors, and needed environment configuration, compares them with roles, maintains a current tools map, selects a suitable profile, directly launches native agents, and decides acceptance. This limited capability work is not delegated source research. A prepared simple task can use a smaller discovered profile when justified by the map. More capability or deeper reasoning must be justified by the actual task, uncertainty, or required check. PCW does not impose a ranking across providers or hard-coded reasoning settings.

After a worker returns, the primary calls `pcw_save_subagent_result` with the exact raw Markdown, registered assignment ID, and actual `executor_session_id`. MCP uses its allocated material ID and writes UTC `saved_at` with the executor metadata. The primary reads using `pcw_read` with the assignment ID, then records its assessment through `process_result`. Task/assignment coordination and raw recording do not authorize primary source work, content application, preparation or Git operations, and do not prove that the task succeeded.

Memory and Git returns name the affected materials and their actual status. A new raw return from the same executor can reuse its filename with `expected_previous_revision`: the matching revision permits an update, keeps links, and marks the new body for preparation. Exact repeat delivery remains idempotent. See [Memory operations](plugins/persistent-context-workspace/skills/pcw/references/memory-operations.md) for conflict handling and the save/read order.

Factual checks are scheduled by the primary at moments chosen from task complexity, or when a saved return shows a mismatch needing attention. They are not created for every return. A checker reproduces behavior or checks real sources, including a no-change research conclusion. Its result is saved and read in the same order before acceptance.

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

The separate `<work-root>/.pcw/.control/<workspace>/` store holds the model map and the explicit task/assignment ledger. It remains available if the workspace index is broken. The primary opens a request with `pcw_task_begin`, uses the complete registered handoff, binds the actual native executor, and saves/reads/assesses each assignment's raw return. Workers retrieve their full assignments with `pcw_assignment_get` before acting. `finish` verifies the retained affected materials, outstanding returns and discrepancies, Current and checkpoint state. Fixed-scope service receipts close preparation/checkpoint work without an endless series of new result files; see [memory closeout](plugins/persistent-context-workspace/skills/pcw/references/memory-operations.md#finite-service-closeout).

Current is readable Markdown with five sections: Goal, Constraints, Completion, Current step, and Blocker. It stays compact. The primary changes its step or blocker only when its decision or obstacle changes, so ordinary returns do not rewrite Current.

New or changed bodies are saved first and remain readable while `pending_preparation`. A dedicated native helper obtains the literal body, divides it into literal semantic parts, and submits them with the returned revision. Tables, code, conditions, and explanations are preserved. Links-only edits and renames do not invoke splitting or embedding. Consolidation changes the actual materials and retains useful conditions, exceptions, uncertainty, tables, and code; source attribution and provenance metadata need not be retained after compaction.

## Search and embeddings

LanceDB stores literal semantic parts, their vectors, material filename-IDs, and current paths. Search returns a bounded set of candidates; the primary reads full selected materials and follows useful links. Semantic search and knowledge consolidation solve different problems. Empty search output does not prove that knowledge is absent.

The bundled default is local `sentence-transformers` with `Qwen/Qwen3-Embedding-0.6B`; Qwen documents use literal parts and queries use its configured retrieval instruction. Ollama `/api/embed` and explicitly configured OpenAI-compatible `/v1/embeddings` are supported alternatives. Connection details are separate from the vector-space profile. A provider switch rebuilds vectors from stored literal parts into an inactive table, and activates source/profile/table together only after success. No provider fallback, fabricated vector, silent truncation, or re-splitting on a pure provider change is allowed.

Search cutoffs and profile values are provisional engineering defaults. They are not claims about measured quality, price, latency, storage, or CPU/RAM use. See [embedding configuration](plugins/persistent-context-workspace/skills/pcw/references/embeddings.md) for exact supported configuration and failure behavior.

The [project search assessment](docs/search-assessment.md) records actual local Qwen measurements and a calibrated starting profile for its frozen eight-document corpus. Its held-out questions recovered complete answers for 6 of 8 positive cases and rejected all 4 negative cases; Russian positive cases recovered 2 of 4. These results do not calibrate the bundled defaults or establish performance on another corpus. Local encoding processes one text at a time within a call, reusing the loaded model; the assessment records the memory failure that motivated this change and the verified repeat.

## Setup and permissions

PCW uses an existing Python 3.11+ interpreter, required package distributions, and Git for memory checkpoints. It does not create a virtual environment, install packages, or download model weights at startup. If a component is missing, a native diagnostic worker reports the exact interpreter, packages, destination, and failure. The primary asks the user for installation or model-download authority with that concrete scope, then delegates the authorized repair and recheck. Refusal, lack of permission, or a failed installation remains a reported blocker.

The portable root `plugin.json` and `mcp.json` let the host resolve `${PLUGIN_ROOT}/scripts/launch.sh`. A successful standalone check or stdio handshake does not prove that an already-running host reconnected. After repair, retry only a supported host reload and verify the pending PCW operation. If the host needs a session restart, preserve the task and next action for continuation.

## History and verification

An authorized worker can create a local checkpoint with `pcw_checkpoint` for exactly the Current and knowledge paths changed by the request. Source commits, pushes, external changes, package installation, and model downloads have separate authority. Restore and reconciliation make derived search state match restored knowledge; Git does not reverse external effects.

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

`PCW_TEST_QWEN` uses already cached model weights in offline mode. `PCW_TEST_NATIVE` makes actual model turns and selects the installed skill through Codex's native skill selector. It preserves process and thread IDs, selected model capabilities, and streamed events under `.pcw/project-update/.pcw-runtime/verification/native/`. Its trace must be assessed separately for instruction compliance, actor responsibilities, raw-result save/read order, executor sessions, and factual checks; a completed model turn or a returned marker alone is not acceptance.

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

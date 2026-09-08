# Persistent Context Workspace

Status: version 0.3.0 uses direct memory updates for both skills; the long-running scenarios in Phase E have not yet been completed. This file is the living implementation plan. Record architecture changes here before implementing them.

## 1. Purpose

The project provides a portable memory layer for long-running agent work on semantic subprojects. It borrows RLM ideas—external context, selective reading, and delegation—but adapts them to a session-based agent environment in which work lasts for weeks and includes real file changes.

The system must:

- preserve continuity across sessions;
- avoid loading the entire history into the primary agent;
- write durable results directly without a separate transaction buffer;
- progressively compact the current state instead of appending forever;
- retrieve details through links only when needed;
- use ordinary files, Git, and native agent tools;
- isolate the memories of unrelated subprojects;
- remain usable outside Codex.

The system must not become a log of every message, a copy of the source project, or an unbounded collection of reports.

## 2. Core model

Each semantic subproject has one durable memory and one prepared task context:

1. `knowledge/` is the only durable system memory. It stores linked objects, facts, rules, constraints, blockers, decisions, and relations.
2. `current.md` is a persistent compact root for one active task. It preserves a Task lock derived only from exact user meaning and links supporting knowledge and evidence for bounded retrieval. The user can refine it before execution.

Neither skill uses `tmp/`, transaction cycles, or a replacement journal. Reader and Worker reports are returned directly in working context; only requested durable meaning enters memory.

The context transformation is:

```text
verbatim user meaning + relevant knowledge + supported evidence
                         ↓
 task-locked, task-specific current.md
```

The execution transformation is:

```text
prepared current.md + original targets + current authority
                         ↓ clean Controller
     source result + knowledge changes + factual run state
```

Neither transformation summarizes the complete conversation. Unrelated memory never enters Current, and the clean Controller never inherits the primary conversation.

## 3. Workspace location

Memory lives in a hidden directory under the working project:

```text
<work-root>/.pcw/
├── project-a/
├── project-b/
└── project-c/
```

One directory represents one semantic subproject, not one session. Consecutive sessions for the same work reuse the same directory. Independent tasks do not share memory.

Subproject layout:

```text
.pcw/<subproject>/
├── current.md
└── knowledge/
    ├── index.md
    └── ...
```

In the first implementation, each subproject memory is its own local Git repository. This isolates memory history from source-code history and keeps service artifacts out of the source repository. The source project's own Git repository must ignore `.pcw/`.

## 4. `current.md` contract

`current.md` is not general project memory. It is the persistent compressed context and plan for one active task:

```markdown
# Current

Task: <active task identity and outcome>
Status: draft | ready | running | blocked | complete | closed

## Task lock

Verbatim request: <exact task-establishing user wording>
Required outcome: <meaning entailed by that wording>
In scope: <explicit scope or not further specified>
Out of scope: <explicit exclusions or not further specified>
User constraints: <verbatim constraints or none stated>
Authority: <explicit mutation and external-action authority>
Open questions: <material unresolved choices or none>

<supported execution logic, blockers, and factual execution state>

# References

- knowledge: [[knowledge/...]]
- evidence: <path, URL, or source coordinate>
```

Only two top-level headings are generated. The verbatim request, task identity, outcome, scope, exclusions, authority, critical user constraints, blockers, and execution logic remain directly in Current. Stable supporting detail may stay in linked knowledge. During a run, Readers may traverse those links for one exact question without changing the prepared task.

Task-defining meaning has `user` provenance. A `derived` implementation step is permitted only when primary evidence proves it necessary to an explicit user outcome inside the locked scope. A `fact` is supporting evidence, not a requirement. An `unresolved` inference remains an open question. Existing knowledge, broad audits, adjacent defects, best practices, and discovered infrastructure never expand Current by themselves.

The user may create, refine, replace, or close Current through `$pcw`. It persists after execution so the user can inspect and refine the same prepared context. `$pcw-run` may update only supported factual execution state and status; it cannot independently change task identity, scope, constraints, or plan. Current is not a record of the exact stage reached before interruption.

Do not include message chronology, unrelated project knowledge, every subagent report, or detail that cannot change execution. Bound Current by useful-context budget; use roughly 3,000 tokens until measured. Never meet the budget by dropping a relevant user constraint.

A later `$pcw` refinement replaces the affected active wording instead of appending a new quote, note, or chronology entry. Preserve the original task-establishing request and exact active constraints. Give each meaning one durable owner: task-specific meaning stays in Current; explicitly requested cross-task meaning belongs in knowledge.

## 5. Direct durable updates

Both skills write intended durable changes directly to `current.md` or `knowledge/`. They do not create intermediate result files, manifests, receipts, promotion inputs, Current snapshots, transaction cycles, or cleanup stages. They do not replace those artifacts with another journal or temporary memory directory.

Reader and Worker answers travel through direct agent messages. The recipient uses relevant results for the requested task and stores durable meaning only in its intended owner. Raw answers are not retained as a second memory layer.

Git stores committed file versions. An interruption can leave unfinished changes in the worktree; it does not leave a PCW record of completed and pending stages. The next session has the saved memory and existing files, not a guaranteed recoverable transaction. PCW does not promise atomic updates, automatic rollback, or exact-stage recovery.

No mandatory runtime validation or acceptance pass follows an edit. Tests, rereading for acceptance, and other checks are not added by PCW; they run only when they belong to the user's task. Scope, authority, provenance, and accurate reporting remain rules for carrying out that task.

## 6. `knowledge/`: durable knowledge

`knowledge/` is the only durable system memory. It stores compact source-backed information that may matter after a task or stage changes:

- architecture decisions and their reasons;
- stable domain constraints;
- component relations;
- diagnostic and testing procedures with their sources and known limits;
- significant incidents and causes;
- active external dependencies and blockers;
- pointers to primary sources.

One record covers one coherent subject. The base format is Markdown with short metadata:

```markdown
---
id: source-ingestion
kind: object
status: active
tags: [source, reader]
supersedes: []
sources:
  - path/to/file:10
---

# Source ingestion

Short source-backed content with attribution and any uncertainty.

## Relations

- depends_on: [[adaptive-chunking]]
- affects: [[reader-routing]]
```

JSON is not a required source format. A source may be any file type, directory, repository, URL, or other accessible object. Machine-readable fields describe a knowledge record and primary coordinates; they do not replace the primary material.

Initial retrieval uses:

- `knowledge/index.md` for major topics;
- clear filenames;
- `rg` for full-text search;
- wiki links and typed relations;
- `tags`, `sources`, and `supersedes` fields.

A vector database, graph database, or dedicated MCP is unnecessary in the first phase. Add one only after measured evidence that file search is insufficient.

## 7. Two natural-language entry skills

Version 0.3.0 exposes exactly two explicit-only skills:

- `$pcw` creates or updates linked knowledge and creates, refines, replaces, or closes the persistent task-specific Current. It does not execute the source task.
- `$pcw-run` executes the prepared Current through a clean Controller and directly persists durable results and factual execution state. It does not independently replan.

Everything after either skill is natural language. Paths, context identity, scope, constraints, and requested outcome may appear in any order. No positional argument, fixed verb, or mandatory template exists. The agent asks only when unresolved ambiguity would select a materially different workspace, context change, or execution target.

### 7.1. Predetermined complete reading

Instruction boundaries are defined by the plugin author, not selected by the executing agent. Every required document is read in full. The agent may not omit required sections because it considers them irrelevant.

The references are separated by responsibility:

- `pcw/references/workspace-contract.md`: shared Current, knowledge, provenance, scope, authority, and Git rules;
- `pcw/references/state-machine.md`: the `$pcw` context-editing procedure only;
- `pcw-run/references/state-machine.md`: the `$pcw-run` execution procedure, clean Controller, and Worker boundaries only;
- `pcw/references/agent-routing.md`: shared bounded Reader routing, without run-only execution requirements.

Each entry skill specifies its exact required set, including operation and Reader references, to read completely before working. `$pcw` does not load the run-only procedure. `$pcw-run` does not load the context-editing procedure or context-query operation. Shared requirements remain mandatory for both. Reading an operation contract does not make executing that operation mandatory when the request does not need it.

### 7.2. Internal operation references

Technical transitions are Markdown files under `pcw/references/operations/`, not Codex skills. Therefore they do not appear in skill completion and cannot be invoked as user commands.

Each operation reference declares its inputs, procedure, result, and authority boundaries. The active entry skill reads the specified operation file in full before using it. Operation results are returned directly, without on-disk envelopes or a separate result-validation step.

The initial operations are:

- `pcw-resolve-workspace` and `pcw-query-context` for exact memory selection and task-relevant retrieval;
- `pcw-inspect-source` for bounded read-only source selection;
- `pcw-checkpoint-memory` for local durable-memory commits.

These are the only four operation references. The cycle, source-map, intermediate-result, promotion, Current-compaction, validation, and pruning operations are removed for both entry skills.

Add another public skill only when the user needs another distinct top-level action. Add a reference operation only for a repeatable internal transition with its own postcondition.

## 8. Flexible procedures

The state machine describes allowed transitions, not one mandatory itinerary. The active public skill performs only the operations required by the current request.

For `$pcw`:

1. `pcw-resolve-workspace` selects exactly one semantic subproject; explicit creation initializes the directory and local Git.
2. `pcw-query-context` selects only existing meaning relevant to the request.
3. Optional `pcw-inspect-source` and bounded Readers gather only evidence actually needed for the requested memory change and return it directly without persistent intermediate files.
4. The primary edits the durable owner of each requested meaning. A normal task refinement changes Current only; knowledge changes only for explicitly requested durable cross-task meaning.
5. `pcw-checkpoint-memory` commits the task's memory changes unless explicitly forbidden, leaving unrelated changes untouched.

For `$pcw-run`:

1. Select the existing workspace and prepared Current.
2. Start a clean Controller with `fork_turns: "none"` and the exact run package.
3. The Controller reads Current in full, performs the authorized task, and obtains missing supporting detail through bounded retrieval when needed.
4. The Controller directly updates durable knowledge and Current's factual execution state without altering its Task lock.
5. Create the local memory checkpoint unless explicitly forbidden and return a compact account of the result and any remaining blocker.

For `$pcw`, every changed meaning requires support from the current user request, and an equivalent refinement replaces rather than accumulates text. For `$pcw-run`, task identity, scope, constraints, and plan remain unchanged; only factual execution state and status may change.

An explicit prohibition of the local checkpoint leaves durable changes uncommitted. Source-repository commits and every push remain outside this automatic behavior.

## 9. Working session

### Session start

1. The user invokes `$pcw` or `$pcw-run` with an unrestricted natural-language request.
2. The selected skill extracts the work root, semantic context, exact requested action, scope, and authority from the complete message.
3. `$pcw` selects task-relevant knowledge, optionally gathers read-only evidence, and directly creates or refines durable memory without executing the source task.
4. `$pcw-run` requires an existing prepared Current and starts a clean Controller without inherited turns. Existing unrelated worktree changes are not overwritten or silently included in the memory commit.

A newly prepared task does not inherit an old plan merely because that plan exists. Durable knowledge remains available to `$pcw`, while the user's current request determines which meanings enter Current.

### Source investigation

First, `pcw-inspect-source` uses cheap methods:

- file types and sizes;
- directory tree;
- extensions and signatures;
- obvious structural boundaries;
- selective read and search support.

Read a small or clearly structured source directly. For a large or unknown source, give Readers bounded questions and source coordinates. Readers use natural boundaries such as log events, table rows, document sections, or project files and return one compact merged answer. Neither entry skill writes a source map or raw Reader reports to a transaction buffer.

### Execution

The primary agent acts as user interface and authority gate. It passes the clean Controller the exact current run request, complete Current, exact roots and coordinates, and current authority. It does not add old conversation summaries, execute the prepared task itself, or author preferred requirements.

The Controller reads Current first and treats its Task lock as immutable. It performs only the requested outcome and supported necessary implementation steps inside that outcome. It reads a small precise target directly. For missing supporting detail in a large or ambiguous area, it gives one Reader one exact question. The Reader starts from Current's knowledge links, follows only relevant active relations and primary coordinates, classifies relevance, and may recursively delegate bounded subquestions. Each parent Reader merges its children and returns one compact result, so the Controller never receives every raw report. Retrieval cannot fill a missing task definition, expand authority, or change the prepared task. Missing task-defining context or unresolved required evidence returns `context_insufficient`; a scope conflict returns `context_scope_conflict`; missing user input or authority returns `needs_input` through the primary agent.

The Controller writes durable results directly to knowledge and supported factual execution state directly to Current. Proposals stay attributed as proposals, uncertain findings stay uncertain, and source facts do not become user requirements. No separate promotion or acceptance step is required.

A separate Verifier is not part of the architecture. Add another coordination role only for a concrete need.

### Completion

The Controller returns a compact result stating what was done and any remaining blocker or uncertainty. The primary agent relays that result without a mandatory reread of the complete changed target or semantic-acceptance pass. Tests run only if they form part of the user's task; the response must not claim checks that did not run.

Durable memory is updated directly, then checkpointed unless the user forbids it. If the checkpoint cannot be created, report that the changes remain uncommitted. No cycle-completion marker, receipt, snapshot, or cleanup is needed.

The next session can refine the persistent Current with `$pcw`, rerun it with `$pcw-run`, or replace it with a different task built from the same linked knowledge.

## 10. Primary agent and clean Controller

For `$pcw`, the primary agent makes a direct minimal durable edit and may use Readers for bounded source reduction. Reader output is merged in working context and not persisted.

For `$pcw-run`, a clean Controller is mandatory. It starts with `fork_turns: "none"`, with no inherited conversation, and receives only the prepared run package. This separation prevents the primary agent's old assumptions from being mixed back into Current during execution. The primary does not perform a separate acceptance review or introduce old context or preferred requirements. If the host cannot provide a clean Controller, execution stops rather than silently inheriting the old conversation.

## 11. Model selection

Select a model after cheap source inspection and operation-complexity assessment, not by permanently assigning maximum reasoning to a role.

- Luna handles high-volume simple reading, region classification, and extraction under a clear schema.
- Terra handles ambiguous analysis, architecture relations, code authoring, and file changes.
- Sol manages the active operation, communicates with the user, and makes final decisions.

A Reader usually starts on Luna. Route an ambiguous region, cross-file inference, or design decision to Terra. Choose reasoning effort for the concrete region and increase it after the first pass when justified.

## 12. Git as memory

Git:

- stores earlier committed memory states;
- shows semantic memory changes for a stage;
- supports branches for parallel directions;
- makes earlier file versions available without permanent archive copies.

Git must not store:

- the complete chat;
- raw copies of large sources;
- every subagent message;
- secrets or private tokens.

Local memory commits are automatic unless the user forbids them. Commit only the task's intended memory paths and preserve unrelated staged or unstaged changes. Commits outside the selected PCW memory repository and every push require explicit authorization. A checkpoint message describes the semantic memory change, not a session number.

Git records file history, not which execution steps completed. It does not provide transaction recovery for external changes, uncommitted work, or agent reports that existed only in working context.

## 13. Repository layout

```text
persistent-context-workspace/
├── .agents/plugins/marketplace.json
├── PLAN.md
├── README.md
├── plugins/
│   └── persistent-context-workspace/
│       ├── .codex-plugin/plugin.json
│       └── skills/
│           ├── pcw/
│           │   ├── SKILL.md
│           │   ├── agents/openai.yaml
│           │   └── references/
│           │       ├── state-machine.md
│           │       ├── workspace-contract.md
│           │       ├── agent-routing.md
│           │       └── operations/
│           │           ├── pcw-resolve-workspace.md
│           │           ├── pcw-query-context.md
│           │           ├── pcw-inspect-source.md
│           │           └── pcw-checkpoint-memory.md
│           └── pcw-run/
│               ├── SKILL.md
│               ├── agents/openai.yaml
│               └── references/state-machine.md
└── tests/
    ├── fixtures/
    └── test_contracts.py
```

Exactly two public skills exist: `pcw` and `pcw-run`. Shared memory rules, Reader routing, and four internal operation references live under `pcw/references/`. Each skill has its own `references/state-machine.md`; technical operations are not registered as skills.

## 14. Implementation phases

### Phase A. Formats and invariants

- define linked durable knowledge as the only system memory;
- define persistent task-specific Current and its budget;
- use direct durable updates for both skills without a transaction buffer;
- define semantic subproject identifiers;
- establish link, status, and Git rules.

### Phase B. Natural-language interface and isolation

- expose only explicit `$pcw` and `$pcw-run` skills;
- accept natural-language requests without positional arguments or fixed verbs;
- keep all technical operations outside the registered skill set;
- require a clean Controller for execution;
- permit bounded question-driven run-time retrieval from Current links while preventing independent replanning;
- define exact required reading sets and read each required document completely;
- keep shared, context-editing, and execution rules separate.

### Phase C. Narrow memory operations

- create `pcw-resolve-workspace`;
- create read-only `pcw-query-context`;
- create `pcw-checkpoint-memory`;
- write requested durable results directly to their owners;
- remove cycle, intermediate-result, promotion, compaction, validation, and pruning operations;
- disable implicit invocation for both public skills;
- remove mandatory runtime checks and acceptance passes;
- document interruption limits without promising exact-stage recovery.

Implement reliable memory updates before complete source analysis; otherwise results become another growing archive.

### Phase D. Sources and agents

- create read-only `pcw-inspect-source`;
- use bounded source questions and natural source boundaries without an on-disk map;
- establish Reader, Controller, and Worker result contracts;
- add Luna/Terra routing;
- keep child results in direct messages rather than a persistent buffer.

### Phase E. Long-running scenarios

- run at least 30 consecutive sessions on a test subproject;
- measure growth of `current.md`, `knowledge/`, and Git;
- refine and replace Current across sessions;
- observe the committed and uncommitted state left by interrupted edits and runs;
- verify a parallel branch and later knowledge merge;
- verify transfer to another agent environment.

These are separate development experiments, not steps added to normal PCW requests. Tests run only as part of an explicitly requested task.

## 15. Intended MVP behavior

The intended behavior is:

- a new session creates or refines Current without the complete chat;
- a clean Controller executes from Current without inherited conversation and receives only compact results from bounded knowledge and source retrieval;
- every Current preserves a verbatim Task lock, and facts or agent inferences cannot silently expand it;
- execution respects the Task lock without a separate mandatory acceptance stage;
- missing task context produces `context_insufficient` instead of improvisation;
- active user constraints remain present through direct refinements;
- `current.md` remains bounded and task-specific across sessions;
- detail is retrievable through links and `rg`;
- unconfirmed material never becomes fact;
- neither skill creates temporary cycles, intermediate result files, or a replacement journal;
- interruption leaves file state and Git history without a guarantee of exact-stage recovery;
- source-project changes and memory changes remain distinguishable;
- the system works with ordinary files and Git without a required external service;
- the plugin installs and updates as one marketplace unit.

## 16. Deferred decisions

These are unnecessary for the first working prototype and must be decided from usage evidence:

- one shared memory repository versus one Git repository per subproject;
- automatic backlink generation;
- a full-text index beyond `rg`;
- vector search;
- an MCP interface;
- cross-machine memory synchronization;
- automatic branching and merge policies.

Until measured evidence requires more, keep two natural-language skills, one linked durable knowledge layer, one persistent task-specific Current, direct updates, and Git.

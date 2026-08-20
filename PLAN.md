# Persistent Context Workspace

Status: the plugin MVP is implemented; the long-running scenarios in Phase E have not yet been completed. This file is the living implementation plan. Record architecture changes here before implementing them.

## 1. Purpose

The project provides a portable memory layer for long-running agent work on semantic subprojects. It borrows RLM ideas—external context, selective reading, and delegation—but adapts them to a session-based agent environment in which work lasts for weeks and includes real file changes.

The system must:

- preserve continuity across sessions;
- avoid loading the entire history into the primary agent;
- separate temporary cycle results from durable knowledge;
- progressively compact the current state instead of appending forever;
- retrieve details through links only when needed;
- use ordinary files, Git, and native agent tools;
- isolate the memories of unrelated subprojects;
- remain usable outside Codex.

The system must not become a log of every message, a copy of the source project, or an unbounded collection of reports.

## 2. Core model

Each semantic subproject has one durable memory, one prepared task context, and one temporary transaction buffer:

1. `knowledge/` is the only durable system memory. It stores linked objects, facts, rules, constraints, blockers, decisions, and relations.
2. `current.md` is a persistent compact root for one active task. It contains task-defining meaning directly and links supporting knowledge and evidence for bounded retrieval. The user can refine it before execution.
3. `tmp/` contains raw and intermediate material from exactly one active or interrupted transaction. It is recoverable but not durable knowledge.

The context transformation is:

```text
user meaning + relevant knowledge + supported evidence
                         ↓
           task-specific current.md
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

Proposed subproject layout:

```text
.pcw/<subproject>/
├── current.md
├── knowledge/
│   ├── index.md
│   └── ...
├── tmp/
│   └── <cycle-id>/
│       ├── manifest.md
│       ├── findings/
│       ├── work/
│       └── handoff.md
└── .gitignore
```

In the first implementation, each subproject memory is its own local Git repository. This isolates memory history from source-code history and keeps service artifacts out of the source repository. The source project's own Git repository must ignore `.pcw/`.

## 4. `current.md` contract

`current.md` is not general project memory. It is the persistent compressed context and plan for one active task:

```markdown
# Current

Task: <active task identity and outcome>
Status: draft | ready | running | blocked | complete | closed

<compact task root: exact outcome, scope, authority, critical rules and
constraints, blockers, ordered execution logic, and factual execution state>

# References

- knowledge: [[knowledge/...]]
- evidence: <path, URL, or source coordinate>
```

Only two top-level headings are generated. Task identity, outcome, scope, authority, critical user constraints, blockers, and execution logic remain directly in Current. Stable supporting detail may stay in linked knowledge. During a run, Readers may traverse those links for one exact question without changing the prepared task.

The user may create, refine, replace, or close Current through `$pcw`. It persists after execution so the user can inspect and refine the same prepared context or recover an interrupted run. `$pcw-run` may update only supported factual execution state and status; it cannot independently change task identity, scope, constraints, or plan.

Do not include message chronology, unrelated project knowledge, every subagent report, or detail that cannot change execution. Bound Current by useful-context budget; use roughly 3,000 tokens until measured. Never meet the budget by dropping a relevant user constraint.

## 5. `tmp/`: transaction buffer

`tmp/` receives raw material for exactly one active or interrupted `$pcw` or `$pcw-run` transaction:

- local maps and source descriptions;
- Reader results;
- Worker assignments and reports;
- evidence coordinates;
- conflicts and uncertain hypotheses;
- actual changes and verification results;
- exact user meaning not yet incorporated into memory.

Each cycle writes to its own directory. Files should reference sources rather than copying them in full without need.

`tmp/`:

- is not durable memory;
- is not indexed as confirmed knowledge;
- is not committed to Git;
- is not deleted before promotion, compaction, validation, and a local memory checkpoint succeed;
- may survive an interrupted session.

After success, remove only the exact absorbed cycle directory. Keep the ignored `tmp/` directory itself for future transactions. At session start, recover an unfinished cycle from its files and Git state before opening another; never infer transaction state from chat history.

## 6. `knowledge/`: durable knowledge

`knowledge/` is the only durable system memory. It stores compact source-backed information that may matter after a task or stage changes:

- architecture decisions and their reasons;
- stable domain constraints;
- component relations;
- verified diagnostic and testing procedures;
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

Short verified content.

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

Version 0.2.0 exposes exactly two explicit-only skills:

- `$pcw` creates or updates linked knowledge and creates, refines, replaces, or closes the persistent task-specific Current. It does not execute the source task.
- `$pcw-run` executes the prepared Current through a clean Controller and persists verified results. It does not independently replan.

Everything after either skill is natural language. Paths, context identity, scope, constraints, and requested outcome may appear in any order. No positional argument, fixed verb, or mandatory template exists. The agent asks only when unresolved ambiguity would select a materially different workspace, context change, or execution target.

### 7.1. Shared process contract

The two entry skills share:

- cycle states and legal transitions;
- invariants for `current.md`, `tmp/`, `knowledge/`, and Git;
- the order in which results pass between operations;
- stop, recovery, idempotency, and authority rules;
- source-analysis and Controller/Reader/Worker routing.

The shared contract lives under `pcw/references/`. Each entry skill canonicalizes that path, reads the required shared references, and stops when the contract is missing or escapes the plugin skills root.

### 7.2. Internal operation references

Technical transitions are Markdown files under `pcw/references/operations/`, not Codex skills. Therefore they do not appear in skill completion and cannot be invoked as user commands.

Each operation reference declares exact preconditions, inputs, procedure, result, blockers, and repeated-call behavior. The active entry skill reads the exact operation file immediately before executing it and validates its result envelope before selecting the next transition.

The initial operations are:

- `pcw-resolve-workspace` and `pcw-query-context` for exact memory selection and task-relevant retrieval;
- `pcw-open-cycle`, `pcw-record-result`, and recovery for transactional input;
- `pcw-inspect-source` and `pcw-map-source` for bounded source analysis;
- `pcw-promote-knowledge`, `pcw-compact-current`, and `pcw-validate-memory` for durable state;
- `pcw-checkpoint-memory` and `pcw-prune-tmp` for the automatic local memory transaction.

Add another public skill only when the user needs another distinct top-level action. Add a reference operation only for a repeatable internal transition with its own postcondition.

## 8. Transaction procedure

The active public skill assembles one transaction from narrow internal operation references. No operation may declare the whole memory update complete by itself.

1. `pcw-resolve-workspace` selects exactly one semantic subproject read-only.
2. `$pcw` uses `pcw-query-context` to select only existing knowledge relevant to the requested Current change.
3. `pcw-open-cycle` creates or recovers one transaction and snapshots the input state.
4. Optional `pcw-inspect-source` and `pcw-map-source` gather bounded read-only evidence.
5. `pcw-record-result` writes each accepted user, Reader, Controller, or Worker result to `tmp/` with exact scope and coordinates.
6. `pcw-promote-knowledge` classifies every accepted meaning as a knowledge change, permitted Current change, reference, ephemeral detail, or conflict. It writes durable knowledge before Current.
7. `pcw-compact-current` rebuilds the whole Current from the promotion manifest, removes duplication and operational noise, and retains every task-relevant rule and constraint.
8. `pcw-validate-memory` checks support, completeness, links, Current shape, scope, conflicts, and the untracked status of `tmp/` without writing.
9. `pcw-checkpoint-memory` commits only validated paths inside the selected memory repository unless explicitly forbidden.
10. `pcw-prune-tmp` removes only the exact absorbed cycle represented by that checkpoint, without requesting separate permission.

For `$pcw`, Current changes require support from the current user request. For `$pcw-run`, promotion, compaction, and validation reject any independent change to task identity, scope, constraints, or plan and permit only evidenced execution state and status.

An explicit prohibition of the local memory transaction leaves validated changes and processed `tmp/` intact. Source-repository commits and every push remain outside this automatic transaction.

## 9. Working cycle

### Session start

1. The user invokes `$pcw` or `$pcw-run` with an unrestricted natural-language request.
2. The selected skill extracts the work root, semantic context, exact requested action, scope, and authority from the complete message.
3. If an unabsorbed cycle exists, recover and finish or report that exact cycle before opening another.
4. `$pcw` selects task-relevant knowledge, optionally gathers read-only evidence, and creates or refines Current without executing it.
5. `$pcw-run` requires an existing valid Current and starts a clean Controller without inherited turns.

A newly prepared task does not inherit an old plan merely because that plan exists. Durable knowledge remains available to `$pcw`, while the user's current request determines which meanings enter Current.

### Source investigation

First, `pcw-inspect-source` uses cheap methods:

- file types and sizes;
- directory tree;
- extensions and signatures;
- obvious structural boundaries;
- selective read and search support.

Read a small or clearly structured source directly. If a large or unknown source requires distributed work, `pcw-map-source` applies two-stage adaptive partitioning:

1. divide the source without loss into sequential overlapping windows;
2. let Readers identify local format and record coordinates;
3. repartition by natural objects such as log events, table rows, JSON entities, text sections, or project files;
4. merge and reread objects split at window boundaries.

The map is temporary navigation material in `tmp/`, not mandatory durable knowledge.

### Execution

The primary agent acts only as user interface and authority gate. It passes the clean Controller the exact current run request, complete Current, exact roots and coordinates, and current authority. It does not add old conversation summaries or execute the prepared task itself.

The Controller reads Current first and treats it as the immutable task root. It reads a small precise target directly. For missing supporting detail in a large or ambiguous area, it gives one Reader one exact question. The Reader starts from Current's knowledge links, follows only relevant active relations and primary coordinates, and may recursively delegate bounded subquestions. Each parent Reader merges its children and returns one compact result, so the Controller never receives every raw report. Retrieval cannot fill a missing task definition, expand authority, or change the prepared task. Missing task-defining context or unresolved required evidence returns `context_insufficient`; missing user input or authority returns `needs_input` through the primary agent.

`pcw-record-result` stores a normalized account in `tmp/`: what changed, where, which checks ran, and what remains unverified. Promotion decides whether each verified meaning becomes durable knowledge, factual Current state, or ephemeral transaction material.

A separate Verifier is not part of the architecture. Add another coordination role only for a concrete need.

### Completion gate

Before telling the user that a run or meaningful stage is complete, `$pcw-run` must:

1. inventory every accepted source change and every external fact that materially affected the result;
2. verify that `pcw-record-result` represents the final state, checks, coordinates, and remaining uncertainty for each item;
3. reject any stale contradiction between the prepared Current, actual targets, and verified result;
4. run promotion, compaction, and validation for all unabsorbed results;
5. complete the automatic local checkpoint and exact-cycle pruning unless explicitly forbidden.

If the user forbids the memory transaction, report source completion separately and retain recoverable inputs. Never report the PCW cycle complete while final work is missing from memory, Current contradicts the target, validation has not succeeded, or checkpointing remains unresolved.

### Stage completion

1. All factual results exist in `tmp/`.
2. `pcw-promote-knowledge` updates durable records.
3. `pcw-compact-current` rebuilds and compacts `current.md`.
4. `pcw-validate-memory` checks the resulting state without writing.
5. Only after validation may `pcw-checkpoint-memory` run, followed by `pcw-prune-tmp` after a confirmed checkpoint.

The next session can refine the persistent Current with `$pcw`, rerun it with `$pcw-run`, or replace it with a different task built from the same linked knowledge.

## 10. Primary agent and clean Controller

For `$pcw`, the primary agent manages the context transaction and may use Readers for bounded source reduction.

For `$pcw-run`, a clean Controller is mandatory. It starts with no inherited conversation and receives only the prepared run package. This separation prevents the primary agent's old assumptions from being mixed back into Current during execution. If the host cannot provide that isolation, execution stops rather than silently degrading to normal mode.

## 11. Model selection

Select a model after cheap source inspection and operation-complexity assessment, not by permanently assigning maximum reasoning to a role.

- Luna handles high-volume simple reading, region classification, extraction under a clear schema, and quick checks.
- Terra handles ambiguous analysis, architecture relations, code authoring, and file changes.
- Sol manages the cycle, communicates with the user, and makes final decisions.

A Reader usually starts on Luna. Route an ambiguous region, cross-file inference, or design decision to Terra. Choose reasoning effort for the concrete region and increase it after the first pass when justified.

## 12. Git as memory

Git:

- stores earlier compacted states;
- shows semantic memory changes for a stage;
- supports branches for parallel directions;
- enables recovery without permanent archive copies.

Git must not store:

- the complete chat;
- raw copies of large sources;
- every subagent message;
- `tmp/` content;
- secrets or private tokens.

Validated local memory commits and exact-cycle pruning form one automatic internal transaction unless the user forbids it. Commits outside the selected PCW memory repository and every push require explicit authorization. A checkpoint message describes the semantic memory change, not a session number.

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
│           │           └── pcw-*.md
│           └── pcw-run/
│               ├── SKILL.md
│               └── agents/openai.yaml
└── tests/
    ├── fixtures/
    └── test_contracts.py
```

Exactly two public skills exist: `pcw` and `pcw-run`. Shared invariants and internal operation references live under `pcw/references/`; technical operations are not registered as skills.

## 14. Implementation phases

### Phase A. Formats and invariants

- define linked durable knowledge as the only system memory;
- define persistent task-specific Current and its budget;
- define tmp recovery and exact-cycle pruning;
- define subproject and cycle identifiers;
- establish link, status, and Git rules.

### Phase B. Natural-language interface and isolation

- expose only explicit `$pcw` and `$pcw-run` skills;
- accept natural-language requests without positional arguments or fixed verbs;
- keep all technical operations outside the registered skill set;
- require a clean Controller for execution;
- permit bounded question-driven run-time retrieval from Current links while preventing independent replanning;
- load internal operation references through exact verified paths.

### Phase C. Narrow memory operations

- create `pcw-resolve-workspace` and `pcw-open-cycle`;
- create read-only `pcw-query-context`;
- create `pcw-record-result`;
- create `pcw-promote-knowledge`;
- create `pcw-compact-current`;
- create read-only `pcw-validate-memory`;
- create `pcw-checkpoint-memory` and `pcw-prune-tmp`;
- disable implicit invocation for both public skills;
- verify each operation's idempotency;
- verify recovery after failure between every pair of transitions.

Implement reliable memory updates before complete source analysis; otherwise results become another growing archive.

### Phase D. Sources and agents

- create read-only `pcw-inspect-source`;
- create conditional `pcw-map-source`;
- define two-stage adaptive partitioning;
- establish Reader, Controller, and Worker result contracts;
- add Luna/Terra routing;
- verify a small file, a large mixed-format file, a source-code project, and clean-context execution.

### Phase E. Long-running scenarios

- run at least 30 consecutive cycles on a test subproject;
- measure growth of `current.md`, `knowledge/`, and Git;
- refine and replace Current across sessions;
- recover interrupted context updates and runs;
- verify a parallel branch and later knowledge merge;
- verify transfer to another agent environment.

## 15. MVP acceptance criteria

The MVP is ready when:

- a new session creates or refines Current without the complete chat;
- a clean Controller executes from Current without inherited conversation and receives only compact results from bounded knowledge and source retrieval;
- missing task context produces `context_insufficient` instead of improvisation;
- active user constraints survive repeated compaction;
- `current.md` remains bounded and task-specific after dozens of cycles;
- detail is retrievable through links and `rg`;
- unconfirmed material never becomes fact;
- interrupted `tmp/` cycles recover safely and completed cycles do not accumulate;
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

Until measured evidence requires more, keep two natural-language skills, one linked durable knowledge layer, one persistent task-specific Current, one recoverable transaction buffer, and Git.

# Persistent Context Workspace

Persistent Context Workspace is an experimental file-backed memory and execution boundary for long-running agent work. Version 0.2.1 exposes two explicit skills. Everything after either skill is interpreted as natural language; paths, context identity, scope, constraints, and requested meaning may appear in any order.

## Install from GitHub

```bash
codex plugin marketplace add pikiby/persistent-context-workspace --ref main
codex plugin add persistent-context-workspace@persistent-context-workspace
```

Start a new Codex thread after installation.

## User interface

### Build or refine context

```text
$pcw Create context for the project at /path/to/project. Record its architecture and prepare a plan for fixing the validator.
```

```text
$pcw In the validator context, keep the existing task but add that the virtual machine is reachable only through VPN and narrow the plan to Debezium.
```

`$pcw` creates a missing context when the request clearly asks for one, or updates an existing context. It maintains linked durable knowledge and builds `current.md`: a compact task root containing a Task lock with the verbatim request, required outcome, explicit scope and exclusions, authority, critical constraints, and unresolved choices. Stable detail remains linked in knowledge. `$pcw` may inspect named source material read-only, but it never executes the prepared task or changes the source project.

Source facts do not expand the task. PCW distinguishes exact `user` meaning, evidenced in-scope `derived` implementation steps, supporting `fact` material, and `unresolved` inference. A discovered manifest, prerequisite, adjacent defect, best practice, or infrastructure component stays supporting or out of scope unless the user requested it or primary evidence proves it strictly necessary inside the locked outcome.

The user can refine, replace, or close Current through later natural-language `$pcw` requests. No positional arguments, fixed verbs, or mandatory request order are required.

### Execute prepared context

```text
$pcw-run Run the prepared validator task in the data-platform context.
```

`$pcw-run` starts a clean Controller with no inherited conversation. The Controller reads the complete prepared `current.md` first, receives only the current run request, exact paths, linked knowledge, source coordinates, and current authority, and then performs the task itself or delegates bounded work.

For missing supporting detail, the Controller gives one Reader one exact question. That Reader starts from Current's knowledge links, follows only relevant relations and primary coordinates, classifies each finding as required, supporting, out of scope, or unresolved, and may recursively delegate bounded subquestions. The Controller receives one compact merged result; raw child reports remain in `tmp/`. Retrieval cannot change the prepared task, scope, exclusions, authority, constraints, audience, deliverables, or quality criteria. If those task-defining meanings or a required fact remain insufficient, the run returns a blocker so the user can refine Current with `$pcw`.

Before any final result is recorded, the Controller maps every material change or output section to the Task lock. The primary agent then reads the complete changed target and performs semantic acceptance against that lock. Mechanical checks cannot replace this review. An unmapped or out-of-scope addition blocks promotion, checkpoint, pruning, and completion; the same clean Controller repairs the result, or the user supplies missing meaning.

## Memory model

Each semantic subproject uses:

```text
<work-root>/.pcw/<subproject>/
├── current.md
├── knowledge/
├── tmp/
└── .gitignore
```

- `knowledge/` is the only durable system memory. It contains compact source-backed objects, facts, rules, constraints, blockers, decisions, relations, and primary coordinates.
- `current.md` is the persistent compact root of one active task. It preserves the user's Task lock directly and links supporting detail for bounded retrieval.
- `tmp/` is not another memory layer. It is the ignored raw transaction buffer for one active or interrupted `$pcw` or `$pcw-run` operation: findings, maps, Controller and Worker results, receipts, promotion input, and the pre-change Current snapshot. After validated results are absorbed, only that exact cycle directory is removed; the empty `tmp/` directory remains for future operations.

Each subproject memory is a local Git repository. A semantically accepted and validated memory checkpoint and exact-cycle cleanup are automatic unless the user explicitly forbids that memory transaction. Source-repository commits and every push still require normal explicit authorization.

## Update plugin

```bash
codex plugin marketplace upgrade persistent-context-workspace
codex plugin add persistent-context-workspace@persistent-context-workspace
```

Start a new thread so Codex loads the refreshed skill definitions.

## Plugin structure

```text
plugins/persistent-context-workspace/
├── .codex-plugin/plugin.json
└── skills/
    ├── pcw/
    │   ├── SKILL.md
    │   ├── agents/openai.yaml
    │   └── references/
    │       ├── workspace-contract.md
    │       ├── state-machine.md
    │       ├── agent-routing.md
    │       └── operations/
    └── pcw-run/
        ├── SKILL.md
        └── agents/openai.yaml
```

Only `pcw` and `pcw-run` are registered as skills. Technical state transitions are Markdown reference contracts under `pcw/references/operations/`, so they do not appear as separate user commands.

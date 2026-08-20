# Persistent Context Workspace

Persistent Context Workspace is an experimental file-backed memory and execution boundary for long-running agent work. Version 0.2.0 exposes two explicit skills. Everything after either skill is interpreted as natural language; paths, context identity, scope, constraints, and requested meaning may appear in any order.

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

`$pcw` creates a missing context when the request clearly asks for one, or updates an existing context. It maintains linked durable knowledge and builds `current.md`: a compressed, self-contained context and plan for one task. It may inspect named source material read-only, but it never executes the prepared task or changes the source project.

The user can refine, replace, or close Current through later natural-language `$pcw` requests. No positional arguments, fixed verbs, or mandatory request order are required.

### Execute prepared context

```text
$pcw-run Run the prepared validator task in the data-platform context.
```

`$pcw-run` starts a clean Controller with no inherited conversation. The Controller reads the complete prepared `current.md` first, receives only the current run request, exact paths, source coordinates, and current authority, and then performs the task itself or delegates bounded work to Workers.

The Controller does not search `knowledge/` to repair an incomplete Current and does not use earlier chat. If Current is insufficient or does not cover the requested run, it returns a blocker so the user can refine it with `$pcw`. A run may record verified results in knowledge and update only factual execution state in Current; it cannot independently change the task, scope, constraints, or plan.

## Memory model

Each semantic subproject uses:

```text
<work-root>/.pcw/<subproject>/
├── current.md
├── knowledge/
├── tmp/
└── .gitignore
```

- `knowledge/` is the only durable system memory. It contains linked objects, facts, rules, constraints, blockers, decisions, and relations.
- `current.md` is a persistent task-specific compression of only the knowledge and evidence required to perform one active task. It remains available for user refinement and recovery after a run.
- `tmp/` is not another memory layer. It is the ignored raw transaction buffer for one active or interrupted `$pcw` or `$pcw-run` operation: findings, maps, Controller and Worker results, receipts, promotion input, and the pre-change Current snapshot. After validated results are absorbed, only that exact cycle directory is removed; the empty `tmp/` directory remains for future operations.

Each subproject memory is a local Git repository. A validated memory checkpoint and exact-cycle cleanup are automatic unless the user explicitly forbids that memory transaction. Source-repository commits and every push still require normal explicit authorization.

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

# Persistent Context Workspace

Persistent Context Workspace is an experimental file-backed memory and execution boundary for long-running agent work. Version 0.3.0 exposes two explicit skills. Everything after either skill is interpreted as natural language; paths, context identity, scope, constraints, and requested meaning may appear in any order.

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

`$pcw` is deliberately direct. It reads the relevant Current and knowledge, optionally gathers bounded read-only evidence, edits the durable owner of each requested meaning, and creates the local memory checkpoint. A refinement replaces equivalent active wording instead of appending message history, and it changes knowledge only when the user actually asks to retain durable cross-task meaning.

### Execute prepared context

```text
$pcw-run Run the prepared validator task in the data-platform context.
```

`$pcw-run` starts a clean Controller with no inherited conversation. The Controller reads the complete prepared `current.md` first, receives only the current run request, exact paths, linked knowledge, source coordinates, and current authority, and then performs the task itself or delegates bounded work.

For missing supporting detail, the Controller gives one Reader one exact question. That Reader starts from Current's knowledge links, follows only relevant relations and primary coordinates, classifies each finding as required, supporting, out of scope, or unresolved, and may recursively delegate bounded subquestions. The Controller receives one compact merged result directly; child reports are not written to a separate buffer. Retrieval cannot change the prepared task, scope, exclusions, authority, constraints, audience, deliverables, or quality criteria. If those task-defining meanings or a required fact remain insufficient, the run returns a blocker so the user can refine Current with `$pcw`.

The Controller performs only the locked task and writes durable knowledge and factual execution state directly to memory. The primary agent relays its compact result to the user. Neither skill adds a mandatory validation, result rereading, or semantic-acceptance stage. Tests and other checks run only when they are part of the user's task, not automatically because PCW was invoked. Attribution and task boundaries remain rules for producing content, not a separate review workflow.

## Required instructions

The plugin defines the required reading in advance: shared memory rules, a separate procedure for each skill, and the specified operation and Reader references. Every required document is read in full. The agent does not decide which required sections to skip.

`pcw/references/workspace-contract.md` contains shared memory, provenance, scope, and authority rules. `pcw/references/state-machine.md` describes only context editing. `pcw-run/references/state-machine.md` contains execution and clean-Controller rules, which `$pcw` does not load. Shared Reader routing contains only bounded source-retrieval rules.

## Memory model

Each semantic subproject uses:

```text
<work-root>/.pcw/<subproject>/
├── current.md
└── knowledge/
```

- `knowledge/` is the only durable system memory. It contains compact source-backed objects, facts, rules, constraints, blockers, decisions, relations, and primary coordinates.
- `current.md` is the persistent compact root of one active task. It preserves the user's Task lock directly and links supporting detail for bounded retrieval.

Neither skill uses `tmp/`, cycles, manifests, intermediate result files, receipts, promotion files, snapshots, or pruning. No replacement journal or temporary memory directory is introduced.

Each subproject memory is a local Git repository. A local memory checkpoint is automatic unless the user explicitly forbids it. Source-repository commits and every push still require normal explicit authorization. After interruption, saved commits and any remaining file changes are available, but there is no record of the exact execution stage and no guarantee of automatic recovery or rollback.

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
        ├── agents/openai.yaml
        └── references/state-machine.md
```

Only `pcw` and `pcw-run` are registered as skills. Four internal Markdown operation references remain under `pcw/references/operations/`: workspace selection, context retrieval, source inspection, and local memory checkpointing. They do not appear as separate user commands.

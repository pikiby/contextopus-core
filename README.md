# Persistent Context Workspace

Persistent Context Workspace is an experimental file-backed memory layer for long-running agent work. The explicit `$pcw` interface retrieves, records, uses, or reconciles one named `.pcw/<subproject>/`; an internal orchestration contract coordinates narrow operations over `current.md`, `tmp/`, `knowledge/`, and Git history.

The repository is also a Codex plugin marketplace, so the complete skill set can be installed and refreshed as one unit.

## Install from GitHub

Add this repository as a marketplace, then install the plugin:

```bash
codex plugin marketplace add pikiby/persistent-context-workspace --ref main
codex plugin add persistent-context-workspace@persistent-context-workspace
```

Start a new Codex thread after installation. All PCW behavior is explicit:

```text
$pcw ask <subproject> <question>
$pcw remember <subproject> <statement>
$pcw do <subproject> <task>
$pcw sync <subproject> [scope]
```

`ask` is read-only. `remember` changes memory only. `do` loads a visible context packet before performing and recording the task. `sync` reconciles memory with a named source through read-only inspection. PCW does not activate for ordinary prompts.

## Update

Refresh the Git marketplace snapshot and reinstall the plugin:

```bash
codex plugin marketplace upgrade persistent-context-workspace
codex plugin add persistent-context-workspace@persistent-context-workspace
```

Start a new thread so the refreshed skill definitions are loaded.

## Local development

Register a checkout as a local marketplace:

```bash
codex plugin marketplace add /absolute/path/to/persistent-context-workspace
codex plugin add persistent-context-workspace@persistent-context-workspace
```

The `$pcw` skill loads the internal orchestration contract from its verified sibling path. That contract loads each narrow operation through `<plugin-skills-root>/<pcw-name>/SKILL.md`, verifies path containment and frontmatter identity, and executes it in the current agent context. It does not depend on a generated `$pcw-*` invocation being recognized as a new skill call.

## Repository layout

```text
persistent-context-workspace/
├── .agents/plugins/marketplace.json
├── plugins/persistent-context-workspace/
│   ├── .codex-plugin/plugin.json
│   └── skills/
│       ├── pcw/
│       ├── persistent-context-workspace/
│       ├── pcw-query-context/
│       └── pcw-*/
├── PLAN.md
└── tests/
```

- `pcw` is the only user-facing skill and has implicit invocation disabled.
- `persistent-context-workspace` is the internal orchestration contract.
- `pcw-*` skills are narrow, repeatable internal operations.
- `PLAN.md` is the architecture and implementation plan.
- `tests/` verifies the plugin, skill contracts, loader rules, and memory fixtures.

No separate runtime or project-specific CLI is required. The skills use the host agent's ordinary file, search, Git, and delegation tools.

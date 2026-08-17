# Persistent Context Workspace

Persistent Context Workspace is an experimental file-backed memory layer for long-running agent work. One public contract skill coordinates small internal skills and preserves continuity in `.rlm/<subproject>/` through `current.md`, `tmp/`, `knowledge/`, and Git history.

The repository is also a Codex plugin marketplace, so the complete skill set can be installed and refreshed as one unit.

## Install from GitHub

Add this repository as a marketplace, then install the plugin:

```bash
codex plugin marketplace add pikiby/persistent-context-workspace --ref main
codex plugin add persistent-context-workspace@persistent-context-workspace
```

Start a new Codex thread after installation. Invoke only `$persistent-context-workspace`; its internal `pcw-*` skills are implementation details and have implicit invocation disabled.

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

The main skill loads an internal operation by resolving and reading the exact sibling path `<plugin-skills-root>/<pcw-name>/SKILL.md`. It verifies path containment and the frontmatter name before executing the contract. It does not depend on a generated `$pcw-*` invocation being recognized as a new skill call.

## Repository layout

```text
persistent-context-workspace/
├── .agents/plugins/marketplace.json
├── plugins/persistent-context-workspace/
│   ├── .codex-plugin/plugin.json
│   └── skills/
│       ├── persistent-context-workspace/
│       └── pcw-*/
├── PLAN.md
└── tests/
```

- `persistent-context-workspace` is the only user-facing skill.
- `pcw-*` skills are narrow, repeatable internal operations.
- `PLAN.md` is the architecture and implementation plan.
- `tests/` verifies the plugin, skill contracts, loader rules, and memory fixtures.

No separate runtime or project-specific CLI is required. The skills use the host agent's ordinary file, search, Git, and delegation tools.

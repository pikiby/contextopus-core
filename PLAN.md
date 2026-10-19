# Contextopus development scope

The independent repository layout is under development and has not been released.
Core owns the shared runtime, model/RAG, storage coordination, module lifecycle,
MCP/CLI/TUI, client adapters and generic examples. Optional module source, domain
tests and artifacts belong to their respective repositories.

- [Current build and verification](docs/development.md)
- [Core architecture](docs/architecture.md)
- [Module standard](docs/modules.md)
- [Workspace](https://github.com/pikiby/contextopus-workspace)
- [Session Search](https://github.com/pikiby/contextopus-session-search)
- [Historical implementation plan](docs/plans/legacy-implementation.md)

Published release evidence, a source candidate and an installed result have
separate verification boundaries. Updating a live root, changing release
versions and publishing artifacts require their own scoped work.

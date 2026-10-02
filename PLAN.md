# PCW implementation

Version 0.11.2 implements the [v3 design](docs/context-workspace-design-v3.md).

The complete ordered work is tracked in [the upgrade plan](docs/context-workspace-upgrade-plan.md). Its execution procedure is [the goal](docs/context-workspace-upgrade-goal.md); API details are in [the contracts](docs/context-workspace-v3-contracts.md).

- Separate explicit creation from opening and reading existing contexts.
- Version and migrate recognized storage with preflight, preserved unfinished work and verified workspace/control snapshots.
- Keep instructions, project goals, independent task state, knowledge and temporary work separate.
- Support independent search and independent invocation/approval settings.
- Preserve semantic topics and labelled links; make the body token limit optional.
- Keep exact local permanent history and a separate observed-operation journal.
- Route creation, search, instructions, upgrade, audit and rework through scoped skills.
- Verify storage, permissions, errors, concurrency and full workflows before claiming completion.

Publishing, installation and host-session refresh are separate actions. A source candidate is not a published or installed release. Deterministic tests establish tool behavior, not universal model compliance.

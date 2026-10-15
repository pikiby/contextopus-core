# PCW implementation

Version 0.14.0 implements the [v4 design](docs/context-workspace-design-v4.md), extending the previous v3 work below.

- Share the RAG and analytical databases under the chosen memory root while retaining separate context files and rules.
- Filter one, several or all categories before vector top-N; cross-context reading never switches active instructions.
- Store stable IDs in YAML and use descriptive renameable knowledge filenames.
- Generalize required sources to references and bounded retrieval instructions, checked on every receipt.
- Route incompatible contexts immediately to migration; migrate cards and vectors together with recoverable snapshots and retained unfinished proposals.

The complete ordered work is tracked in [the upgrade plan](docs/context-workspace-upgrade-plan.md). Its execution procedure is [the goal](docs/context-workspace-upgrade-goal.md); API details are in [the contracts](docs/context-workspace-v3-contracts.md).

- Separate explicit creation from opening and reading existing contexts.
- Version and migrate recognized storage with preflight, preserved unfinished work and verified workspace/control snapshots.
- Keep instructions, project goals, independent task state, knowledge and temporary work separate.
- Support independent search and independent invocation/approval settings.
- Preserve semantic topics and labelled links; make the body token limit optional.
- Keep exact local permanent history and a separate observed-operation journal.
- Route creation, search, instruction editing, upgrade, audit, rework and usage analysis through scoped action-named skills.
- Ask about required-source authoring at creation; store the chosen rule in INSTRUCTIONS and freshly consult every marked source whenever its material is received.
- Expose operations through two MCP entrypoints with on-demand schemas and validated read/change routing.
- Verify storage, permissions, errors, concurrency and full workflows before claiming completion.

Publishing, installation and host-session refresh are separate actions. A source candidate is not a published or installed release. Deterministic tests establish tool behavior, not universal model compliance.

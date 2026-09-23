# PCW implementation

Version 0.10.0 implements the [INSTRUCTIONS.md design](docs/context-workspace-design-v2.md), configurable knowledge approval and explicit context selection.

- Keep project guidance in persistent INSTRUCTIONS.md with a single bootstrap template.
- Return its complete text at startup; the main skill must read and follow it before context retrieval and work.
- Store task state and results as temporary Markdown without the old five-field Current contract.
- Route direct instructions-edit requests to the dedicated pcw-instructions skill and read/prepare/apply tools.
- Route explicit context-creation requests to pcw-create; resolve placement and task with the user. Require an unambiguous user instruction to create or switch context, and ask when selection is unclear.
- Use INSTRUCTIONS.md to configure knowledge approval, initially disabled; always present changes and require approval for instructions edits. Preserve revision conflicts, temporary-data isolation, indexing and knowledge review.
- Keep project policies out of duplicate skill/MCP instructions; the instruction-edit procedure has one skill definition.
- Verify persistence, free Markdown, approval boundaries, conflicts, interrupted writes, cleanup and standard-MCP contracts.

Publishing, installation and host-session refresh are separate actions. Deterministic tests establish tool behavior, not universal model compliance.

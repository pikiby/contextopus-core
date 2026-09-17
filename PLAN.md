# PCW implementation

Version 0.8.0 implements the memory-only cycle in [the governing document](docs/context-workspace-design.md).

- Primary-owned knowledge, Current and exact navigation links.
- Direct work with optional delegation, without environment discovery or an assignment controller.
- Whole-text saves, automatic token windows with overlap and Qwen embeddings by default.
- Configurable local/API embedding sources with compatible tokenizers.
- Revision-checked indexing, pending retry, atomic profile switching and legacy index recovery.
- Preserved compaction, path safety and explicitly authorized memory Git operations.

Verification and limitations are recorded in `docs/context-memory-assessment.md`. Historical release assessments remain evidence for their stated versions, not proof of current behavior.

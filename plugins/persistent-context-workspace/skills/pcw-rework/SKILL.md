---
name: pcw-rework
description: Deliberately transform existing PCW knowledge as requested, such as removing a class of information, making topics compact, retaining relationships or clarifying them.
---

# Rework knowledge

Use the two [MCP entrypoints](../pcw/SKILL.md#mcp-calls): `pcw_query` for reads and `pcw_execute` for changes. The names below are operations; place their parameters in `arguments`. Describe only an unknown signature.

1. Establish the requested transformation and scope. Follow [context selection](../pcw/SKILL.md#context-selection), start `purpose: rework`, read INSTRUCTIONS and PROJECT, and create/resume task Current. Editing instructions alone does not authorize rewriting knowledge.
2. Enumerate all materials in scope with paginated `list`. A request affecting "all" cannot be satisfied from search top-N. Search helps locate related topics; read affected complete bodies and inspect incoming/outgoing links. Verify material revisions when using an earlier audit.
   On every receipt of a material with `required_sources`, follow the [required-source procedure](../pcw/references/required-sources.md); earlier checks never substitute.
3. Prepare final text and relationships according to the requested transformation and current instructions. For a split, decide the original ID's fate and new topics together. For deletion/merge include replacements so incoming links are reviewed. Retain conditions and provenance, including relevant required-source blocks. Research missing mechanisms only through allowed sources; do not invent them.
4. Keep work in tmp, update Current, and prepare a coherent change using `proposal_prepare`. If it exceeds one operation's capacity, use explicit dependency-ordered batches and report remaining scope. Do not claim partial scope is complete. `needs_split` reports the configured token limit, not a semantic diagnosis.
5. Follow the main cycle's review, exact chat presentation, approval/apply and finish steps. Show removals as well as additions. A no-change conclusion still needs result review. Report indexing and Git states; do not rewrite instructions as a side effect.

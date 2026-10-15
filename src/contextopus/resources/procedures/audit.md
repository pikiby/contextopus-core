This is the canonical audit procedure. Use Contextopus MCP, not direct runtime writes. Workspace operations accept the legacy names below; prefer `workspace.<operation>`. Resolve the selected work_root and workspace explicitly. Fetch a referenced procedure with `procedure(name=...)`; fetch a reference with `procedure(name="reference/<name>")`.


# Audit context

Use the two [MCP entrypoints](procedure:workspace#mcp-calls): `contextopus_query` for reads and `contextopus_execute` for changes. The names below are operations; place their parameters in `arguments`. Describe only an unknown signature.

1. Establish scope and follow [context selection](procedure:workspace#context-selection). Read INSTRUCTIONS and the project record independently. An audit needs no work cycle; if one is useful, use `purpose: audit`.
2. Use `audit` for structural checks. For an entire-context request page through all results and `list`; vector top-N is insufficient. Read necessary complete materials and selected links. Opening must not migrate, repair indexing or rewrite them.
   On every receipt of a material with `sources` (or legacy `required_sources`), follow the [required-source procedure](procedure:reference/required-sources); earlier checks never substitute.
3. Assess requested semantic issues against current instructions and sources: mixed questions, redundant claims, contradictions, unsupported claims or unnecessary detail. Distinguish observed errors from hypotheses requiring evidence. A large file alone does not prove mixed meaning.
4. For every finding show material/title, exact revision, concrete fragment, problem and its basis. Include a related material or rule when applicable. State scope and unresolved evidence. Do not claim a model judgment is a deterministic check.
5. Present the report in chat. If an audit cycle was opened, finish it after reporting without a knowledge proposal. Audit does not authorize fixes, rule changes or permanent retention of the report. Rework starts only when requested.

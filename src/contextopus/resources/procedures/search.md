This is the canonical search procedure. Use Contextopus MCP, not direct runtime writes. Workspace operations accept the legacy names below; prefer `workspace.<operation>`. Resolve the selected work_root and workspace explicitly. Fetch a referenced procedure with `procedure(name=...)`; fetch a reference with `procedure(name="reference/<name>")`.


# Search context

Use the two [MCP entrypoints](procedure:workspace#mcp-calls): `contextopus_query` for reads and `contextopus_execute` for changes. The names below are operations; place their parameters in `arguments`. Describe only an unknown signature.

1. Follow [context selection](procedure:workspace#context-selection). Ask if the intended context is unclear; independent reading does not authorize creation or switching.
2. Read `instructions_read` and `project_read`. Follow the current rules; chat does not replace Contextopus reading.
3. Query `search`, then read selected complete topics through `read/read_many`. Default scope is the selected context; use `categories` or `all_categories` when needed for the question. The filter precedes nearest-result selection. Keep the original context's rules and write destination when reading another category. Use returned titles and descriptions to select useful links. For an actual linked read supply `from_id` if useful for tracing. Do not load all neighbors automatically.
4. On every receipt of a material with `sources` (or legacy `required_sources`), follow [required-source reading](procedure:reference/required-sources). Check each reference anew according to its bounded instruction, even after earlier checks and even when creation of new source links is disabled. Use facts within their conditions and verification limits. Missing, outdated or pending-index information is not evidence of absence. On format incompatibility, immediately route to upgrade and resume retrieval after success; no new migration request is needed.

## Choosing the selection

Start with the context's inherited `selection`; inspect returned diagnostics before adjusting it. `core.algorithms` returns current descriptions, parameter schemas, defaults and guidance by name. With `semantic:true` it searches their indexed descriptions using a fixed selector; `core.algorithms_refresh` explicitly refreshes that derived catalog after installation or a provider update. Catalog discovery never changes context selection.

For an incomplete answer, distinguish a wrong scope, a low technical candidate limit, a relevance cutoff and missing indexed knowledge. Change only the relevant parameter or algorithm, explaining the observed reason. A large rejected tail does not by itself justify loading it. Use `selection:{algorithm,parameters}` for one request; persistent changes use a scoped settings preview/apply. Changing algorithms starts from that algorithm's own parameters. `output:fragments` returns matching parts; materials remain available through normal read. `none` removes the relevance cutoff but retains eligibility and pagination. Explicit `candidate_limit` bounds retrieval and is reported separately from result size.

Use `core.index_stats` with module/collection to count indexed objects and fragments without reading vectors. Supply a short `purpose` and known `task_id` when helpful for later analysis; do not invent task or session identity. Diagnostics show candidate scope, counts, boundary, settings origins and incompleteness. A small result set is not proof of high quality. Analyze a search episode through the analyze procedure when requested; ordinary retrieval does not trigger a full audit.

Omit `cycle_id`. Do not call startup, tmp, proposal, apply or finish for a lookup. The plugin may journal the observed calls; reading creates no knowledge-write obligation. If work or an independently permitted update is needed, route it through the main cycle and current settings.

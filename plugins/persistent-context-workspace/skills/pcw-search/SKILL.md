---
name: pcw-search
description: Retrieve relevant knowledge from an already selected PCW context whenever useful, without starting a work cycle, creating tmp or requiring a memory update.
---

# Search context

Use the two [MCP entrypoints](../pcw/SKILL.md#mcp-calls): `pcw_query` for reads and `pcw_execute` for changes. The names below are operations; place their parameters in `arguments`. Describe only an unknown signature.

1. Follow [context selection](../pcw/SKILL.md#context-selection). Ask if the intended context is unclear; independent reading does not authorize creation or switching.
2. Read `instructions_read` and `project_read`. Follow the current rules; chat does not replace PCW reading.
3. Query `search`, then read selected complete topics through `read/read_many`. Use returned titles and descriptions to select useful links. For an actual linked read supply `from_id` if useful for tracing. Do not load all neighbors automatically.
4. On every receipt of a material with `required_sources`, follow [required-source reading](../pcw/references/required-sources.md). Check each source anew for its specified question, even after earlier checks and even when creation of new source links is disabled. Use facts within their conditions and verification limits. Missing, outdated or pending-index information is not evidence of absence. A needed migration or repair is a separate authorized operation.

Omit `cycle_id`. Do not call startup, tmp, proposal, apply or finish for a lookup. The plugin may journal the observed calls; reading creates no knowledge-write obligation. If work or an independently permitted update is needed, route it through the main cycle and current settings.

---
name: pcw-search
description: Retrieve relevant knowledge from an already selected PCW context whenever useful, without starting a work cycle, creating tmp or requiring a memory update.
---

# Search context

1. Follow [context selection](../pcw/SKILL.md#context-selection). Ask if the intended context is unclear; independent reading does not authorize creation or switching.
2. Read `pcw_instructions_read` and `pcw_project_read`. Follow the current rules; chat does not replace PCW reading.
3. Query `pcw_search`, then read selected complete topics through `pcw_read/read_many`. Use returned titles and descriptions to select useful links. For an actual linked read supply `from_id` if useful for tracing. Do not load all neighbors automatically.
4. Use facts within their conditions and verification limits. Missing, outdated or pending-index information is not evidence of absence. A needed migration or repair is a separate authorized operation.

Omit `cycle_id`. Do not call startup, tmp, proposal, apply or finish for a lookup. The plugin may journal the observed calls; reading creates no knowledge-write obligation. If work or an independently permitted update is needed, route it through the main cycle and current settings.

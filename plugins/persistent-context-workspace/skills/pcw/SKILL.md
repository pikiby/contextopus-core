---
name: pcw
description: Maintain and use a Persistent Context Workspace from a natural-language request. Use only when the user explicitly invokes $pcw to prepare context, retain knowledge, or execute or continue a task using that memory.
---

# PCW

PCW is the primary agent's working memory. The primary reads and changes knowledge, Current, links and authorized memory history through MCP. It may investigate, change and verify allowed sources directly, or delegate optionally. PCW does not discover the agent environment, publish model maps, register assignments or control workers.

## Context first

Call `pcw_startup` for the selected work root and workspace. Recover the five Current fields and pending memory operations. Missing knowledge is a recovery problem, not an empty successful workspace. For missing MCP/runtime components, read [Setup](references/setup.md).

Before external investigation, search accumulated knowledge with `pcw_search`, read relevant whole topic materials through `pcw_read` or `pcw_read_many`, and follow only useful links. Avoid rereading unchanged facts already in context. If memory is empty or insufficient, proceed to allowed sources. Search absence does not prove absence of facts.

## Work and retain knowledge

Perform the authorized work and verify its actual result. As useful findings emerge, save them using `pcw_create` or `pcw_update`; do not postpone all memory updates until the end of a long task. Supply ordinary complete Markdown for each independently useful topic. Keep facts, conditions, sources, uncertainty, tables and code. Do not create a giant multi-topic report merely because findings arrived together, or save operational receipts and duplicate external artifacts as knowledge.

The plugin generates filename-IDs, verifies disk writes, automatically splits token windows with overlap, embeds them and updates LanceDB. **Do not prepare fragment arrays, boundary positions, or a splitting subagent.** A successful receipt contains the saved revision and actual indexing status, not a repeated full document. Read again for meaning or uncertain results, not routinely after a verified write.

Use exact-ID links for useful navigation. Correct known incorrect text, consolidate genuine duplication, and preserve useful conditions and differences. A linked correction does not fix an incorrect active body. See [Memory operations](references/memory-operations.md).

## Optional delegation

Give a worker a standalone assignment: objective, facts as text, allowed sources/actions, constraints, checks and what to return. Use a separate context without the primary conversation. Do not pass knowledge paths/IDs, Current, PCW state or memory-management instructions. Explicitly prohibit PCW tools and discovery, reading or changing of `.pcw` by any mechanism. This is an assignment restriction, not technical isolation. The worker returns findings; the primary decides and performs memory writes. No PCW registration or identity binding is needed.

## Indexing and completion

For saved-but-pending material, fix the reported dependency/provider/configuration problem and call `pcw_reconcile`. It processes saved text without resubmission. Status and startup are lightweight and do not load weights. See [Automatic indexing](references/prepare-search.md) and, when configuring a provider, [Embeddings](references/embeddings.md).

Update Current through `pcw_current_set` when the goal, constraints, completion condition, step or blocker actually changes; omitted fields remain unchanged. An empty blocker is `""`. No task registration or finish gate is required.

Compare actual work and memory status with the user's request. Report pending indexing or unverified outcomes honestly. Use `pcw_checkpoint` only with actual user authorization; preparing context does not authorize its future task, publication, installation, downloads or source commits.

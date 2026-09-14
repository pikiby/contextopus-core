---
name: pcw
description: Maintain and use a Persistent Context Workspace from a natural-language request. Use only when the user explicitly invokes $pcw to prepare context, retain knowledge, or execute or continue a task using that memory.
---

# PCW

Remain the user's collaborator and owner of knowledge content. Search and read memory yourself; delegate real-source investigation and authorized source changes to native subagents. Prepare-only requests end with the requested memory result. A saved task or a bare invocation does not authorize execution; an explicit execution request includes necessary preparation without another command.

## Working flow

First establish readiness yourself. If the bundled `pcw` tools are unavailable or setup has not been verified, read [Runtime setup](references/setup.md) and run the cheap bundled check before loading other references or delegating source work. Ask for any still-missing installation permission using the actual missing Python/packages and destination; after approval, repair the missing requirements and resume this task. Stop at a concrete blocker on refusal or failure. Before first local embedding use, distinguish local dependency readiness from model availability and obtain any still-missing download permission. This setup check belongs to the primary, without a source-investigation subagent or a generic web diagnosis.

1. Resolve one work root and semantic workspace from the request. Memory belongs at `<work-root>/.pcw/<workspace>/`. Reuse an unambiguous existing workspace; create one only when authorized by the request. For selection, creation, writes, or recovery, read [Memory operations](references/memory-operations.md).
2. Read `pcw_current_get` into your working context at task start or recovery. Use `pcw_status` to distinguish available memory and pending preparation. Keep the user's goal, constraints, and completion condition in focus.
3. Use `pcw_search` for a bounded selection and `pcw_read` to open full materials by ID. Follow useful IDs in `links`; stop when enough is known. Empty knowledge starts with source investigation. An empty search is not proof that knowledge is absent. Refine the query when needed; do not add a search-only agent or browse the entire graph.
4. When evidence or source changes are needed, read [Native assignments](references/native-assignments.md) and delegate a concrete bounded task. Pass relevant knowledge IDs so corrections can be returned precisely. Remain responsible for subsequent assignments and the user's result.
5. Incorporate accepted results and corrections into the affected knowledge yourself. Preserve conditions, version distinctions, sources, and uncertainty. Replace duplicated content instead of adding another summary. Extract a shared material only when total text and navigation overhead justify it; do not claim measured reading savings without observations. Choose links and explicit replacements yourself.
6. Use the memory tools for material changes. For new or changed content, read [Prepare search](references/prepare-search.md), start its native helper, and submit literal parts. A saved material with pending preparation is not yet fully indexed. Links-only edits and renames need no preparation.
7. Keep Current concise: update its working step or blocker when that changes; change task meaning only when the user's instruction changes. Checkpoint the exact request-owned durable paths unless the user forbids the local memory commit. Report actual results, unresolved preparation or failures, and the checkpoint when created.

Use [Embedding configuration](references/embeddings.md) only for connection setup, provider changes, threshold configuration, or embedding errors. Tool schemas are authoritative for arguments; the bundled MCP server is `pcw`. Runtime checks and a standalone handshake do not prove that this host has connected; follow the setup reference's recovery boundary when tools remain unavailable.

Do not create temporary process documents, raw subagent archives, or a replacement journal. Do not add routine semantic-validation, rereading-for-acceptance, or test phases to memory handling. Checks required by the actual source task still belong to that task. Source facts and agent proposals do not expand task authority.

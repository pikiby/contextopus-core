# Persistent Context Workspace

Version 0.8.0 is the primary agent's working memory: ordinary Markdown topic materials, exact links, compact Current and automatic token-window embeddings in LanceDB. The primary uses saved context first, performs work directly or delegates optionally, and retains useful new facts during work.

There is no environment discovery, model map, assignment registration, executor binding or splitting agent. See the [governing document](docs/context-workspace-design.md) and [release notes](CHANGELOG.md).

## Work cycle

1. Invoke `$pcw` with a work root, workspace and natural-language task.
2. `pcw_startup` returns Current and bounded memory status without loading model weights.
3. Search accumulated knowledge, read relevant whole topic files and needed links before investigating external sources.
4. Perform and verify authorized work directly or optionally delegate it. Workers get standalone facts and allowed task sources, no PCW access or memory coordinates.
5. Save useful facts and corrections through `pcw_create` / `pcw_update` as complete ordinary Markdown topic materials. The plugin generates filename-IDs and verifies disk writes.
6. The plugin automatically tokenizes saved text, forms overlapping windows, computes embeddings and updates LanceDB. No boundary arrays or second transfer of the body.
7. Check actual memory/index status and update Current when focus changes. Pending indexing uses `pcw_reconcile` after fixing the reported cause.

Knowledge remains authoritative when a tokenizer, embedding provider or index operation fails. A save returns the durable material ID and honest pending status, so retrying indexing does not create duplicate files. Topic organization, factual corrections, compaction and links remain primary judgments. Operational receipts do not become knowledge.

## Storage and search

```text
<work-root>/.pcw/<workspace>/
  current.md
  knowledge/<generated-id>.md
  .pcw-runtime/active.json
  .pcw-runtime/lancedb/
  .git/                         # only after an authorized memory checkpoint
```

The small adjacent `.pcw/.control/<workspace>/` retains storage-loss detection and ID reservations. Old control records are preserved for compatibility, not resumed as a task controller. Current's five fields can be updated directly.

Search returns bounded unique topic-material IDs, paths and distances. Read selected full bodies and useful exact-ID links. Windows select materials; they do not replace the source files. Links-only changes and moves preserve vectors. Merge redirects incoming links before deleting replaced materials.

## Embeddings and token windows

Default: local `Qwen/Qwen3-Embedding-0.6B`, pinned revision, 1024 dimensions, CPU. The local model and its tokenizer are reused. Windows default to 512 tokens with 64-token overlap; these are configurable engineering values, not an empirical quality optimum. Unicode characters and literal source bytes are preserved; windows may cross Markdown paragraphs, tables and code.

Alternative embedding sources: another `sentence-transformers` model, Ollama `/api/embed`, or an explicitly configured `/v1/embeddings` API. API keys are referenced through environment-variable names. Remote models require an explicitly compatible Hugging Face tokenizer or tiktoken encoding. No secret belongs in knowledge or Git, and no provider fallback occurs automatically.

`pcw_switch_embeddings` accepts complete provider/profile and search settings plus optional `chunking`. Model-space or chunking changes rebuild an inactive table, check source revisions, then activate it atomically. Errors retain the previous source and index. See [configuration](plugins/persistent-context-workspace/skills/pcw/references/embeddings.md).

## Upgrade from 0.7.x

This release intentionally removes the orchestration and manual segmentation MCP interfaces. Use a new host thread for the revised skill and tools. Existing knowledge, IDs, links and Current remain intact. Opening a legacy workspace replaces only the derived search table; `pcw_reconcile` automatically reindexes its saved materials. Legacy remote profiles need a compatible tokenizer configured first. Known incorrect old revisions remain excluded from search until corrected.

Installing does not migrate YAML UUIDs or rewrite knowledge. Explicit `pcw_migrate_legacy_ids` remains available. Missing workspace storage is reported for recovery rather than silently treated as new empty memory.

For the existing Git marketplace tracking this repository:

```bash
codex plugin marketplace upgrade persistent-context-workspace
codex plugin add persistent-context-workspace@persistent-context-workspace
```

Read [runtime setup](plugins/persistent-context-workspace/skills/pcw/references/setup.md) only for installation or observed dependency failures. Launching the plugin does not install packages, create a virtual environment, or download weights. A first authorized local embedding operation may need the selected model cache. Git checkpoints and external publication retain their own authorization requirements.

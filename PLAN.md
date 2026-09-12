# Persistent Context Workspace

Version 0.4.0 introduces one explicit `$pcw` skill and a local Python MCP runtime. This is the implementation plan for the approved LanceDB and Qwen3 embedding design. Record architecture changes here before implementation.

## Ownership and task authority

The primary agent remains the user's collaborator. It searches and reads knowledge, defines bounded assignments, accepts returned evidence, writes durable content, removes duplication, and chooses navigation links. Native subagents investigate real sources and make authorized source changes. They return results and corrections identified by the knowledge IDs supplied with their assignments.

A request to prepare or refine context authorizes memory work and necessary read-only investigation. It does not execute a task recorded in Current. An explicit execution or continuation request includes the necessary preparation; there is no second launch command or separate Controller.

A separate native helper divides supplied knowledge content into literal semantic parts for search. It does not inspect external files, summarize, infer missing facts, choose links, or compact knowledge. The Python runtime requests this preparation through tool results; the host agent starts the helper. Python does not spawn native agents.

## Memory and retrieval

One semantic workspace lives at `<work-root>/.pcw/<workspace>/`. Full Markdown knowledge materials remain authoritative. Every material has a permanent `id` and a `links` list of exact material IDs in YAML frontmatter. Filenames are mutable addresses. IDs are not recycled. Links provide navigation without relation types, confidence scores, or mirrored edges.

Current contains the task goal, constraints, completion condition, current step, and blocker. The primary reads it at task start or recovery. Task meaning changes when the user's instruction changes; the working step changes when the agent chooses its next action or encounters a different blocker. Current is not an event journal or a second copy of knowledge.

LanceDB stores each literal semantic part, its vector, material ID, and current path. Queries use the active embedding profile and return a bounded set of material IDs and paths. The primary opens whole materials by ID and follows relevant links until it has enough information. There is no search-only subagent.

The filter requests at most `N` nearest parts, removes distances above `d_max`, and computes the median of positive adjacent gaps. The first gap at least `max(min_jump, multiplier * median)` cuts the tail. Fewer than three surviving results or no positive gaps disables gap cutting. Material IDs are deduplicated after filtering. No plateau heuristic or full-collection response is added.

Initial numerical settings are provisional runtime defaults, not measured quality claims. Thresholds belong to the embedding profile and distance metric. Different queries can retrieve other candidates; an empty response does not prove knowledge is absent.

## Content updates and preparation

The primary incorporates accepted source results and discovered corrections into the affected materials. It preserves attribution, uncertainty, version distinctions, conditions, and exceptions. A duplicate should not become another summary alongside the original. Shared descriptions are extracted only when their total text, metadata, and navigation cost justify the split; storage savings do not establish retrieval savings.

Creation and content updates persist the primary's text before search preparation. Such materials are explicitly pending. The host obtains the exact content and revision, delegates literal semantic splitting in a clean native context, and submits the resulting text parts with the revision. The runtime checks exact ordered coverage and rejects stale or changed content. It computes embeddings and replaces only that material's rows. Pending preparation remains visible after a failure; stale search rows must not be presented as current.

A links-only edit updates frontmatter. A rename updates the material path. Neither calls the preparation helper or embedding model.

Mechanical merge and replacement operations accept primary-authored target content and explicit old-ID to target-ID mappings. They save targets, update incoming navigation by exact ID, preserve or explicitly replace outgoing links, remove duplicates and self-links, and only then remove replaced materials and rows. Partial semantic extraction does not imply global redirection. Deletion removes incoming links before deleting the material. The runtime never chooses semantic replacements from vector similarity.

## Embedding runtime

A persistent stdio MCP process loads local `Qwen/Qwen3-Embedding-0.6B` lazily through `sentence-transformers` and reuses it across requests. The profile pins the model revision, dimension, input formatting, normalization, and execution settings. Documents remain literal text; Qwen queries receive the profile's retrieval instruction.

A common adapter accepts a list of texts plus `document` or `query` purpose and returns ordered numerical vectors. Supported connections are local sentence-transformers, Ollama `/api/embed`, and an explicitly configured OpenAI-compatible `/v1/embeddings` endpoint. Credentials are environment references. Chat access does not provide embedding access or authorize paid calls.

Local input length is checked; Ollama receives `truncate: false`. Compatible HTTP providers have no universal non-truncation flag: their configured server contract must reject overflow, and the client cannot prove lack of truncation from a returned vector. Invalid vector counts, indexes, dimensions, and non-finite values fail explicitly. No provider fallback, fabricated vectors, or silent local truncation is allowed.

Changing vector compatibility rebuilds into an inactive table from stored literal parts without splitting again or changing knowledge. The new source, profile, thresholds, and table become active together after success. Failure retains the previous source and table. Only established computational compatibility permits connection-only changes without re-embedding; a matching model name or dimension is insufficient.

## History, maintenance, and deployment

Git records Current and knowledge history. Runtime configuration, LanceDB files, caches, credentials, and locks are excluded. Restoration and reconciliation make the active search representation match restored knowledge; missing or changed parts return to preparation instead of reusing stale vectors. Physical database cleanup is maintenance, not a requirement for every mutation. No separate seven-day index archive, source-checksum freshness scheme, daemon, or operation journal is introduced.

The plugin bundles the runtime, one skill, its conditional references, a stdio configuration, and a launcher. Dependencies are installed explicitly into an isolated environment. The launcher resolves a dedicated interpreter and imports the runtime from the active plugin copy, including installed cache copies. It never installs dependencies or downloads a model at process startup. The embedding model is obtained only on a subsequent embedding request under the selected connection policy.

Local memory checkpoints cover only the request's intended durable paths unless the user forbids them. Source commits and publishing remain separately authorized actions. Multi-file failures are reported with partial effects; Git does not undo external actions or recover lost agent context.

## Delivery and verification

1. Replace the two entry skills and legacy Controller instructions with one concise natural-language workflow and conditional references.
2. Implement durable material operations, ID navigation, Current, pending preparation, LanceDB search, provider switching, and Git checkpoints/restoration.
3. Package persistent stdio startup with actionable dependency failures and explicit isolated installation.
4. Verify runtime behavior with deterministic adapters and real local LanceDB. Verify adapters without external credentials or model downloads. Verify the actual stdio initialization and tool-list handshake.
5. Validate skill and plugin metadata and reconcile documentation against implemented tool signatures.

Contract checks cover packaged entrypoints and resolvable references. Runtime tests cover observable memory and search behavior rather than matching instruction wording. Adapter tests cover provider protocols and errors. Real Qwen retrieval quality, target-machine latency and memory use, and long-running multi-session behavior remain separate measurements until actually run.

Legacy memory is adopted explicitly: keep existing IDs and provenance, assign IDs to records that lack them, and convert filename-based navigation deliberately. New navigation metadata does not erase meaningful statements in legacy relation prose. A copied Markdown folder is not assumed to be already indexed.

The unresolved design question is how to discover stale knowledge that causes no visible difficulty. No universal automatic freshness guarantee is claimed.

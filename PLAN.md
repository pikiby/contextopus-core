# Persistent Context Workspace

Version 0.4.2 retains one explicit `$pcw` skill and a local Python MCP runtime, and uses portable plugin-path resolution for startup without requiring a virtual environment. This is the implementation plan for the approved LanceDB and Qwen3 embedding design. Record architecture changes here before implementation.

## Ownership and task authority

The primary agent remains the user's collaborator. It searches and reads knowledge, defines bounded assignments, accepts returned evidence, writes durable content, removes duplication, and chooses navigation links. Native subagents investigate real sources and make authorized source changes. They return results and corrections identified by the knowledge IDs supplied with their assignments.

A request to prepare or refine context authorizes memory work and necessary read-only investigation. It does not execute a task recorded in Current. An explicit execution or continuation request includes the necessary preparation; there is no second launch command or separate Controller.

The primary checks runtime readiness before loading task-specific references or delegating source work. Missing Python or dependencies trigger a concrete installation proposal and permission request unless the same installation is already authorized. After approval, install the missing requirements, repeat readiness checks, and continue the same user task. Refusal, denied execution, or an installation failure leaves an explicit blocker; it does not establish that memory or a checkpoint was saved.

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

The plugin bundles the runtime, one skill, its conditional references, the declared stdio MCP configuration, and a POSIX shell launcher. The shell accepts an explicit absolute `PCW_PYTHON` or selects `python3` from PATH; it can report missing Python without requiring Python to launch that diagnosis. Runtime code comes from the active plugin copy, including installed cache copies. Reusable dependencies may live in the selected interpreter or a private packages directory reported by readiness checks. That directory contains packages, not a Python environment. No virtual environment, system-package override, dependency installation, or model download is created automatically at startup.

The portable root `plugin.json` selects the supported plugin loader, and root `mcp.json` declares `sh` with `${PLUGIN_ROOT}/scripts/launch.sh` as one argument. Codex resolves the argument before launching the process. The compatibility `.codex-plugin/plugin.json` retains matching metadata but does not redeclare a legacy MCP transport. A shell expression that merely reads `PLUGIN_ROOT` or `CLAUDE_PLUGIN_ROOT` from an assumed environment is not the path-resolution mechanism.

Cheap readiness checks report the selected interpreter, required distributions, version compatibility, pip availability, and exact dependency installation target. Base readiness, local embedding dependencies, deeper imports, and model availability are separate results. Successful startup or dependency checks do not establish that model weights are cached. Before a first download, the primary discloses the selected model, cache destination, and download/storage/compute scope and obtains any still-missing permission.

Dependency repair and a standalone stdio handshake do not establish a live host connection. Retry through a supported host reload only when it is actually available, then verify the host exposes PCW tools. Otherwise preserve the task and its next action in the conversation and resume it after the current host session restarts; do not require a new assignment, fabricate an automatic reconnect, or add a second manual MCP registration.

Local memory checkpoints cover only the request's intended durable paths unless the user forbids them. Source commits and publishing remain separately authorized actions. Multi-file failures are reported with partial effects; Git does not undo external actions or recover lost agent context.

## Delivery and verification

1. Replace the two entry skills and legacy Controller instructions with one concise natural-language workflow and conditional references.
2. Implement durable material operations, ID navigation, Current, pending preparation, LanceDB search, provider switching, and Git checkpoints/restoration.
3. Package persistent stdio startup using existing Python, actionable readiness reports, and consent-based repair of missing dependencies without requiring a virtual environment.
4. Verify runtime behavior with deterministic adapters and real local LanceDB. Verify adapters without external credentials or model downloads. Verify standalone stdio separately from a fresh Codex-host thread that loads the installed plugin and calls PCW tools through Codex. Host tests must use Codex's resolved transport rather than manually injecting plugin-root variables. Exercise cached local Qwen in the opt-in release check without requesting a language-model turn.
5. Validate skill and plugin metadata and reconcile documentation against implemented tool signatures.

Contract checks cover packaged entrypoints and resolvable references. Startup checks exercise absent Python, missing dependencies, interpreter overrides, and installed paths containing spaces. Runtime tests cover observable memory and search behavior rather than matching instruction wording. Run the complete suite with pytest, which collects both unittest cases and the runtime's pytest functions. Adapter tests cover provider protocols and errors. Real Qwen retrieval quality, target-machine latency and memory use, and long-running multi-session behavior remain separate measurements until actually run.

Legacy memory is adopted explicitly: keep existing IDs and provenance, assign IDs to records that lack them, and convert filename-based navigation deliberately. New navigation metadata does not erase meaningful statements in legacy relation prose. A copied Markdown folder is not assumed to be already indexed.

The unresolved design question is how to discover stale knowledge that causes no visible difficulty. No universal automatic freshness guarantee is claimed.

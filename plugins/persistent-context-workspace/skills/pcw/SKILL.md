---
name: pcw
description: Maintain and use a Persistent Context Workspace from a natural-language request. Use only when the user explicitly invokes $pcw to prepare context, retain knowledge, or execute or continue a task using that memory.
---

# PCW

The primary talks with the user, decides scope, reads PCW memory, chooses native subagents, and accepts work. Native subagents inspect real sources, make authorized changes, check results, write Current and apply knowledge or Git changes. PCW does not dispatch subagents, run a Controller, or use hooks.

After MCP is available, use this short loop throughout the request:

1. Call `pcw_action_requirements` for the next action.
2. Act on its instructions and the user's authority. Before a native launch, obtain `prepare_assignment` with `ready: true` for the complete assignment; correct missing prerequisites and repeat the call when it is false.
3. Submit the result through the applicable MCP operation.
4. Call it again before the next action.

The four actions are `prepare_assignment`, `process_result`, `transition`, and `finish`. Read [action requirements](references/action-requirements.md) only through that MCP call immediately before acting. Try the exposed PCW tools first. If they are unavailable, follow [Runtime setup](references/setup.md) for bounded diagnostics and any authorized repair; do not insert diagnostics before working MCP calls merely because this is a new conversation. Start this loop when MCP is available. Startup recovery does not transfer model-map work to a subagent.

## Start and assign

Resolve one work root and workspace, then try `pcw_current_get` and `pcw_status`; successful calls establish that PCW MCP is available. Use [Runtime setup](references/setup.md) for unavailable tools or embedding prerequisites that still need checking. Use `pcw_search` and `pcw_read` yourself for existing memory. When knowledge is empty, skip search and assign any needed source research directly. A request to prepare context does not execute a saved task. Execution needs an explicit user request.

Before a native assignment, the primary itself uses native environment tools, descriptors, and necessary environment configuration to establish current available model/reasoning combinations. It records that snapshot with `pcw_environment_check`, itself gathers and compares the model information with roles, and itself builds, publishes, or refreshes the tools map with `pcw_tools_map_publish`. This is a limited primary responsibility; it is not real-source research delegated to a worker. Select an existing current profile. Do not assume a provider-wide ranking or a reasoning level. Give a prepared, bounded task to the smallest suitable discovered profile; justify a larger model or deeper reasoning from the profile, remaining uncertainty, task complexity, or the required check. State the chosen model and supported reasoning settings explicitly in the native launch.

Read [Native assignments](references/native-assignments.md) before delegating real-source investigation, implementation, Current, knowledge application, Git, or a factual check. Use a clean, prepared native context where the host supports it. PCW supplies context and durable-memory operations; it does not launch the agent.

## Receive, save, decide

The worker returns its own free-form Markdown findings, changes, sources, checks, uncertainty, and blocker; memory and Git returns include affected material IDs and status. The primary must first call `pcw_save_subagent_result` with that raw return, an exact filename-ID, and the worker's actual `executor_session_id`. Do not rewrite, summarize, compact, or make a semantic decision before this primary save. Then read the saved material through `pcw_read`, including `saved_at` and `executor_session_id`, before deciding on follow-up, consolidation, links, or acceptance.

The primary may itself perform this raw-result save and the environment/tools-map operations needed to choose a native agent. All other Current writes, content application, source checks, and Git operations are native-subagent work. Preserve substantive facts, conditions, uncertainty, tables, and code during consolidation. Compaction does not require retaining source attribution or provenance metadata.

Schedule a factual check at moments chosen from task complexity, and add one when a return reveals a mismatch that needs attention. A return alone never mandates another check. The checker must reproduce the result or inspect the real source, including for a no-change research result. Save and read its raw return by the same order, then the primary decides whether the observed result satisfies the user request.

## Memory rules

Read [Memory operations](references/memory-operations.md) before durable memory work. A material's filename, including `.md`, is its unique ID within `knowledge`; its path is separate. Rename updates search paths without re-embedding unchanged body text; exact incoming links change only when the filename-ID changes. Moving `a.md` to `nested/a.md` preserves its ID and links. Migrate legacy UUID-addressed memory only under an explicit migration request.

Current is readable Markdown with five sections: Goal, Constraints, Completion, Current step, and Blocker. Keep it compact. Change step or blocker only when the decision or obstacle changes; do not rewrite Current after every tool return.

For new or changed bodies, use [Prepare search](references/prepare-search.md). Preserve the literal semantic split and existing embedding/search behavior. Read [Embedding configuration](references/embeddings.md) only for provider configuration, search settings, or embedding failures. Numerical defaults are engineering defaults, not measured quality, price, latency, or resource claims.

Use `pcw_checkpoint` only through an authorized native assignment for exact durable memory paths. Source commits, pushes, package installation, model download, and absent-component repair need their own user authority as described in Runtime setup.

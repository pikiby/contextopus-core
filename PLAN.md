# Persistent Context Workspace

Version 0.6.0 defines one `$pcw` skill and a persistent local MCP server. This plan records the adopted design and the acceptance boundaries for its implementation.

## Responsibilities and workflow

The primary agent converses with the user, determines scope and acceptance, reads Current and knowledge through MCP, chooses native model/reasoning profiles, directly assigns native agents, and makes content and task decisions. Native subagents inspect real files, logs, code, and allowed services; make authorized changes; perform factual checks; write Current; apply knowledge/compaction/link decisions; and carry out Git operations. MCP manages PCW state only. It is neither a Controller nor a subagent dispatcher and uses no lifecycle hooks.

The primary uses a short cycle: obtain `pcw_action_requirements` for `prepare_assignment`, `process_result`, `transition`, or `finish`; perform the action under user authority; submit its result by the relevant MCP operation; obtain requirements again. Detailed directives are supplied immediately before their action.

For a native launch, `prepare_assignment` must return `ready: true` for the complete assignment and an exact profile ID from the current map. When it returns false, the primary corrects every reported prerequisite and repeats the call before launching. Receiving instructions without a valid assignment does not establish launch readiness; the primary still decides semantic suitability and authority.

Before assigning a native subagent, the primary itself uses native environment tools, descriptors, and necessary environment configuration to establish current capabilities, records them with `pcw_environment_check`, itself gathers and compares model information with roles, publishes current profiles with `pcw_tools_map_publish`, and selects an applicable profile. This is a limited primary responsibility, distinct from delegated project-source research. Profiles contain actual model identifiers, supported reasoning parameters, roles, and conditions. The primary explicitly supplies the selection at launch. There is no provider-wide hard-coded model ranking or effort map. A small model is appropriate only when a prepared task and map profile justify it; extra capability or reasoning must be explained by complexity, uncertainty, or verification needs.

A user request to prepare context authorizes memory preparation and required bounded investigation, not execution of a task merely recorded in Current. An explicit execution or continuation request includes needed preparation. Missing runtime components are diagnosed and repaired by a native worker only after the primary obtains user permission for the observed scope.

## Result ordering and checks

Workers author their own free-form Markdown results: facts, source coordinates, changes, checks, uncertainty, mismatch, and blockers. On every worker return, the primary first calls `pcw_save_subagent_result(work_root, workspace, assignment_id, result, executor_session_id)` with the exact raw text and actual session ID. MCP assigns UTC `saved_at`, returns a successful save only after persistence, and preserves the original saved record on duplicate delivery. The primary then uses `pcw_read` to see saved text and metadata before any substantive decision. This raw save and environment/tools-map operations are the primary's narrow direct-MCP exceptions; content changes, Current, Git, source checks, and applying decisions remain worker tasks.

Memory and Git returns include the affected material filename-IDs, Current path when affected, and actual status. A new raw return from the same executor may reuse its raw-result filename with a matching `expected_previous_revision`; it gets a new save timestamp and needs preparation again. An identical, still accurate return remains idempotent. Stale affected IDs or a generic success claim do not satisfy the return contract.

The primary schedules factual checks at intermediate or final moments selected from task complexity. A saved mismatch that needs attention creates an additional check. A return alone does not. A checker reproduces behavior or verifies real sources, even for no-change research, and returns observations and method. The primary saves then reads this raw check result and accepts only after comparing actual evidence with the user request. A static test, saved material, or worker claim does not prove live behavior.

## Durable memory

Each workspace stores readable `current.md` and Markdown materials below `knowledge/`. MCP generates new IDs and uses them as filenames; agents never choose names at creation. The full filename is the material ID. Moves preserve it and update only search paths. Existing materials remain readable without automatic migration. `links` contains exact generated filename-IDs with no relation types or mandatory reverse edges.

Knowledge remains free Markdown. Consolidation removes actual repetition from working materials while preserving substantive facts, conditions, uncertainty, tables, code, and implementation details. Source attribution and provenance metadata need not be retained after compaction. PCW never chooses semantic merges or link targets from vector similarity.

Current has readable Goal, Constraints, Completion, Current step, and Blocker sections. It is compact task focus, not a return journal. Update its step or blocker when the primary's decision or obstacle changes; change task meaning only when the user changes the task.

Content changes become pending search preparation. A dedicated native helper literal-splits only the returned body and submits the same text and revision. LanceDB stores literal parts, vectors, filename-IDs, and paths. Links-only edits and renames do not prepare or embed. The default local Qwen profile and its search cutoffs are engineering defaults, not measured retrieval, price, latency, or resource claims. Provider switching re-embeds stored literal parts into an inactive table without changing knowledge or splitting again.

Git tracks exact request-owned Current and knowledge paths through an authorized worker checkpoint. Runtime state, caches, vectors, and credentials stay outside Git. Restore/reconciliation makes derived search state match durable knowledge; it does not undo source or external actions.

## Delivery and acceptance

1. Keep one explicit skill and portable persistent MCP declaration.
2. Implement current tools-map/environment state, action requirements, primary raw-result save/read ordering, filename-ID migration/rename behavior, readable Current, preparation, semantic search, and durable memory operations.
3. Preserve the existing embedding/provider split and reject invented claims about numerical defaults.
4. Test observable runtime behavior separately from static documentation contracts.
5. Validate a real host run separately: actual tool exposure, direct native assignment, selection of model/reasoning from a current map, raw save/read ordering, factual checks, and source observations.

Contract tests must check documentation/reference reachability, the exact action headings, filename-ID fixtures, readable Current sections, and that documented MCP operations exist. They do not replace runtime, host, model, or factual-source evidence.

The measured retrieval and CPU/RAM assessment is recorded in [docs/search-assessment.md](docs/search-assessment.md). Its calibrated starting profile applies to the frozen project fixture; bundled defaults remain provisional. Native semantic preparation and whole-workflow acceptance require separate actual-agent evidence.

For an absent or stale tools map, the primary rebuilds it from the native environment's available tools, descriptors, and necessary environment configuration before assigning work. No bootstrap research launch is introduced.

## Workflow correction after the cluster-context audit

The passive control store `.pcw/.control/<workspace>/` holds model maps and an explicit task/assignment ledger independently of the derived index. A request is opened with `pcw_task_begin`; a ready preparation returns the complete native handoff and a generated return ID. Native executor binding and `pcw_assignment_get` preserve the prepared context. Raw save/read/assessment states and unresolved discrepancies persist across recovery.

`finish` checks retained affected material preparation, registered return processing, Current and exact memory checkpoint state. Frozen-scope service receipts make closeout finite without creating a new material for each technical completion. Isolated regressions use real LanceDB and temporary Git with injected test vectors; historical native evidence below does not validate these new APIs.

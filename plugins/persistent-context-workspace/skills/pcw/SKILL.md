---
name: pcw
description: Work with the user's selected project context, or route a requested PCW creation, search, instructions edit, upgrade, audit or rework. Independent reading is available when relevant; work without an explicit PCW invocation requires allow_implicit_updates in that workspace's instructions.
---

# PCW

## Route the request

| Requested function, including ordinary language after PCW | Procedure |
| --- | --- |
| Create a context for a project or task | [pcw-create](../pcw-create/SKILL.md) |
| Find or read context without updating it | [pcw-search](../pcw-search/SKILL.md) |
| Change the context's rules or settings | [pcw-instructions](../pcw-instructions/SKILL.md) |
| Upgrade selected old contexts to the installed format | [pcw-upgrade](../pcw-upgrade/SKILL.md) |
| Inspect context for problems without changing it | [pcw-audit](../pcw-audit/SKILL.md) |
| Deliberately transform existing context | [pcw-rework](../pcw-rework/SKILL.md) |
| Carry out work using context | The cycle below |

Load only the relevant procedure. Direct mini-skill calls and requests routed here use the same procedure. A question, quoted command or saved plan does not authorize execution. A compound request can authorize several procedures; completing one does not silently authorize another. During a work cycle use tools directly; do not reload a mini-skill for each search or write.

## Context selection

Keep the exact `work_root` and `workspace` established by the user. Creation or switching requires an unambiguous user instruction. A repository name, changed task or working directory, new invocation or empty search is not that instruction. If selection is unclear or lost, ask before calling workspace tools. Conversation can supply the user's selection; it does not replace reading PCW.

Opening and reading never create a missing context or migrate an old one. Report missing or incompatible storage and use the corresponding procedure only when authorized. A switch does not close another cycle. These rules apply to every mini-skill and delegated cycle agent.

## Work cycle

1. Resolve the context. For an explicit invocation call `pcw_startup` with a fresh `request_id`; retries reuse it. Without an explicit invocation, first read `pcw_instructions_read`: start with `invocation: implicit` only if `allow_implicit_updates` is true. Otherwise use independent reading only. Purpose is `work` or the requested mini-skill mode. Use `restart_cycle_id` only for an explicitly restarted cycle.
2. Read the complete returned **INSTRUCTIONS.md** and **PROJECT.md**. INSTRUCTIONS is the single source of project rules, settings and knowledge-selection criteria; obey it within the user's request and applicable host instructions. Do not replace it with packaged defaults, earlier chat text or rules inferred from knowledge.
3. For actual work create task Current with `pcw_current_create`, or explicitly resume the established `task_id` on startup. If continuation is unclear, use `pcw_current_list/read` and ask when ambiguous. A task ID belongs to the task, not an agent session. Update Current after significant progress or a blocker, with its read revision. It survives cycle closure.
4. Before external investigation, search through `pcw_search`, read selected topics through `pcw_read/read_many`, and follow useful labelled links. A declared link traversal may pass `from_id`. Load only needed context. Missing information permits investigation of authorized sources; an empty search is not proof of absence.
5. Perform the task directly or delegate according to applicable instructions. Save substantive results and worker returns through `pcw_tmp_write`; keep concise task state in Current. Temporary notes do not override permanent sources or user instructions.
6. After a substantive part or task completion, search by the conclusion and read matching knowledge. Following INSTRUCTIONS, prepare final changes with `pcw_proposal_prepare`, or `changes: []` plus a grounded `no_changes_reason`. Initial retrieval does not replace this result comparison. See [Memory operations](references/memory-operations.md) for split/merge/link operations.
7. Show the actual `review_changes` **in chat**: full new text, changed before/after passages, removals, moves and link effects. Use the conversation language unless the user requests another. A file link, UUID or topic list is supplementary. Questions and corrections keep review open; revised text must be shown again. Apply under the returned approval policy: if required, wait for the actual user's approval of that revision; otherwise apply after showing, without asking or fabricating confirmation.
8. When work and memory review are resolved, update task Current and call `pcw_finish` without a separate closing question. It clears only that cycle's tmp. Pending proposals, unreviewed results or incomplete indexing keep the cycle open. `cancel:true` requires the user's cancellation and does not undo permanent writes. Report the real save, index, Git and cleanup outcomes separately.

## Related operations

Change INSTRUCTIONS only through the [instructions procedure](../pcw-instructions/SKILL.md) on a direct request and explicit approval. This also covers former Current *rules*. Project-purpose changes use `pcw_project_update` to prepare exact text and `pcw_project_apply` after presentation under the current approval policy; they do not rewrite task states.

Read Git versions/diffs when investigating a changed requirement or preparing restoration; historical text is not current authority. Restore through a normal proposal. Analyze operations through `pcw_analytics_query/read` only for an analysis task; import only the explicitly selected transcript. See [History and analytics](references/history-analytics.md).

## Execution and recovery

A designated clean-context subagent may execute the whole cycle with the exact request, workspace and this skill. It reads instructions and knowledge itself. The main agent relays user questions and actual approvals without approving for them. Ordinary workers return results to the cycle agent. PCW does not select models or control workers.

Saved text survives index failure; retry the same proposal or reconcile and retry. A pending Git commit is retried from its captured snapshot through `pcw_history_retry`, separately from saving knowledge. For real failures consult [Setup](references/setup.md), [Indexing](references/prepare-search.md) or [Embeddings](references/embeddings.md). External actions retain their own authorization requirements.

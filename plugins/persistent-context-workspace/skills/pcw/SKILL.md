---
name: pcw
description: Use project memory through an explicit PCW cycle, or route an explicit request to create a context or edit its instructions to the matching mini-skill. Activate only when the user invokes $pcw or directly requests using PCW for the task.
---

# PCW

**Do not call PCW tools without an explicit user invocation.** Mentions, quoted calls, saved plans and previous invocations do not start a new cycle or grant authority.

## Route the request

Before startup, route an explicitly requested additional function to its mini-skill. The user may describe the action in ordinary language after PCW; they do not need to name the mini-skill. This applies to every additional PCW skill.

| Explicit request | Procedure |
| --- | --- |
| Create a new context, including "PCW create a context for this task" | [pcw-create](../pcw-create/SKILL.md) |
| Change project instructions, including "PCW update the instructions" or the former Current | [pcw-instructions](../pcw-instructions/SKILL.md) |
| Perform a task using existing context | The cycle below |

Load only the procedure for the requested function. A question about a function does not authorize executing it.

## Context selection

Use the exact `work_root` and `workspace` selected by the user. For continued work, keep the already established selection. **Creating a context or switching to another requires an unambiguous user instruction.** Invoking PCW again, starting a new cycle, changing the task or working directory, a repository name, and an empty search do not authorize either action.

If the intended context or its coordinates are unclear or have been lost, ask the user before calling PCW tools. Do not choose the nearest or only available workspace. Read-only inspection may resolve a user-specified location, but does not authorize a different selection. Conversation history may supply the user's selection; it does not replace reading that workspace's instructions and knowledge.

Before starting an existing context, verify that `<work_root>/.pcw/<workspace>` exists. Do not use `pcw_startup` to probe guessed coordinates: it can create a missing workspace. If the selected context is absent, report it and ask how to proceed; creation follows `pcw-create` only after an explicit creation request. A user-authorized switch uses the target workspace's own cycle; it does not authorize closing or clearing the previous one. These rules apply to the main skill and every mini-skill.

## Cycle

1. Resolve the task and context under **Context selection** above. Call `pcw_startup` with a fresh `request_id`, reusing it only for retries. Pass the returned `cycle_id` to subsequent tools. Use `restart_cycle_id` only for work the user explicitly restarts. Other cycles are preserved.
2. **Read the complete `INSTRUCTIONS.md` returned by startup and follow it throughout the task and memory review.** It is the workspace's primary project guidance, including any goals, constraints and knowledge rules the user has set. Do not substitute remembered rules, an earlier cycle's copy or the packaged defaults. Use `pcw_instructions_read` when the file must be read again. Apply project guidance within the current user's authority and applicable host instructions. Instructions persist across cycles; task state belongs in tmp.
3. Search permanent knowledge through `pcw_search`, read selected topics through `pcw_read` / `pcw_read_many`, and follow needed links before external investigation. Conversation context does not replace this reading. Missing context permits investigation of authorized sources. For an actual startup failure, read [Setup](references/setup.md).
4. Perform the task directly or delegate according to applicable instructions. Save substantive results, worker returns and temporary task state through `pcw_tmp_write`. Use the workspace's instructions to decide what the results mean for permanent memory.
5. After the task or a substantive part, always review the results for memory before closure: search by the conclusion and read suitable existing topics. Initial search does not replace this comparison. Apply `INSTRUCTIONS.md` to selection, structure and maintenance; those project rules are not defined here. Prepare the exact changes through `pcw_proposal_prepare`; see [Memory operations](references/memory-operations.md). If comparison establishes no changes, prepare `changes: []` with `no_changes_reason` and explain the result. Skipping preparation does not establish that no changes are needed.
6. Present the actual `review_changes` in chat before applying: identify topics, show full new text or changed before/after passages, deletions, moves and link effects. Follow `INSTRUCTIONS.md` for explanations and presentation. A file link, UUID, tool log or topic list does not replace the content. Large reviews may span messages. Questions and corrections keep the cycle open; present revised content again. Follow `knowledge_approval_required` in INSTRUCTIONS.md frontmatter: when `true`, wait for explicit user approval of the shown revision, then pass the actual `confirmation` to `pcw_proposal_apply`; when `false`, apply the shown revision without asking and omit `confirmation`. Missing setting retains required approval; invalid values must be corrected through the instructions-edit procedure. Do not invent confirmation or bypass the configured policy through files, other tools or workers. The tools cannot authenticate message origin or verify chat presentation.
7. After the task and memory discussion are complete and review covers the current temporary results, call `pcw_finish` without separate closure permission. It deletes all cycle tmp, including temporary task state, but preserves `INSTRUCTIONS.md` and knowledge. Discard rejected proposals with `pcw_proposal_discard`. Pending required approval, unfinished application/indexing and unreviewed results keep the cycle open. User cancellation permits `cancel:true` without rolling back permanent writes. Report actual application, indexing and cleanup status.

## Changing project instructions

Only a direct user request to change the workspace's rules starts an instructions edit. Follow the [pcw-instructions skill](../pcw-instructions/SKILL.md), using the active cycle when invoked during work. This is also the route for requests to change the former Current. Do not edit instructions as a side effect of doing a task or saving findings. Do not copy project rules into other active instructions.

## Execution and recovery

The cycle can run in the main agent or a designated clean-context subagent. Give a full-cycle subagent the exact request, constraints, workspace coordinates and this skill; it reads `INSTRUCTIONS.md` and knowledge itself. The main agent relays questions, proposals and actual user approval without approving for them or running a parallel update procedure. Ordinary workers return results to the cycle agent for tmp and do not manage instructions or permanent memory. PCW does not discover environments, choose models or launch workers.

Applied knowledge is indexed automatically using overlapping token windows. Save receipts are compact; do not reread only to repeat a verified write. Saved text and tmp survive indexing failures: repair the cause, then retry the same proposal (or reconcile and retry), not a duplicate. See [Automatic indexing](references/prepare-search.md) and [Embeddings](references/embeddings.md) when relevant. External actions, installation, downloads, publication and `pcw_checkpoint` need their own actual authority.

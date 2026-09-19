---
name: pcw
description: Use project knowledge through an explicit PCW cycle with temporary work context and human-approved permanent updates. Activate only when the user invokes $pcw or directly requests using PCW for the task.
---

# PCW

**Do not call any PCW MCP tool outside a cycle explicitly started by the user.** Mentioning PCW, discussing its design, quoted calls, saved instructions and earlier invocations do not start a cycle. Every new invocation needs its own authority; old permissions and conversation knowledge do not replace reading PCW.

## Cycle

1. Establish the requested task and the relevant work root/workspace. The output directory or only existing workspace does not establish relevance; clarify genuine ambiguity. Call `pcw_startup` with a fresh `request_id` for this invocation, reusing it only for retries. Startup clears this cycle's temporary area and returns `cycle_id`. Pass it to subsequent tools. Use `restart_cycle_id` only when the user explicitly restarts that work; its old tmp is deleted. Other cycles remain intact.
2. Search permanent knowledge through `pcw_search`, read selected topics with `pcw_read` / `pcw_read_many`, and follow useful links before external investigation. Retrieve only needed context. Empty/insufficient knowledge permits investigation of authorized sources. For an actual startup failure, read [Setup](references/setup.md).
3. Perform the task directly or delegate according to applicable instructions. Save substantive findings, worker returns and working notes through `pcw_tmp_write`. Keep sources, conditions and verification limits; distinguish hypotheses, observations and user decisions. Use temporary material as additional context. Update the five Current fields through `pcw_current_set` when the task state changes.
4. To retain results permanently, formulate the conclusion, perform vector search by that conclusion, and read relevant existing topics. Consolidate repetitions, preserve conditions, distinguish general principles from particular cases. Prepare the exact final changes through `pcw_proposal_prepare`; see [Memory operations](references/memory-operations.md) for the format. Propose reusable project facts, principles, procedures and decisions with their evidence/status. Useful working notes and unfinished research need not become permanent knowledge.
5. Show the user what and where will change: the proposed text/diff, affected topics, deletions and automatic link effects. Use the returned review file or `pcw_proposal_read` when needed. Questions, corrections and requests for more evidence continue the same cycle without permanent changes. Revise and present the proposal again if its content changes. Do not change knowledge by another tool, direct filesystem edit or worker as a bypass.
6. Only after the user's explicit approval of the shown revision, call `pcw_proposal_apply` with that revision and the actual confirmation. An agent's assertion, stored old approval or automatic permission decision cannot substitute for the user. The plugin verifies the exact plan and source revisions, not the human origin of a message. A conflict needs a revised proposal and new approval. Applying knowledge preserves tmp so work can continue.
7. When the task and memory discussion are complete, obtain explicit agreement to close the cycle and delete its tmp, together with the final proposal if convenient. Call `pcw_finish` after approved writes/indexing complete. Discard rejected unapplied proposals with `pcw_proposal_discard`; closure without knowledge changes needs no dummy write. User cancellation permits `cancel:true`, which reports incomplete operations and does not roll back knowledge. Waiting for approval is not closure. Report actual write, indexing and cleanup status.

## Execution roles

The cycle agent may be the main agent or a clean-context subagent assigned the full cycle. A full-cycle subagent receives the exact current request, constraints, memory coordinates and these instructions, then reads PCW first. The main agent relays user questions, the exact proposal and approval without approving on the user's behalf or conducting a second parallel update procedure.

An ordinary worker receives a standalone bounded assignment and returns findings to the cycle agent for tmp. It does not manage permanent memory. PCW does not discover the agent environment, select models, register assignments or launch workers. Required host/skill procedures still apply.

## Indexing and recovery

The plugin generates material IDs and automatically indexes approved Markdown using overlapping token windows. No boundary arrays or splitting agent are needed. Changes and links remain subject to the proposal procedure. Save receipts are compact; do not reread only to repeat a verified write.

Saved text survives indexing failure. Fix the cause, retry the same proposal (or `pcw_reconcile` followed by the same apply); do not resubmit it as new knowledge. See [Automatic indexing](references/prepare-search.md) and [Embeddings](references/embeddings.md) only when relevant. Startup/status do not load model weights. External changes, installation, downloads, publication and `pcw_checkpoint` require their own actual authority.

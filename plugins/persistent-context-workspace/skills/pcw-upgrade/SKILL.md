---
name: pcw-upgrade
description: Inspect and migrate explicitly selected old PCW contexts to the installed storage format, preserving user instructions and knowledge. Does not perform semantic rework.
---

# Upgrade context format

1. Resolve the user's exact context, list of contexts or bounded directories. Follow [context selection](../pcw/SKILL.md#context-selection). Enumerate only those directories, never the whole computer.
2. Call `pcw_upgrade_plan` for each selected existing context. It returns compatibility, the source revision, technical changes, saved unfinished work and blockers. Explain each unfinished work item using its request/task and material titles; distinguish prepared proposals from applied changes awaiting closure. An open record does not prove that an agent is running. An unknown structure requires inspection/restoration; do not guess its version. An already compatible format requires no rewrite merely because the plugin was updated.
3. Show affected paths and explain that the snapshot retains the entire workspace, including tmp, plus its control state. Compatible unfinished work is preserved with the same IDs, draft revisions and states. Do not apply, discard or cancel it as part of migration. If `ready` is false, describe the exact blocker and affected work; resolving it is a separate authorized procedure. Otherwise apply the requested migration through `pcw_upgrade_apply(expected_revision, user_request)`; use `resume_revision` when a migration is pending.
4. Report verified format, workspace/control backup paths, preservation of unfinished work and any pending index repair. Retry an interrupted migration using its original revision and retained snapshot. Source conflicts require inspection. The format is marked current only after source and backup checks. Migration does not finish old tasks or approve their proposals.
5. Preserve custom INSTRUCTIONS verbatim. A new default template does not authorize replacement. Reclassifying old goals, splitting mixed knowledge and revising instructions are separate requested rework/instructions procedures. Do not turn format migration into substantive editing.

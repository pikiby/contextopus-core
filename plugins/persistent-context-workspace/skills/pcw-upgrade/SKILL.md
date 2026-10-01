---
name: pcw-upgrade
description: Inspect and migrate explicitly selected old PCW contexts to the installed storage format, preserving user instructions and knowledge. Does not perform semantic rework.
---

# Upgrade context format

1. Resolve the user's exact context, list of contexts or bounded directories. Follow [context selection](../pcw/SKILL.md#context-selection). Enumerate only those directories, never the whole computer.
2. For each existing context call `pcw_workspace_inspect` and `pcw_upgrade_plan`. Read the source revision and technical changes. An unknown structure requires inspection/restoration; do not guess its version. An already compatible format requires no rewrite merely because the plugin was updated.
3. Show affected paths, preservation rules and backup behavior. Resolve active cycles first through their own authorized procedure; never cancel another agent's work for convenience. Apply the requested technical migration with `pcw_upgrade_apply(expected_revision, user_request)`.
4. Report verified format, retained backup and any pending repair. Retry an interrupted migration using its original revision; do not overwrite its snapshot. Source conflicts require inspection. The format is marked current only after successful checks.
5. Preserve custom INSTRUCTIONS verbatim. A new default template does not authorize replacement. Reclassifying old goals, splitting mixed knowledge and revising instructions are separate requested rework/instructions procedures. Do not turn format migration into substantive editing.

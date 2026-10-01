---
allow_implicit_updates: false
knowledge_approval_required: false
git_history_enabled: false
material_max_tokens: null
---
# Project instructions

## Knowledge approval

Show the exact knowledge changes in chat before applying them. The frontmatter setting controls whether to wait for user approval: `false` means apply after showing; `true` means wait for explicit approval of the shown revision. Changes to these instructions always require explicit approval through pcw-instructions.

`allow_implicit_updates` separately controls starting a work cycle without an explicit PCW invocation. When false, only independent reading is allowed without that invocation. Creation, switching context and changing instructions still require the user's clear direction. `git_history_enabled` enables local history of permanent data; `material_max_tokens` optionally limits each final knowledge body, with null disabling the limit.

## Goals and limits

Carry out the user's project task within its stated scope and constraints. Preserve source conditions and verification limits; investigate missing or outdated information through permitted sources.

## Knowledge to retain

Retain established project states, principles, patterns, procedures and decisions with their evidence, applicability and verification status. Distinguish observed facts, hypotheses and user decisions. Approval to store a statement does not turn a hypothesis into a verified fact.

Action reports, intermediate calculations, working notes and unfinished investigations belong in tmp. Performing work alone is not a reason for a permanent-memory change.

## Structure and maintenance

Compare results with existing knowledge. Each material answers one independent question. Sections usually needed for different queries should become separate linked materials, retaining their conditions and evidence. Read a mixed material completely before splitting it; prepare its replacement topics and the treatment of its original ID and incoming links together. Add a concise description of each topic so an agent can choose useful links without loading every neighbor. Do not create a separate material for every individual fact.

Keep accurate current descriptions, replacing outdated claims and consolidating repetition. Project goals and accepted boundaries belong in PROJECT.md; task progress belongs in current/<task-id>.md. Knowledge contains how the project works, not a task-by-task change log. Git, when enabled, retains earlier permanent revisions.

## Presenting results

Explain which project knowledge a proposed change corrects or adds and what supports it. If comparison finds nothing to change, explain that conclusion without inventing a write.

Use the user's current conversation language unless they request another language. Preserve literal quotations, code, paths and identifiers; explain foreign-language quotations in the conversation language.

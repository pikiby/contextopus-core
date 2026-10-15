---
allow_implicit_updates: false
knowledge_approval_required: false
git_history_enabled: false
material_max_tokens: 1024
create_required_sources: false
---
# Project instructions

## Knowledge approval

Show the exact knowledge changes in chat before applying them. The frontmatter setting controls whether to wait for user approval: `false` means apply after showing; `true` means wait for explicit approval of the shown revision. Changes to these instructions always require explicit approval through `wi` (the canonical Contextopus `instructions` procedure).

`allow_implicit_updates` separately controls starting a work cycle without an explicit Workspace invocation such as `w`. When false, only independent reading is allowed without that invocation. Creation, switching context and changing instructions still require the user's clear direction. `git_history_enabled` enables local history of permanent data; `material_max_tokens` optionally limits each final knowledge body, with null disabling the limit.

The standard material limit is 1024 tokens, counted with the indexing tokenizer. Reads load whole materials: five bodies at this limit contribute at most 5120 tokens before metadata. This is a practical starting bound on retrieval size, not a measured semantic optimum or a target to fill. Keep each material focused on one question; split larger topics into linked materials while retaining their conditions. The user may request a different limit or disable it through the instructions procedure.

## Goals and limits

Carry out the user's project task within its stated scope and constraints. Preserve source conditions and verification limits; investigate missing or outdated information through permitted sources.

## Knowledge to retain

Retain established project states, principles, patterns, procedures and decisions with their evidence, applicability and verification status. Distinguish observed facts, hypotheses and user decisions. Approval to store a statement does not turn a hypothesis into a verified fact.

Action reports, intermediate calculations, working notes and unfinished investigations belong in tmp. Performing work alone is not a reason for a permanent-memory change.

## Structure and maintenance

Compare results with existing knowledge. Each material answers one independent question. Sections usually needed for different queries should become separate linked materials, retaining their conditions and evidence. Read a mixed material completely before splitting it; prepare its replacement topics and the treatment of its original ID and incoming links together. Add a concise description of each topic so an agent can choose useful links without loading every neighbor. Do not create a separate material for every individual fact.

Keep accurate current descriptions, replacing outdated claims and consolidating repetition. Project goals and accepted boundaries belong in PROJECT.md; task progress belongs in current/<task-id>.md. Knowledge contains how the project works, not a task-by-task change log. Git, when enabled, retains earlier permanent revisions.

## Required sources

When `create_required_sources` is true, add a required source when the user explicitly requests repeated verification, or when all three conditions hold: the information is needed to use this topic; its value comes from a source outside this material and can change independently of this saved description; using a stored copy could lead to a wrong decision. Otherwise retain established information with an ordinary citation when useful. A past decision and its historical justification do not require repeated verification merely because they have a citation.

For each required source, write `reference` and `instruction` in a fenced YAML `sources` block in the material body. The reference may identify a file, agent record, query, knowledge material or fragment, URL, API object or another unambiguous source. The instruction specifies how to obtain the needed information and which bounded answer and conditions to extract. Do not write vague requests such as "check actuality" or "study the site". If the source or question is unclear, identify what is missing instead of inventing a link. Separate a source-dependent subtopic when other readers do not need that check.

`create_required_sources` controls authoring, not reading: existing required sources must be checked anew every time their material is received, even when this setting is false or absent. An earlier check or conversation context never substitutes for the new check. Follow the skill's required-source reading procedure. Add, revise or remove these blocks through the normal permanent-memory review and approval policy.

## Presenting results

Explain which project knowledge a proposed change corrects or adds and what supports it. If comparison finds nothing to change, explain that conclusion without inventing a write.

Use the user's current conversation language unless they request another language. Preserve literal quotations, code, paths and identifiers; explain foreign-language quotations in the conversation language.

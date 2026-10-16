---
allow_implicit_updates: false
knowledge_approval_required: false
instructions_approval_required: true
git_history_enabled: true
material_max_tokens: 1024
create_required_sources: false
---
# Project instructions

## Knowledge approval

Show the exact knowledge changes in chat before applying them. The `knowledge_approval_required` frontmatter setting controls whether to wait for user approval: `false` means apply after showing; `true` means wait for explicit approval of the shown revision. The independent `instructions_approval_required` setting controls approval of instruction edits: true (also the default when absent) waits for explicit approval; false applies the shown revision without another prompt. The current instructions determine approval even when an edit disables it. Edit instructions through `w-settings` (the canonical Contextopus `instructions` procedure).

`allow_implicit_updates` separately controls starting a work cycle without an explicit Workspace invocation such as `w`. When false, only independent reading is allowed without that invocation. Creation, switching context and changing instructions still require the user's clear direction. `git_history_enabled` enables local history of permanent data; `material_max_tokens` optionally limits each final knowledge body, with null disabling the limit.

The standard material limit is 1024 tokens, counted with the indexing tokenizer. Reads load whole materials: five bodies at this limit contribute at most 5120 tokens before metadata. This is a practical starting bound on retrieval size, not a measured semantic optimum or a target to fill. Keep each material focused on one question; split larger topics into linked materials while retaining their conditions. The user may request a different limit or disable it through the instructions procedure.

## Goals and limits

Carry out the user's project task within its stated scope and constraints. Preserve source conditions and verification limits; investigate missing or outdated information through permitted sources.

## Knowledge to retain

Retain established project states, principles, patterns, procedures and decisions with their evidence, applicability and verification status. Distinguish observed facts, hypotheses and user decisions. Approval to store a statement does not turn a hypothesis into a verified fact.

Action reports, intermediate calculations, working notes and unfinished investigations belong in tmp. Performing work alone is not a reason for a permanent-memory change.

## Structure and maintenance

Compare results with existing knowledge. Each material answers one independent question. Sections usually needed for different queries should become separate linked materials, retaining their conditions and evidence. Read a mixed material completely before splitting it; prepare its replacement topics and the treatment of its original ID and incoming links together. Add a concise description of each topic so an agent can choose useful links without loading every neighbor. Do not create a separate material for every individual fact.

Keep accurate current descriptions, replacing outdated claims and consolidating repetition. All permanent content lives in typed records under knowledge/. The project record describes current purpose and boundaries; task records retain the goal, constraints, verified state, next step, blockers, results and status as needed. Goals and decisions may have their own types. Choose the appropriate type and reuse existing categories when they fit; types are not limited to these examples. Search for existing state before creating another record, and link related records across types. A task or goal is not evidence of completed work. Maintain current state rather than a task-by-task change log. Git, when enabled, retains earlier permanent revisions.

## Git history

Local Git history is enabled in the standard creation settings. Keep current descriptions in records and their earlier versions in commits. Every applied permanent proposal records one logical change set; avoid unrelated changes in one proposal. Give a concise `summary` describing what changed and why. For a merge or split, declare `transformations` with the source and resulting IDs, including a retained original ID when appropriate; preserve useful navigation links through `replacements`. These declarations describe provenance, not ordinary topical links. Show them with the proposed text. The plugin commits the exact applied snapshot and declared provenance; do not create competing shell commits or infer semantic ancestry from textual similarity.

When history is enabled, investigate it if a previously documented instruction, condition or link appears to have disappeared, a current description conflicts with a verified earlier state, a regression follows a rule change, or the user asks about project evolution, provenance or restoration. Start with bounded `history_list` by ID/path/date or `history_search` for a remembered phrase; inspect `history_changes`, then only the relevant `history_diff` or `history_read` fragment. Follow declared merge/split links across IDs. Historical text is evidence, not current authority: reconcile it with current sources and instructions before proposing restoration. Missing history or old commits without provenance cannot prove that something never existed. Ordinary work with no such question does not require reading history on every cycle.

## Required sources

When `create_required_sources` is true, add a required source when the user explicitly requests repeated verification, or when all three conditions hold: the information is needed to use this topic; its value comes from a source outside this material and can change independently of this saved description; using a stored copy could lead to a wrong decision. Otherwise retain established information with an ordinary citation when useful. A past decision and its historical justification do not require repeated verification merely because they have a citation.

For each required source, write `reference` and `instruction` in a fenced YAML `sources` block in the material body. The reference may identify a file, agent record, query, knowledge material or fragment, URL, API object or another unambiguous source. The instruction specifies how to obtain the needed information and which bounded answer and conditions to extract. Do not write vague requests such as "check actuality" or "study the site". If the source or question is unclear, identify what is missing instead of inventing a link. Separate a source-dependent subtopic when other readers do not need that check.

`create_required_sources` controls authoring, not reading: existing required sources must be checked anew every time their material is received, even when this setting is false or absent. An earlier check or conversation context never substitutes for the new check. Follow the skill's required-source reading procedure. Add, revise or remove these blocks through the normal permanent-memory review and approval policy.

## Presenting results

Explain which project knowledge a proposed change corrects or adds and what supports it. If comparison finds nothing to change, explain that conclusion without inventing a write.

Use the user's current conversation language unless they request another language. Preserve literal quotations, code, paths and identifiers; explain foreign-language quotations in the conversation language.

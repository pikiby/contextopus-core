# Work with typed records and shared temporary memory

Use this scenario for “update the saved policy,” “track this task,” or “verify and save the result.” Workspace owns contexts with independent INSTRUCTIONS and typed Markdown records in the shared Core index. Knowledge, project, task, goal and decision records use the same operations; `workspace.record_types` lists types actually present, and `workspace.list` returns bounded metadata. A planned status is not evidence of completed work.

## Prepare and retain actual work

Obtain `guide(procedure="workspace")` before the applicable action. For independent reading, discover contexts and read relevant records without starting a work cycle. For user-authorized work, select the context and inspect existing work. Start one new cycle with the exact user request and read its returned complete instructions/project, or continue the matching cycle with the available current rules. Compare results with existing knowledge, prepare actual changes or explain a grounded no-change conclusion, present and apply changes under the effective approval policy, and use the dedicated finish under the separate cleanup approval policy. Repeated invocation and follow-up questions continue the same task and cycle. The ordinary procedure already covers its stages; use `guide(operation="workspace.proposal_prepare")` for an unknown signature.

Refresh complete rules for a new independent task, an explicit context change, changed rules or lost rule text. Refresh used procedures after a plugin update. The default `reread_instructions=false` does not require a redundant read on every invocation; an explicit agent/model profile may require it. Pass applicable user rules, including cross-cutting requirements, to delegated workers.

Search normally returns metadata, author-written descriptions and compact diagnostics. Evaluate the scope, distinct document count, relevance boundary and candidate completeness before deciding what to read or whether another query is needed. Distance is not confidence. Read useful bodies through `workspace.read(material_id=...)` or `workspace.read_many(material_ids=[...])`. Reuse existing stable IDs when changing a task or decision, rather than adding a duplicate “latest result” record.

New records and actual body changes include an author-reviewed description of content and applicability. Existing description gaps remain readable and are listed by audit; repair them after reading the whole record through ordinary proposals. Never substitute a title or truncated beginning. Stable YAML IDs identify records; stored YAML links use real vault paths for native Obsidian navigation. A rename proposal shows affected local incoming links and blocks a foreign-context rewrite until that context is explicitly updated. Display aliases describe neither the target's applicability nor the reason for an edge.

Required sources keep their reference and retrieval instruction. Check them anew each time their record is received, even when the ordinary instruction-rereading setting is false. Navigation links do not become mandatory source checks.

Example: after verifying an API migration, update its existing decision and task state in one `workspace.proposal_prepare`. Use `material_id` and `expected_revision` for existing records; genuinely new records use proposal `key` and may link with `@key`. State verified behavior, source and unresolved limitation. Present returned `review_changes` before applying its exact revision. Report save, indexing and Git outcomes separately.

## Rules and temporary handoff

Machine policy settings live in Core configuration. Read selected effective values with `workspace.settings_read`; review changes through `workspace.settings_preview/settings_apply` under the current instructions-approval policy. Complete free-form INSTRUCTIONS retain user rules. Instruction edits require a direct user request and `instructions_prepare/instructions_apply`. `instructions_approval_required` controls those approvals independently of `knowledge_approval_required`; proposing false cannot waive current true approval.

Within the active cycle, `workspace.tmp_write` saves an optional assignment, source evidence or reusable result as a .tmp card with a readable name, stable ID and ordinary/required links. Pass its reference and applicable rules to native workers; native agent tools handle delivery and replies. `workspace.tmp_list/tmp_read` recover needed shared inputs. Update the current card at its revision instead of accumulating obsolete notices. No per-file disposition ledger is required.

Temporary cards can link to permanent or temporary material; permanent knowledge must not depend on .tmp. `workspace.tmp_delete` checks the exact revision, incoming dependencies and cleanup policy. Preserve useful inputs for pause or handoff. Once work and memory review are resolved, `workspace.status` provides pending work and the exact deletion scope/revision for the dedicated finish tool. Applying knowledge does not itself finish the cycle.

Derived context/<name> tags support visualization without creating another ownership/filter mechanism; other tags are preserved. Context names are unique under Unicode NFKC and case-insensitive comparison.

Implementation references: `src/contextopus/modules/workspace/cycles.py`, `src/contextopus/modules/workspace/records.py`, `src/contextopus/modules/workspace/temporary_materials.py`, `src/contextopus/modules/workspace/operations.py`. Detailed procedures: `workspace`, `instructions`, `reference/memory-operations`.

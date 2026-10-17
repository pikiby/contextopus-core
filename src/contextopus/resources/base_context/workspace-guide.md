# Workspace guide and example

Contextopus Core shares indexing, retrieval, configuration and operation contracts. Workspace owns contexts with independent INSTRUCTIONS and typed Markdown records. Project, task, decision, guide and template records share the same store and search path.

Obtain `guide(procedure="workspace")` before the applicable action. For independent reading, discover contexts and read relevant records without starting a work cycle. For user-authorized work, select the context, read its complete instructions, open one cycle, keep progress, compare results with existing knowledge, prepare exact changes or a grounded no-change conclusion, present and apply changes under the effective approval policy, and finish. Repeated invocation and follow-up questions continue the same task and cycle. The ordinary procedure already covers its stages; use `guide(operation="workspace.proposal_prepare")` for an unknown signature.

Refresh complete rules for a new independent task, an explicit context change, changed rules or lost rule text. Refresh used procedures after a plugin update. The default `reread_instructions=false` does not require a redundant read on every invocation; an explicit agent/model profile may require it. Pass applicable user rules, including cross-cutting requirements, to delegated workers.

Search normally returns metadata, author-written descriptions and compact diagnostics. Evaluate the scope, distinct document count, relevance boundary and candidate completeness before deciding what to read or whether another query is needed. Distance is not confidence. Material limits apply after grouping repeated fragments by document; explicit fragment mode uses fragment units. Read a chosen record before treating its body as evidence.

New records and actual body changes include an author-reviewed description of content and applicability. Existing description gaps remain readable and are listed by audit; repair them after reading the whole record through ordinary proposals. Never substitute a title or truncated beginning. Stable YAML IDs identify records; stored YAML links use real vault paths for native Obsidian navigation. A rename proposal shows affected local incoming links and blocks a foreign-context rewrite until that context is explicitly updated. Display aliases describe neither the target's applicability nor the reason for an edge.

Required sources keep their reference and retrieval instruction. Check them anew each time their record is received, even when the ordinary instruction-rereading setting is false. Navigation links do not become mandatory source checks.

Example: after verifying an API migration, update its decision record and task state in one proposal. State verified behavior, source and unresolved limitation. Do not transform a planned migration into a completed fact.

Machine policy settings live in Core configuration. Read selected effective values with `workspace.settings_read`; review changes through `workspace.settings_preview/settings_apply` under the current instructions-approval policy. Complete free-form INSTRUCTIONS retain user rules. Instruction edits require a direct user request and `instructions_prepare/instructions_apply`. `instructions_approval_required` controls those approvals independently of `knowledge_approval_required`; proposing false cannot waive current true approval.

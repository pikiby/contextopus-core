# Workspace guide and example

Contextopus Core shares indexing, retrieval, configuration and operation contracts. Workspace owns contexts with independent INSTRUCTIONS and typed Markdown records. Project, task, decision, guide and template records share the same store and search path.

For independent reading, discover contexts and read relevant records without starting a work cycle. For user-authorized work, use the selected context, read its current instructions, open one cycle, keep progress, prepare exact knowledge changes, present them, apply under its approval policy, and finish. Fetch `procedure(name="workspace")` for the authoritative procedure and use `describe` for unknown arguments.

Example: after verifying an API migration, update its decision record and task state in one proposal. State verified behavior, source and unresolved limitation. Do not transform a planned migration into a completed fact.

Instruction edits require a direct user request. `instructions_approval_required` controls their approval independently of `knowledge_approval_required`. A missing instruction approval setting means true. Disabling approval still follows the current policy.

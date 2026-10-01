---
name: pcw-create
description: Create a PCW context only on an explicit request, with a user-selected location, project definition and separately chosen settings. Also used when pcw routes that request here.
---

# Create context

1. Follow [context selection](../pcw/SKILL.md#context-selection). Establish the actual creation request and project/task scope. Accept any clear natural-language description; do not require parameter names.
2. Resolve placement. If unspecified, offer concrete full paths under the relevant project or another known location, plus a user-chosen location. Do not invent a shared directory. Show `<work_root>/.pcw/<workspace>`; inspect it without startup. An existing context is not overwritten or silently renamed. Ask how to proceed if the chosen name exists. Include any needed parent directory creation in the proposed placement.
3. Ask **separate questions** for each unanswered setting: may work update this context without an explicit PCW invocation (`allow_implicit_updates`); must shown knowledge/PROJECT changes wait for approval (`knowledge_approval_required`); enable local Git history (`git_history_enabled`); enable a material token limit, and if so its value (`material_max_tokens`, otherwise null). Explain choices in ordinary language. Do not ask again for supplied values or treat silence as selection.
4. Read the packaged [default instructions](../../pcw_runtime/default_instructions.md). Compose initial INSTRUCTIONS using that one template and the selected settings; compose PROJECT from the user's stated purpose, goals and boundaries. Show the resulting instructions, project text, settings and absolute destination so the agreed creation is concrete. Do not import unapproved facts from chat as knowledge.
5. Call `pcw_workspace_create(request_id, instructions_content, project_content, user_request)` with those exact texts and the user's creation request. Retry identical input with the same request ID. Creation initializes no task and opens no cycle. Verify returned path, settings and independent Git status.
6. If the user also authorized actual work, begin the [work cycle](../pcw/SKILL.md#work-cycle). Otherwise report creation and stop; an empty new context needs no fabricated knowledge, proposal or finish call. Keep the established coordinates for continuation.

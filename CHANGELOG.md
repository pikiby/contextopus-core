# Changelog

## 0.6.0

- Generate material IDs and filenames in MCP; keep the ID unchanged when moving a material.
- Register tasks and complete assignments, bind actual executor sessions, and track delivery, raw-result saving, reading, assessment, and unresolved discrepancies.
- Check actual task-owned files, search preparation, Current, and local memory checkpoints before allowing completion.
- Keep model maps, instructions, and assignment state outside the derived runtime so recovery remains available when runtime storage disappears.
- Close preparation and checkpoint returns through verified, stable service receipts and idempotent repeat delivery.
- Preserve the primary agent's explicit native launches and MCP calls; no environment completion hooks are introduced.

### Upgrade

Refresh the Git marketplace and reinstall using the commands in [README](README.md#update-the-codex-plugin), then start a new Codex thread.

The MCP API changes: `pcw_create` accepts content and optional links without a filename; `pcw_save_subagent_result` requires a registered `assignment_id` instead of an agent-chosen `material_name`. Open a task with `pcw_task_begin`, prepare and bind assignments, and deliver the full assignment before saving returns. Existing knowledge remains readable and is not renamed automatically.

### Verification records

The complete test suite passed 131 tests and 73 subtests, with six opt-in skips and seven warnings. The tests include actual MCP stdio calls, LanceDB, temporary Git checkpoints, recovery, and finite service closeout with injected test vectors. These results do not constitute a new real-model or native-agent workflow check. See the [implementation assessment](docs/implementation-assessment.md).

## 0.5.0

- Add MCP instructions and prerequisite checks for preparing assignments, processing returns, moving between stages, and finishing work.
- Store the primary agent's environment-specific model and reasoning map; require its refresh when the recorded environment changes.
- Save unmodified subagent returns through MCP with UTC timestamps and executor session IDs. Support guarded replacement by revision and idempotent repeat delivery.
- Use filenames as knowledge IDs, with explicit legacy migration and link-preserving rename, move, merge, and deletion operations.
- Keep Current readable in five Markdown sections, including when values contain headings, code, or trailing newlines.
- Define planned and mismatch-triggered factual checks, literal preparation by a separate small model, and completion of memory checkpoints.
- Limit local embedding batches to one text while reusing the loaded Qwen model.
- Add runtime, host, and native-workflow verification, plus separate implementation, regulation, coverage, and search assessments.

### Upgrade

Refresh the configured Git marketplace and reinstall the plugin using the commands in [README](README.md#update-the-codex-plugin). Start a new Codex thread afterward.

UUID-addressed knowledge is migrated only through an explicit `pcw_migrate_legacy_ids` request. Installation preserves existing memory without silently converting it.

### Verification records

Release validation: the plugin manifest validator passed; the test suite passed 121 tests and 73 subtests, with six opt-in skips. All four fresh Codex/MCP checks then passed with the installed 0.5.0 package and cached offline Qwen. Earlier independently assessed native workflows cover the unchanged runtime and agent instructions.

The published assessments describe the checks and their limits. Detailed local traces and snapshots referenced under `.pcw/project-update/.pcw-runtime/verification/` are local evidence, not part of the distributed plugin.

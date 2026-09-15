# Changelog

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

---
name: pcw-run
description: Execute the task prepared in one Persistent Context Workspace current.md through a clean Controller that inherits no prior conversation. Use only when the user explicitly invokes $pcw-run with a natural-language execution request.
---

# PCW Run

Execute an already prepared Current through a clean Controller. Earlier conversation must not rewrite the task.

## Required reading

Read this fixed set completely before working. Do not skip documents or sections based on your own judgment of relevance. Paths are relative to this skill directory; shared references remain inside this plugin's skills root.

- [Shared memory contract](../pcw/references/workspace-contract.md)
- [Execution rules](references/state-machine.md)
- [Shared Reader routing](../pcw/references/agent-routing.md)
- [Resolve workspace](../pcw/references/operations/pcw-resolve-workspace.md)
- [Inspect source](../pcw/references/operations/pcw-inspect-source.md)
- [Checkpoint memory](../pcw/references/operations/pcw-checkpoint-memory.md)

These are instruction references, not separate skills. Stop with `shared_contract_unavailable` if any required document cannot be read completely; do not reconstruct it from memory. Context-authoring instructions are not part of this set.

## Run

1. Resolve the existing workspace with `pcw-resolve-workspace`. This entrypoint does not create missing memory.
2. Start a clean Controller and pass the prepared task exactly as defined by the execution rules.
3. Let the Controller execute within Current's task and authority, using bounded Readers or Workers when needed.
4. The Controller writes durable results directly and uses `pcw-checkpoint-memory` unless the user forbids the local memory commit.
5. Relay the Controller's result, changed targets, blockers, uncertainty, and memory commit id.

The primary agent is the user interface and authority boundary, not another executor or a result-review gate. Do not require it to reread the changed target, compare the result with Current, or approve the Controller's output.

Do not add validation, semantic acceptance, comparison, or tests to the run. Perform such work only when it is part of the explicit user task. Do not create temporary process documents.

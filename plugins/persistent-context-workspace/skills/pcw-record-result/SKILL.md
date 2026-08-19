---
name: pcw-record-result
description: Normalize one accepted Reader, Worker, or explicit user-memory result into the active cycle tmp directory without promoting it to current or knowledge. Internal subskill; use only when loaded by pcw after bounded reading, work, or a remember command.
---

# Record result

Store one verifiable result in a canonical form without treating it as durable knowledge.

## Preconditions

- An active cycle manifest exists.
- The result belongs to that cycle's request and scope.
- The caller accepted the result as usable or explicitly partial, or the result is the exact payload of a `remember` command.

## Inputs

- `workspace` and `cycle_id`.
- A caller-provided stable and unique `result_id`.
- `kind: reader | worker | user`.
- Exact scope and source coordinates.
- Facts, changes, checks, uncertainty, and status.

## Procedure

1. Verify that `cycle_id` matches and scope is allowed.
2. Reject claims without coordinates unless they are verbatim user instructions.
3. Reject an entire copied source offered in place of a result.
4. Normalize the record to the format in `workspace-contract.md`.
5. Write Reader and user results to `tmp/<cycle-id>/findings/<result-id>.md` and Worker results to `work/<result-id>.md`.
6. For `kind: user`, preserve the statement verbatim, identify its exact user-message coordinate, and distinguish an instruction or constraint from an attributed claim about external state.
7. If the id already exists:
   - identical content is a no-op;
   - different content returns `result_id_conflict`.
8. Do not change `current.md`, `knowledge/`, or the Git index.

## Output

Return `output_state: working`, the exact result path, and its `result_id`. Store a receipt at `tmp/<cycle-id>/receipts/pcw-record-result-<result-id>.md`.

## Blockers

- `cycle_mismatch`
- `result_id_missing`
- `result_id_conflict`
- `evidence_coordinates_missing`
- `scope_escape`

## Idempotency

Repeating an identical `result_id` does not change the file. Never append a suffix or create a hidden duplicate for conflicting content.

# Record result

Store one accepted raw result in `tmp/` without treating it as durable knowledge or Current.

## Preconditions

- An active cycle manifest exists.
- The result belongs to that cycle's request and scope.
- The caller accepted it as usable or explicitly partial, or it is exact user-provided meaning.
- A final Controller result has passed primary semantic acceptance against Current's Task lock.

## Inputs

- Workspace, cycle id, and a stable unique result id.
- `kind: reader | controller | worker | user`.
- Exact scope and source coordinates.
- User meaning, facts, changes, checks, uncertainty, and status.

## Procedure

1. Verify that the cycle id matches and scope is allowed.
2. Reject claims without coordinates unless they are exact user-provided meaning.
3. Reject an entire copied source offered in place of a result.
4. Normalize the record to `workspace-contract.md`.
5. For `kind: reader`, require the exact question, claim verdicts, relevance classifications, a compact answer, primary coordinates, out-of-scope findings, conflicts, uncovered scope, and uncertainty. When the Reader used recursive children, accept one merged parent result for the Controller and keep child reports as intermediate cycle material.
6. For a final `kind: controller` result, require:
   - the complete result and changed targets;
   - a mapping from every material change or output section to a `user` outcome or evidenced `derived` necessity;
   - excluded `out_of_scope` findings;
   - executed checks and remaining uncertainty;
   - `semantic_acceptance: passed` with the Current snapshot identity and the primary's Task-lock-based review findings.
7. Reject a final Controller result that has only mechanical checks or whose semantic acceptance was performed without reading the complete changed target.
8. Write Reader and user results to `tmp/<cycle-id>/findings/<result-id>.md`; write Controller and Worker results to `tmp/<cycle-id>/work/<result-id>.md`.
9. For `kind: user`, preserve exact wording and distinguish an instruction, constraint, correction, or revocation from an attributed claim about external state. Never create a user result from an agent-authored correction instruction.
10. If the id already exists, identical content is a no-op and different content returns `result_id_conflict`.
11. Do not change `current.md`, `knowledge/`, or the Git index.

## Output

Return `output_state: working`, the exact result path and id, and store a receipt under `tmp/<cycle-id>/receipts/`.

## Blockers

- `cycle_mismatch`
- `result_id_missing`
- `result_id_conflict`
- `evidence_coordinates_missing`
- `reader_result_shape_invalid`
- `requirement_mapping_missing`
- `semantic_acceptance_missing`
- `semantic_acceptance_failed`
- `scope_escape`

## Idempotency

Repeating an identical result id does not change the file. Never append a suffix or create a hidden duplicate for conflicting content.

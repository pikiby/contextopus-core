# Query context

Read the existing memory needed for a context-editing request. This operation belongs only to `pcw`.

## Inputs

The resolved existing workspace, exact user request, Current, knowledge index, and targeted search capability. Default selection budget: about 2,000 tokens.

## Procedure

1. Remain read-only.
2. Read Current completely to retain the existing task while applying explicit refinements. Reading it for task selection does not authorize rewriting it during a knowledge-only request.
3. Use the knowledge index, Current's links, filenames, relations, and full-text search to locate the requested records.
4. Read relevant records and follow links needed to answer this request. Leave unrelated knowledge outside the selected context.
5. Return the existing task meaning, selected records, available attribution, relevant source coordinates, conflicts, and unresolved choices. Do not turn discovered facts into new task requirements.
6. If required context cannot be read or the task remains materially ambiguous, return the corresponding blocker.

Do not launch an audit, reread written results, or write a selection report to disk.

## Output

Return `output_state: context_selected`, selected knowledge paths, relevant Current meaning, source coordinates, conflicts, and missing information directly to the caller.

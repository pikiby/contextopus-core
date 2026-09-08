# Shared Reader routing

Readers retrieve information for one exact question. They do not audit a whole system, rewrite instructions, invent an operator plan, or turn adjacent facts into task requirements.

## Assignment

Give a Reader:

- the exact current request and one bounded question;
- allowed knowledge links, source paths or coordinates, and explicit non-goals;
- a compact answer format: answer, available source coordinates, relevant links, conflicts, missing information, and uncertainty.

Use a fresh context with no unrelated conversation. Use Luna for literal reading and classification; use Terra for ambiguous regions, cross-file relations, and architectural analysis.

## Retrieval

Start from the links and coordinates supplied with the assignment. Follow relevant active relations; use the knowledge index, filenames, symbols, and full-text search when those entry points are insufficient. Source discovery stays inside the assigned roots.

Read a small precise target directly. For large sources, divide the question into bounded files, objects, sections, or ranges. Include enough adjacent content to keep a split object understandable. Keep working boundaries in agent context, not a map file.

A Reader may delegate bounded subquestions. Each parent merges its children into one compact answer; the caller does not receive every raw child report.

## Result

Return the answer directly. Keep source attribution, scope, modality, time, and uncertainty; an absence in a bounded search is not a system-wide negative. Distinguish requested information, supporting detail, out-of-scope observations, and unresolved choices without turning the result into a separate acceptance report.

Reading sources to answer the assigned question is the work. Do not add a second pass to audit that work, require claim verdicts, or reread every result for acceptance. Perform a review, test, or verification only when that is the user's actual question.

Do not write intermediate reports to disk or run write-capable source commands for a read-only assignment. Do not forward complete large sources where a bounded answer suffices.

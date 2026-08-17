---
name: pcw-map-source
description: Build a lossless temporary navigation map for a large or structurally unknown source after pcw-inspect-source returns decision map. Internal subskill; use only when loaded by persistent-context-workspace for the active cycle.
---

# Map source

Create a temporary complete-source map and adaptive work boundaries without promoting the map to durable knowledge.

## Preconditions

- A `pcw-inspect-source` receipt contains `decision: map`.
- An open `tmp/<cycle-id>/` exists.
- Every Reader receives the original user request.

## Inputs

- The inspection receipt.
- Exact source roots.
- The user task.
- Optional window sizes; for one text file, default to a 64 KiB core and 4 KiB overlap.

## Procedure

1. Select coarse units:
   - project or directory: files and natural containers;
   - table: row ranges with repeated headers;
   - JSON or JSONL: objects or safe byte windows;
   - unknown large file: sequential byte windows.
2. Cover core ranges without gaps or overlap. Add overlap only for boundary detection; never count overlap as separate evidence.
3. Use Luna for simple local format and boundary detection. Route only ambiguous or cross-file regions to Terra.
4. Record each core range's coordinates, format, object starts and ends, neighbor relations, and reread requirement.
5. Merge objects split at boundaries and reread each merged object as one unit.
6. Build adaptive units around events, rows, objects, sections, or files.
7. Write `tmp/<cycle-id>/findings/source-map.md`. Do not filter regions during the first covering pass.
8. Never promote the map to `knowledge/` automatically.

## Output

Return `output_state: source_mapped`, the map path, and:

```yaml
coverage:
  source_units: <count>
  covered_units: <count>
  gaps: []
  boundary_repairs: []
```

`gaps` must be empty for `status: ok`.

## Blockers

- `inspection_not_map`
- `coverage_gap`
- `boundary_unresolved`
- `reader_failure`
- `source_changed_during_mapping`

## Idempotency

Reuse matching units for the same source snapshot and never duplicate the map. If the source changed, return `source_changed_during_mapping` instead of mixing versions.

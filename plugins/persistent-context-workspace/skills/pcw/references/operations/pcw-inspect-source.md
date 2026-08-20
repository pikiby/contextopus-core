# Inspect source

Choose a reading strategy without full analysis and without changing either source or memory.

## Preconditions

- The workspace and cycle are open.
- The original request and exact source roots are available.

## Inputs

- `workspace` and `cycle_id`.
- The verbatim user task.
- One or more source roots.
- Optional thresholds from the cycle manifest.

## Procedure

1. Use cheap operations: `rg --files`, metadata, extensions, sizes, signatures, headers, and small samples.
2. During inspection, read no more than 64 KiB of samples from one file; sample the beginning, middle, and end only when needed.
3. Identify formats, natural coordinates, and targeted searchability.
4. Return `decision: direct` when targeted search or natural boundaries can cover the request without loading a substantial share of the source.
5. Return `decision: map` when any condition holds:
   - one unstructured file is larger than 256 KiB;
   - unknown or mixed-format material exceeds 1 MiB;
   - a broad request covers roughly 1,000 or more project files;
   - object boundaries cannot be determined reliably by a cheap pass;
   - direct reading is expected to exceed the context budget.
6. For a narrow request in a large codebase, prefer `direct` with `rg` when symbols or paths are precisely addressable.
7. Write nothing.

## Output

Return the standard envelope with `output_state: source_inspected` and:

```yaml
inspection:
  decision: direct | map
  source_types: []
  coordinate_system: line | byte | row | object | path
  estimated_scope: <files-and-bytes>
  reasons: []
  direct_queries: []
```

## Blockers

- `source_missing`
- `source_unreadable`
- `unsupported_remote_source`
- `scope_not_bounded`

## Idempotency

Create no files. Return the same decision and rationale when sources, request, and thresholds are unchanged.

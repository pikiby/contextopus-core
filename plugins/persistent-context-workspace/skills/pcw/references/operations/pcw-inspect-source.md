# Inspect source

Select a bounded reading strategy when the current request needs source information. Do not change source or memory.

## Inputs

The resolved workspace, exact request, and allowed source roots or coordinates.

## Procedure

1. Use targeted `rg`, file metadata, extensions, headers, and small samples to locate the requested material.
2. Sample no more than 64 KiB from one file during this initial inspection.
3. Use `decision: direct` when named files, symbols, objects, or sections make the answer directly addressable.
4. Use `decision: readers` for broad or ambiguous material. Divide the question into bounded assignments under the shared Reader routing rules; return their merged answer in working context.
5. A narrow request does not require scanning an entire large repository. Do not produce a full-source map or persist intermediate reports.
6. Return missing or unreadable sources as blockers, rather than inventing their content.

## Output

Return `output_state: source_inspected`, `decision: direct | readers`, source types, natural coordinates, and bounded entry points. No files are produced.

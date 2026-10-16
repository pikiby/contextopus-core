# Search scope and result selection

Core and Workspace use one selection registry. Structural eligibility filters run before vector nearest-neighbor retrieval. The selected algorithm then cuts or pages that eligible candidate pool. `output: "materials"` returns one representative excerpt per document key; `output: "fragments"` retains selected fragments. A key is `[module, collection, object_id]`; Workspace collections are context names.

Selecting another context as evidence does not activate its instructions. Workspace cross-context search uses the active context's search settings; `diagnostics.scope.settings_context` identifies that settings scope. `scope.contexts` identifies the contexts actually searched. Core can restrict `module` and `collection` separately. A null scope field means no restriction for that field.

## Installed algorithms

These are engineering defaults, not calibrated relevance guarantees. Distances are ranking measurements, not confidence scores. Inspect `core.algorithms` for the installed descriptions and parameter schemas.

| Algorithm | Parameters and defaults | Selection order |
| --- | --- | --- |
| `distance_jump` | `N: 20`, `d_max: 0.8`, `min_jump: 0.02`, `multiplier: 3.0` | Nearest N fragments → distance cap → first large gap → document deduplication for material output. |
| `distance_threshold` | `N: 20`, `d_max: 0.8` | Nearest N fragments → distance cap → optional material deduplication. |
| `nearest_n` | `N: 20` | Nearest N fragments → optional material deduplication. |
| `none` | `offset: 0`, `page_size: 20` | Distance-ordered page, without a relevance cut → optional material deduplication. |
| `archivist` | `d_max: null`, `top_k: 20` | Group document keys → optional distance cap → upper-median first jump → weak plateau cut → top_k last. |

For `distance_jump`, at least three candidates must remain after the distance cap. The first gap at least `max(min_jump, median(positive gaps) * multiplier)` cuts the tail. This uses Python's arithmetic median: an even-sized set averages its middle pair. Equal distances do not contribute positive gaps. Empty, short or flat sets can therefore have no jump. Legacy `N`, `d_max`, `min_jump` and `multiplier` retain this order, including deduplication after the cut. More fragments from one document can consume several N slots, so material output can contain fewer than N documents.

`archivist` preserves the compared Archivist procedure with a Contextopus identity adaptation. It groups by document key before cuts, retaining the nearest representative. Repository/location families and default-branch preference are not inferred by Core; a module owns such domain rules. Its first jump uses the **upper median** positive gap times 3, with a minimum of 0.02. If more than three representatives remain, the weak-plateau pass uses `head = median(first three distances)` and `delta = max(0.02, median(positive gaps) * 2)`; this second median is the arithmetic median. Starting at index 2, it cuts before the first candidate whose distance exceeds `head + delta` and whose preceding local gap is below 0.01. `top_k` applies after both passes. With `d_max: null`, no absolute distance cap applies. For example, distances `[0.10, 0.11, 0.12, 0.60, 0.61, 0.62]` retain the first three; `[0.10, 0.11, 0.13, 0.15, 0.151, 0.152]` retain the first four through the weak-plateau rule. Grouping happens even when fragment output is requested, so this algorithm returns one representative per document.

For inspection, `none` pages the candidate fragments before material deduplication. Request fragment output when every page position matters. Stable pagination assumes the same indexed corpus and ranking; index changes or tied distances can change later pages.

## Configuration and origins

The common configuration object is:

```json
{
  "selection": {
    "algorithm": "distance_jump",
    "parameters": {
      "N": 20,
      "d_max": 0.8,
      "min_jump": 0.02,
      "multiplier": 3.0
    }
  }
}
```

Settings merge in this order:

1. Built-in defaults, with explicit migration of the active index's legacy search settings.
2. `<root>/core/configuration/settings.json`.
3. `<root>/core/configuration/modules/<module>.json`.
4. `<root>/core/configuration/contexts/<module>/<context>.json`.
5. Request overrides.

Partial parameters inherit only within the same algorithm. Switching `algorithm` clears parameters inherited for the previous algorithm and uses the new algorithm's defaults. Unknown algorithms or parameters, invalid types, nonfinite numbers and out-of-range values fail validation. A module's custom algorithm uses its declared JSON schema.

`core.settings` returns effective `values`, individual `sources`, and a revision. Selection origins use keys such as `selection.algorithm` and `selection.parameters.N`; examples include `algorithm.default`, `root.active_index`, `root.configuration`, `module.configuration`, `context.configuration`, and `request`. Legacy aliases include `searchN → N` and `distance → d_max` where the selected algorithm supports them. A modern parameter explicitly supplied in the same configuration layer wins over its legacy alias. Search-time legacy arguments appear as `request.legacy`.

Save changes through `core.settings_preview` followed by `core.settings_apply` with the exact `preview_revision`. The revision binds the configuration scope and `request_only` mode. A stale preview must be regenerated. `request_only: true` returns effective request settings without saving them. Supplying `selection` directly to a search also affects only that request.

Prefer algorithm parameters in new clients. Legacy Workspace `N`, `d_max`, `min_jump`, and `multiplier` are accepted only when supported by the selected algorithm. Core's legacy `distance` requires a `d_max` parameter; Core's legacy `limit` maps to `N`, or `page_size` for `none`. For `archivist`, use `selection.parameters.top_k` explicitly.

## Diagnostics and limits

Search responses expose the algorithm identifier/version, effective settings and their origins, eligibility scope, boundary reason, deduplication order and count units:

- `eligible_documents` and `eligible_fragments`: indexed data allowed by the structural filters, before nearest retrieval.
- `considered_fragments`: finite-distance candidate rows submitted to selection.
- `selected_fragments`: candidate representatives kept by the algorithm before material-output deduplication.
- `selected_materials`: distinct document keys among those representatives.

The older `eligible`, `considered` and `selected` fields remain compatibility aliases. Use the explicit unit fields for comparisons: the compatibility `eligible` field counts fragments in Core and documents in Workspace.

By default, nearest retrieval considers the full eligible pool. An explicit `candidate_limit` caps retrieval independently of the algorithm; allowed values are 1–100000. `limits.nearest` reports that cap, and `candidate_pool_truncated` reports whether eligible fragments were omitted. The metadata candidate snapshot retains at most 1000 rows; `limits.candidate_snapshot` reports that bound, and `truncated` reports snapshot truncation. Neither flag describes the normal algorithm cut or pagination.

Candidate snapshots contain keys, revisions, fragment indices, distances, input positions and selected flags. They omit source bodies and vectors. `nearby_rejected` contains up to five rejected candidate metadata rows. Read the source material before treating a search candidate as verified evidence. Search history and counterfactual replay have separate evidence limits described in [Search analysis](search-analysis.md).

## Catalog and module providers

`core.algorithms` lists descriptions or finds an exact identifier; non-exact text queries filter the description text. `semantic: true` searches derivative algorithm cards in the common RAG index under module `core`, collection `search_algorithm`. That search fixes `nearest_n` internally and restricts eligibility to the catalog, avoiding recursive algorithm selection. Document include/exclude patterns do not hide catalog cards.

Run `core.algorithms_refresh` explicitly to index changed descriptions and remove cards for algorithms no longer registered. A semantic query with missing or stale representations returns `catalog_state: "missing"` or `"stale"` and `next_action: "core.algorithms_refresh"`; the query does not refresh them. Exact catalog inspection needs no embeddings.

A provider directory contains `algorithm.py` exporting `select(rows, parameters)` and `description.json` declaring `id`, `version`, `purpose`, `parameters_schema`, `defaults`, `when_to_use`, and `how_to_adjust`. The function receives distance-ordered candidate dictionaries and returns `(kept_rows, boundary_metadata)`. Keep selection deterministic, retain candidate identity, and handle empty input. Use the shipped [algorithm guide](../src/contextopus/resources/base_context/algorithm-guide.md) and template for the complete example.

A module declares its relative `filter_algorithms` path inside its package. Discovery reads contracts; provider code is loaded only for an enabled module whose current package fingerprint matches its prepared fingerprint. A disabled or changed unprepared package contributes no algorithm. Loaded providers are cached for the current fingerprint; malformed providers are isolated from the remaining registry. Explicit module preparation/enablement and catalog refresh are separate operations.

## Repair an unavailable configured algorithm

Disabling a module, changing its package without preparing/enabling it again, or removing its provider can make a saved selection unavailable. `core.settings` preserves that selection and reports `selection_status.valid: false`, `code: "algorithm_unavailable"`, and `next_action: "core.settings_preview"`. Search with the unchanged saved selection fails; no builtin is substituted silently.

Inspect settings at the same module/context scope where the selection was configured. An explicit builtin `selection` in a search request works without changing the saved configuration. To repair it persistently, preview a replacement such as `{"selection":{"algorithm":"nearest_n","parameters":{"N":20}}}` at that configuration scope, then apply the returned revision. Enabling the original prepared module is another explicit repair path. Disabled provider code is not loaded to inspect or replace its settings.

Preview revisions include the available algorithm descriptions. If a provider is enabled, disabled, or changed between preview and apply, regenerate the preview rather than applying the old revision.

## MCP examples

Use `contextopus_query` for reads and `contextopus_execute` for writes. Replace the root/context values with the selected coordinates.

Inspect an exact algorithm without loading embeddings:

```json
{"operation":"core.algorithms","arguments":{"query":"archivist"},"work_root":"/path/to/root"}
```

Search one Workspace context with a request-only selection override:

```json
{"operation":"workspace.search","arguments":{"query":"release conditions","selection":{"algorithm":"nearest_n","parameters":{"N":5}}},"work_root":"/path/to/root","context":"project-a"}
```

Inspect a page of fragments across explicitly chosen contexts:

```json
{"operation":"workspace.search","arguments":{"query":"release conditions","categories":["project-a","project-b"],"output":"fragments","selection":{"algorithm":"none","parameters":{"offset":20,"page_size":20}}},"work_root":"/path/to/root","context":"project-a"}
```

Search another module's collection through Core:

```json
{"operation":"core.search","arguments":{"query":"release conditions","module":"example","collection":"reference","selection":{"algorithm":"archivist","parameters":{"d_max":null,"top_k":5}}},"work_root":"/path/to/root"}
```

Preview a persistent context setting, then pass the returned revision to the execute tool:

```json
{"operation":"core.settings_preview","arguments":{"module":"workspace","context":"project-a","changes":{"selection":{"algorithm":"distance_threshold","parameters":{"N":40,"d_max":0.6}}}},"work_root":"/path/to/root"}
```

```json
{"operation":"core.settings_apply","arguments":{"preview_revision":"<returned-preview-revision>"},"work_root":"/path/to/root"}
```

Refresh the semantic catalog with the execute tool, then search it with the query tool:

```json
{"operation":"core.algorithms_refresh","arguments":{},"work_root":"/path/to/root"}
```

```json
{"operation":"core.algorithms","arguments":{"query":"retain a close cluster and cut a weak tail","semantic":true,"limit":3},"work_root":"/path/to/root"}
```

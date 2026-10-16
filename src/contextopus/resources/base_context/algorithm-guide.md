# Creating a retrieval selection algorithm

A selection algorithm receives ranked nearest-neighbor candidates after structural filters. It chooses a bounded result set; it does not change embeddings, source data or active instructions. Configure selection through the shared Core settings and registry.

Inspect the installed algorithm manifest and interface before implementing. Declare a stable identifier, version, purpose, parameter schema, defaults and usage guidance. Keep selection deterministic for identical candidates and parameters. Empty input, equal distances, missing distances and short candidate lists need defined behavior.

Example: a distance-jump selector keeps the closest group before an unusually large increase in distance. It should still obey the requested upper result bound and preserve ranked order. Compare it using fixed query fixtures and relevant source results, not only timing or synthetic distance arrays.

A configuration preview should display the algorithm and effective parameters. Applying it requires the exact preview revision. Request-level overrides remain scoped to that request.

An enabled module's `filter_algorithms` directory supplies algorithm subfolders, each with `description.json` and `algorithm.py`. A minimal descriptor is:

```json
{"id":"sample_first","version":"1.0.0","purpose":"Keep the first ranked candidates","parameters_schema":{"type":"object","properties":{"N":{"type":"integer","minimum":1,"maximum":1000}},"additionalProperties":false},"defaults":{"N":20},"when_to_use":"Fixed nearest window","how_to_adjust":"Change N"}
```

```python
# algorithm.py

def select(rows, parameters):
    kept = rows[:parameters["N"]]
    return kept, {"reason": "nearest_window"}
```

The shared registry validates `parameters_schema` and `defaults`, loads `select(rows, parameters)`, and supplies distance-ordered candidates. The selector returns `(kept_rows, boundary_metadata)`. Choose it through `selection: {"algorithm":"sample_first","parameters":{"N":20}}` in shared settings or a scoped search request. An enabled module contributes this provider through its manifest's `filter_algorithms` path.

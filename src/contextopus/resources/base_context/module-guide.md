# Creating a Contextopus module

A module contributes a domain adapter and operations to the common Core. It uses the shared index, operation registry, configuration and analytics instead of building a competing search store. Existing Workspace records remain governed by Workspace instructions and proposals.

Inspect installed module manifests and `describe` before implementation. Provide a `module.json` manifest, handler files under `package/`, and operation schemas. Registration should be passive: discovery must not load a model, install packages, run background jobs or change data. Enable a module only through an explicit action. Inspect module compatibility before enabling or updating code.

Example: the shipped `examples/modules/synk` module registers a bounded version query that reads an installed command without starting synchronization. Its handler receives one arguments dictionary and returns JSON. A module that needs indexing must use Core's supported source-adapter integration; the operation manifest alone does not register a new document store.

Document lifecycle, update compatibility, data locations, ownership of writes, recovery and meaningful validation. Test that disabled module imports and status queries cause no side effects.

A minimal root-local release has `module.json` beside `package/adapter.py`:

```json
{"id":"sample","version":"1.0.0","core_requires":">=1.2,<2","operations":[{"name":"sample.status","kind":"query","handler":"adapter.py:status","arguments_schema":{"type":"object","additionalProperties":false}}]}
```

```python
# package/adapter.py

def status(arguments):
    return {"available": True}
```

Handlers receive one dictionary and return JSON-compatible output in a child interpreter. Install under `<root>/modules/sample`, then use `core.module_prepare(module="sample")`, `core.module_enable(module="sample")` and query `sample.status`. Mutable state belongs in `data/` and `config/`. Preparation and enabling authorize trusted code execution; this is not an operating-system sandbox. Optional manifest keys `procedures`, `skills` and `filter_algorithms` name directories relative to `package/`.

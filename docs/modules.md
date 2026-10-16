# Root-local modules

Copy a module directory into `<root>/modules/<id>`. Discovery reads `module.json`
without importing code or installing dependencies. Existing built-in workspace
storage and Python entry points retain their current layout and behavior.

A release consists of `module.json` and `package/`. Mutable user files live in
`data/` and `config/`, alongside the package. Updates never replace those paths.
Core stores desired enablement and prepared content digests under
`core/configuration/modules.json`, so rebuilding the application retains state.

```json
{
  "id": "sample",
  "version": "1.0.0",
  "core_requires": ">=1.2,<2",
  "dependencies": {"python": []},
  "operations": [{
    "name": "sample.status",
    "kind": "query",
    "handler": "adapter.py:status",
    "arguments_schema": {"type": "object", "additionalProperties": false}
  }],
  "procedures": "procedures",
  "skills": "skills",
  "filter_algorithms": "filter_algorithms",
  "tui": "sample.open_tui"
}
```

IDs use lowercase letters, digits, underscores and hyphens, starting with a
letter. Versions and `core_requires` use PEP 440. Every operation name must start
with the module ID and a dot. Paths are relative to `package/` and cannot escape
it. Provider directories are exposed only for enabled modules through
`app.module_manager.sources(id, kind)`. Procedure `sample/setup` reads
`package/procedures/setup.md`; skills and filter algorithms retain their provider
file contracts. `tui` names an operation contributed by the module.

Python handlers receive one arguments dictionary and return JSON-compatible data.
They run in a child Python interpreter. Dependencies are prepared explicitly with
`uv venv` and `uv pip install`; each release owns its `.venv`, so a failed
upgrade cannot mutate the previous release environment. Repeated preparation
reuses that environment. Dependency-free handlers use Core's interpreter.
A non-Python operation supplies `command: ["executable", "argument"]` instead of
`handler`. Commands read one JSON object on stdin and return JSON on stdout.
Both adapters receive `CONTEXTOPUS_ROOT`, `CONTEXTOPUS_MODULE_DATA` and
`CONTEXTOPUS_MODULE_CONFIG`; stdout must contain only the JSON response.
Preparation and enablement authorize trusted module execution; this is not an OS
sandbox. Command executables must already exist on PATH or be bundled.

All interfaces use the same operations:

- Query `core.modules` lists `discovered`, `prepared`, `enabled`, `incompatible`
  and `error` states.
- Execute `core.module_prepare` with `module` validates compatibility and prepares
  native Python dependencies. It does not import handlers.
- Execute `core.module_enable` with `module` atomically registers the complete
  operation contribution. Changed packages require preparation again.
- Execute `core.module_disable` removes contributed operations and persists that
  choice.
- Execute `core.module_update` with `module` and `source` stages an unpacked local
  release, checks its manifest and publishes an atomic `.current.json` release pointer.
  Previous releases remain in `.releases/`; preparation failures restore the old
  pointer and previous enablement. The original package remains available when
  rolling back the first managed update. An interrupted enablement can be retried
  using prepare and enable. No update downloads or live computer installation is
  implied.

`examples/modules/synk` supplies a generic adapter that reads the installed
`codex-sync --version` or `contextopus-synk --version` and never starts sync.
Copy it into the root module directory, prepare, enable and query `synk.version`.

The CLI offers `contextopus --root ROOT modules` and subcommands
`modules prepare ID`, `modules enable ID`, `modules disable ID`, and
`modules update ID --source RELEASE_DIRECTORY`. These commands use the same
root-owner service operations as MCP. The dashboard's Modules page offers the
same actions; Update opens a path input (Escape cancels). Enabled modules with a
`tui` operation expose Open, which runs the returned `argv` while suspending the
parent display. Built-in workspace lifecycle remains managed by Core.

Applications for different contexts sharing a root reconcile persisted module
state before registry description and dispatch. Enabling, updating or disabling
through one context therefore updates the operations available to another on its
next request; dispatch validates the refreshed schema under the root lock.

Native integration includes enabled, fingerprint-current module skills when a
root is supplied (`plan(..., root=ROOT)`; CLI `integrate` uses its selected root).
Each `package/skills/<skill-name>/` must contain `SKILL.md`; supporting text and
binary files are copied with it. Skill names must not collide with built-ins or
other modules. Installation, update and removal happen through the usual explicit
integration preview/apply, including native Codex plugin integration. Config-only
integration copies no skills. A later integration plan removes unchanged managed
files belonging to disabled or removed module skills, and preserves files the
user modified. Enabling a module alone does not write into native client folders.

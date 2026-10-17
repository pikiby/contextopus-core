# Root-local modules

Copy a module directory into `<root>/modules/<id>`. Discovery reads `module.json`
without importing code or installing dependencies. One shared Core operation
handles installation; listing modules does not prepare dependencies, apply
migrations or execute handlers.

A release consists of `module.json` and `package/`. Mutable user files live in
`data/` and `config/`, alongside the package. Updates never replace those paths.
Core stores desired enablement and prepared content digests under
`core/configuration/modules.json`, so rebuilding the application retains state.

```json
{
  "id": "sample",
  "version": "1.0.0",
  "core_requires": ">=1.3,<2",
  "dependencies": {"python": []},
  "storage": {
    "engine": "sqlite",
    "schema_version": 1,
    "migrations": "migrations",
    "compatible_versions": {"min": 1, "max": 1}
  },
  "operations": [{
    "name": "sample.status",
    "kind": "query",
    "handler": "adapter.py:status",
    "arguments_schema": {"type": "object", "additionalProperties": false}
  }]
}
```

IDs use lowercase letters, digits, underscores and hyphens, starting with a
letter. Versions and `core_requires` use PEP 440. Every operation name must start
with the module ID and a dot. Paths are relative to `package/` and cannot escape
it. Optional `procedures`, `skills` and `filter_algorithms` name provider
directories. These are exposed only for enabled modules through
`app.module_manager.sources(id, kind)`. Procedure `sample/setup` reads
`package/procedures/setup.md`; skills and filter algorithms retain their provider
file contracts. `tui` names an operation contributed by the module.

Legacy Python handlers receive one arguments dictionary and return
JSON-compatible data.
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

## One installation action

Once the author has placed the package in `<root>/modules/<id>`, ask `$m` to
install that module. The skill reads `guide(procedure="modules")` and calls the
shared operation. An explicit request to install authorizes the declared
installation sequence; inspection alone does not.

All interfaces use the same operations:

- Query `core.modules` lists lifecycle states, including `storage_pending` when
  declared migrations await installation, and reports compatibility and errors.
- Execute `core.module_install` with `module` prepares dependencies, applies the
  declared storage migrations and enables operations. Retry the same operation
  after resolving an installation failure.
- Execute `core.module_prepare` with `module` validates compatibility and prepares
  native Python dependencies without applying storage migrations or importing
  handlers.
- Execute `core.module_enable` with `module` atomically registers the complete
  operation contribution. Changed packages require preparation again; pending or
  incompatible storage blocks enablement. This low-level action does not migrate
  storage.
- Execute `core.module_disable` removes contributed operations and persists that
  choice.
- Execute `core.module_update` with `module` and `source` stages an unpacked local
  release, checks its manifest and publishes an atomic `.current.json` release pointer.
  Previous releases remain in `.releases/`; dependency or migration failures restore
  the old release pointer. Storage compatibility is checked before activation;
  incompatible previous code is not reported as enabled after a schema change.
  The original package remains available when rolling back the first managed update. An interrupted enablement can be retried
  using Install. No update downloads or live computer installation is
  implied.

`examples/modules/synk` supplies a generic adapter that reads the installed
`codex-sync --version` or `contextopus-synk --version` and never starts sync.
Copy it into the root module directory, install it and query `synk.version`.

The CLI offers `contextopus --root ROOT modules` and subcommands
`modules install ID`, `modules disable ID`, and
`modules update ID --source RELEASE_DIRECTORY`. These commands use the same
root-owner service operations as MCP. The dashboard's Modules page offers
Install, Update and Disable; Update opens a path input (Escape cancels). Enabled
modules with a
`tui` operation expose Open, which runs the returned `argv` while suspending the
parent display. Low-level CLI `prepare` and `enable` remain available for diagnosis.
Built-in workspace lifecycle remains managed by Core.

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

## Authoring structured storage

Core owns the ordinary relational catalog at `<root>/core/storage/modules.sqlite3`.
A module declares its schema and migrations in `module.json`; the installer
creates the catalog, applies migrations and records versions. There is no manual
SQL installation step and no module-specific database connection in handlers.
User files continue to belong in `data/` and `config/`. Domain tables hold
structured records; the shared RAG index holds searchable material and remains a
separate Core service. A module does not create a private vector database.

`storage` is optional. Its SQLite contract declares the desired integer
`schema_version`, a migration directory relative to `package/`, and inclusive
`compatible_versions.min`/`max`. Supply one ordinary SQL file per version,
numbered continuously from `001-name.sql` (underscore separators are also
accepted) through the target version. Core replaces `{{module}}` with the
validated module ID. Quote names such as `"{{module}}::sessions"` and
`"{{module}}::messages"`, including indexes and other schema objects. Foreign
keys and joins between the module's tables are supported.

Core validates migration identity and applies pending files transactionally.
Previously applied migration files must retain their contents. Declare the schema
versions the code actually supports; a package cannot use an incompatible schema.
Core rejects cross-module table access, `ATTACH`, direct `PRAGMA`, extension
loading and transaction management in module SQL. DDL belongs in packaged
migrations; runtime writes use DML through registered execute operations. These
checks constrain SQL access, while the installed package remains trusted code.

An operation that needs storage declares `"protocol": "contextopus-core-v1"`.
Its Python handler takes `(arguments, core)` and returns JSON-compatible output:

```python
def sessions(arguments, core):
    return core.storage.query(
        'SELECT id, title FROM "{{module}}::sessions" ORDER BY id'
    )

def save(arguments, core):
    return core.storage.execute(
        'INSERT INTO "{{module}}::sessions" (id, title) VALUES (?, ?)',
        [arguments["id"], arguments["title"]],
    )
```

`query(sql, parameters=())` returns `{"columns": [...], "rows": [{...}]}`;
`execute(sql, parameters=())` returns `{"rowcount": ..., "lastrowid": ...}`.
Parameter values travel separately from SQL. Query operations cannot invoke
storage writes. The Core parent process owns the connection and serializes
mutations; child handlers receive the storage bridge and no connection or catalog
path. Legacy one-argument handlers keep their original protocol.

Non-Python commands may declare the same protocol. Stdout carries newline-delimited
JSON only, with logs on stderr. Core sends a `request` containing `protocol`,
`arguments`, `module` and `kind`. The child sends a `call` with `id`,
`method` (`storage.query` or `storage.execute`) and `arguments` (`sql` and
`parameters`); Core replies with `return`, the same `id`, and `result` or
`error: {"type": ..., "message": ...}`. Finish with
`{"type":"result","result":...}` or
`{"type":"error","error":{"type":...,"message":...}}`.

## Runnable catalog example

The repository's `examples/modules/catalog-demo` is a complete dependency-free package.
Copy that folder into an isolated root's `modules/`, then run:

```console
contextopus --root ROOT modules install catalog-demo
contextopus --root ROOT execute catalog-demo.session_put --arguments '{"id":"s1","title":"Example session"}'
contextopus --root ROOT execute catalog-demo.message_put --arguments '{"id":"m1","session_id":"s1","body":"A linked message"}'
contextopus --root ROOT query catalog-demo.sessions
contextopus --root ROOT query catalog-demo.messages --arguments '{"session_id":"s1"}'
```

Its single packaged migration creates two ordinary linked tables and an index.
The operations demonstrate inserts, updates, a foreign key, a join and aggregation
through Core. The example is a generic catalog and has no dependency on session
search daemons. Repeating Install keeps existing rows; disabling retains them.

# Root-local modules

Copy a module directory into `<root>/modules/<id>`. Discovery reads `module.json`
without importing code or installing dependencies. One shared Core operation
handles installation; listing modules does not prepare dependencies, apply
migrations or execute handlers.

A release consists of `module.json` and `package/`. Mutable user files live in
`data/` and `config/`, alongside the package. Updates never replace those paths.
Core stores desired enablement and prepared content digests under
`core/configuration/modules.json`, so rebuilding the application retains state.

Modules with Markdown records can use the shared child `core.documents` API for
scoped files, revision checks and reconciliation plans. Shared instruction bodies
live in `core/instructions/` and are selected through YAML wikilinks, rather than
copied into each module. See [file documents](implementation/file-document-sources.md)
and [instruction operations](instruction-library.md). SQL and RAG remain derived
views for these file-backed records; modules with other source types retain their
own ingestion procedure.

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
`modules install ID --source PATH`, `modules disable ID`, and
`modules update ID --source RELEASE_DIRECTORY`. These commands use the same
root-owner service operations as MCP. The dashboard's Modules page offers
Install, Update and Disable; Update opens a path input (Escape cancels). Enabled
modules with a
`tui` operation expose Open, which runs the returned `argv` while suspending the
parent display. Low-level CLI `prepare` and `enable` remain available for diagnosis.
Workspace is distributed separately as an ordinary root-local module. Core
starts with no Workspace operations, project rules, domain storage or reference
documents. Its built-in `m` skill manages installation; the six `w` skills are
provided by an enabled Workspace package.

### Install a built folder or ZIP

Core 1.5 accepts a trusted built folder or a ZIP whose root (or single `ID/`
folder) contains `module.json` and `package/`. Root licenses, documentation and
installer wrappers are copied with the code. Source checkouts containing `.git`,
caches, environments or live state must be built first.

```console
contextopus --root ROOT modules install ID --source /path/to/module.zip --plan
contextopus --root ROOT modules install ID --source /path/to/module.zip
```

The first command validates and fingerprints the payload without staging it or
running module code. The second prints that preview, copies checked bytes into
a temporary folder, validates the complete manifest, then uses normal dependency,
storage, installation-hook and activation steps. Installing executes trusted
module code and can resolve declared dependencies; checksums are not a sandbox.
Unsafe paths, duplicate/case-colliding names, symlinks, oversized payloads,
identity mismatches and changed source bytes are rejected. ZIP limits are 10,000
entries, 256 MiB per file and 512 MiB of uncompressed files.

The source command returns exit code 0 only after an enabled result, and 2 on
failure. An existing module folder or lifecycle record is never overwritten by
`install --source`. Updates remain explicit: build/unpack the replacement and
use `modules update ID --source RELEASE_DIRECTORY`; data and configuration are
retained. Failed first installs retain their files/state for diagnosis. After
review, retry `modules install ID` without `--source`.

MCP/API clients query `core.module_source_plan` with `module` and `source`, then
execute `core.module_install` with the same coordinates and its `revision` as
`source_revision`. Source changes invalidate the preview. The existing
`core.module_install` call with only `module` still installs an already-placed
folder. Native client skills are refreshed separately with `integrate CLIENT
--user --apply`; reload the client afterwards.

## Optional Workspace package

The Core wheel contains infrastructure only. The separate
`contextopus-workspace-VERSION.zip` contains `workspace/module.json` and
`workspace/package/`. Install the verified ZIP with the same action as any
other module:

```console
contextopus --root ROOT modules install workspace --source /path/to/contextopus-workspace-1.5.0.zip
```

This explicit installation applies Workspace-owned storage preparation before
publishing its operations, settings, procedures and RAG source. Existing domain
data is retained. A package's presence or a restarted Core does not authorize
migration. Disable removes its contributions while preserving its files and
records; update uses `core.module_update` and retains the previous release.
Client integration remains a separate explicit preview/apply operation and reads
the enabled package's skill manifest. Core client bundles contain only `m`;
Workspace contributes its six `w` skill entrypoints after installation.

Workspace source, its builder, tests and ZIP belong to the independent
[contextopus-workspace repository](https://github.com/pikiby/contextopus-workspace).
Use the [Workspace 1.5.0 release](https://github.com/pikiby/contextopus-workspace/releases/tag/v1.5.0)
or follow that repository's build instructions. Version 1.4.0 belongs to the
earlier combined distribution.

## Trusted in-process contributions

A module can declare `contribution` instead of child operations or a service:

```json
{
  "id": "sample",
  "version": "1.0.0",
  "core_requires": ">=1.5,<2",
  "contribution": {
    "factory": "sample/__init__.py:register",
    "requires": ["contextopus-core>=1.5,<2"]
  }
}
```

Core loads this trusted factory in its own interpreter, in a package namespace
bound to the root and release fingerprint. Native requirements must already be
installed in that interpreter; a private module environment cannot supply them.
This mode has the same trust as installed Core Python code and is useful when a
module needs direct access to Core's shared in-process services. Workspace uses
this mode; Session Search uses the persistent child-service mode below. Both use
the same discovery, install, enable, disable, update and restart lifecycle.

The factory registers module-prefixed operations, aliases, procedures, settings
providers, its own RAG source and lifecycle hooks through the contribution host.
Core checks conflicts before publishing the complete registration. Explicit
installation runs paired `install_prepare` and `install_apply` hooks: preparation
returns a revision, and apply receives that revision. Read-only `ready` hooks
gate activation and restart; ordinary discovery or restart never runs migration
hooks. Module-owned migrations must preserve sources and support retry after an
interruption. Shared SQL and RAG remain Core services with separate commits.

Disable and update revoke new admission and drain admitted native calls before
running cleanup; nested Core requests retain the admitted contribution snapshot.
Self-disable defers cleanup until that call exits. Close failures are reported
after remaining contributions and owned Core resources are released. A failed
candidate cannot supply callbacks to the restored release. Profile rebuilding
accepts at most one module owner, checked before any rebuild callback executes.

### Replacing a compatibility adapter

An application can explicitly register a replaceable compatibility adapter;
Core does not automatically discover an external Session Search executable.
The generic adapter API can, for example, expose an existing external indexer.
A folder package may use that adapter's ID; placing it in `modules/` does not
change an explicitly registered active implementation.

Use the ordinary Install action to switch. Core prepares dependencies and
storage, starts the declared service and checks readiness before saving folder
ownership and replacing the adapter's complete operation contribution. Failed
first preparation or startup leaves the adapter available. The original program
and its data are not removed or imported by this switch.

If enablement runs without a service owner, Core reports `activation_pending`.
The adapter remains active until an owner starts the candidate successfully.
Inspection does not start a child. Once folder ownership is saved, it survives
restart; disabling or breaking that module does not silently restore the old
adapter. Retry a failed candidate explicitly with Install or Enable.

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

Core keeps each module's relational records in a separate SQLite file at
`<root>/core/storage/modules/<module-id>.sqlite3`.
A module declares its schema and migrations in `module.json`; the installer
creates its file, applies migrations and records versions. There is no manual
SQL installation step and no module-specific database connection in handlers.
User files continue to belong in `data/` and `config/`. Domain tables hold
structured records; the shared RAG index holds searchable material and remains a
separate Core service. A module does not create a private vector database.
Models and embedding providers also remain shared Core services.

Core uses a separate writer lock for each module file, so a transaction or SQL
write in one module does not hold another module's writer lock. SQLite still
allows one writer at a time within each file. The root guard handles short write
admission; relocation holds it while draining active module writes, then retains
the database locks through the verified copy and routing switch. Keep SQL
transactions short. There is no transaction spanning module files or SQL and RAG.

If the older `core/storage/modules.sqlite3` catalog exists, only an explicit
Core storage apply or module installation partitions its tables and migration
ledgers into module files. Inspection, preparation and queries do not migrate it.
Core retains the legacy source and a durable recovery backup; interrupted
partitioning can be resumed by the same explicit operation.

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
storage writes. The Core parent process owns database connections and coordinates
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

## Persistent services (local source extension)

This extension is being developed locally; it does not describe a published
release or confirm the capabilities of an installed Core. See the complete
[contract and session-search handoff](implementation/module-services-local.md).

Declare `service: {"factory":"worker.py:create_service","ready_timeout":10,
"stop_timeout":5}` and operations with `"service": true` in place of `handler`.
The factory receives the child Core SDK and returns an object with optional
`start()`, required `dispatch(operation, arguments, context)` and optional
`close()`. Core's root owner starts enabled services and hosts one runtime per
root/module. Discovery is passive. Disable, update and owner shutdown stop the
runtime. `core.modules` reports service state/PID/errors; expose background
queue health in a module query as well.

Use `with core.storage.transaction(timeout_seconds=5) as tx:` with `tx.query`
and `tx.execute`, commit on success and rollback on failure. Transactions last
at most five seconds. SQLite has multiple connections but one writer per
database file, including different module tables. Keep transactions short; do
file reads, parsing, waiting, tokenization and embedding outside them. No
independent parallel writers or WAL configuration are implied.

Declare `"rag": true` for shared `core.embeddings` and module-scoped `core.rag`:
profile, document/query embeddings, token counting, vector revision lookup and
put/search/delete. SQL and RAG have separate commits; retain durable jobs and
deletion records for safe replay. The dependency-free
`examples/modules/service-demo` demonstrates a persistent worker with SQL jobs
and atomic counter updates; its README uses an isolated source environment.

Child modules can call `core.rag.search(query=..., collection=...)` for the same
metadata filtering, inherited selection algorithms and diagnostics as native
contributions. Optional `object_type`, `status`, `include_archived`, `selection`,
`purpose`, `task_id` and `candidate_limit` retain Core semantics. The parent
always fixes the module scope to the caller. Omit `selection` to inherit settings;
do not implement another top-k default in the module. Results include candidate
evidence; modules can return compact descriptions and expose full content in
their own read operation. Existing `search_vector` remains available for callers
that explicitly need nearest-vector candidates rather than standard selection.
The child `search` method is available in Core 1.6+.

Revision checks use `core.rag.vector_revisions(collection=..., object_ids=...)`:
only those IDs are returned, with explicit missing and conflicting IDs. The
no-ID call is rejected. Full inventory uses `vector_revisions_page` and an
opaque continuation cursor over one native snapshot. Both support a result
byte budget; pages also bound distinct objects. See the
[revision API contract](implementation/module-services-local.md#revision-lookup-and-inventory)
for limits, cursor lifetime and recovery. Resume durable jobs on startup;
request a full inventory only when the task needs one.

RPC input and output frames each have a 1 MiB limit, counting the entire compact
UTF-8 JSON message and newline. Oversized Core results return a bounded error
that the child can handle without losing its connection. Document embeddings accept
1–128 inputs, but high-dimensional output may require smaller batches; reduce
the batch after an explicit oversized-result error. A running parent model or
native RAG call cannot be forcibly interrupted: Core stops/disconnects the child,
and asynchronous cleanup waits for that parent call to finish.

Modules that require the local shared-search extension can probe `core.rag.capabilities()`
for `search: true` before starting workers. This probe does not load the embedding model.


## Read-only web library contribution

An enabled module may expose a query operation named `<module_id>.library` to supply collections, paginated records and full reads to the Core web interface. The UI discovers this operation through `core.modules`; no module-specific Core code is required. See [the library contract](web-interface.md#module-contribution).

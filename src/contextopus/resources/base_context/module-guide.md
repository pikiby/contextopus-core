# Create and install a Contextopus module

A module contributes a domain adapter and registered operations to Core. The author supplies a folder containing `module.json` and `package/`, places it in `<root>/modules/<id>`, and asks `$m` to install it. The skill obtains `guide(procedure="modules")` and calls `core.module_install(module=<id>)`. Core prepares dependencies, applies declared migrations and enables the operations. CLI `modules install ID`, TUI Install and MCP use this same operation. Inspection alone does not authorize installation; an installation request already authorizes its declared sequence.

Discovery reads the manifest without importing handlers, preparing dependencies, applying migrations, loading models or starting jobs. Disabled modules remain passive. `core.modules` reports compatibility, lifecycle and storage errors. A failed or incompatible module must not be treated as enabled. Retry installation through Core after resolving its cause. Low-level prepare/enable operations remain available for diagnosis; enable does not apply migrations.

Example: first inspect `core.modules` for a supplied catalog module. Once installation is authorized, install it through `core.module_install`, inspect its declared procedure/signature, then verify its own status and a bounded query through the shared registry. A visible folder or successful dependency preparation alone does not establish operational readiness.

## Package contract

A minimal dependency-free release is:

```text
sample/
  module.json
  package/
    adapter.py
```

```json
{"id":"sample","version":"1.0.0","core_requires":">=1.3,<2","operations":[{"name":"sample.status","kind":"query","handler":"adapter.py:status","arguments_schema":{"type":"object","additionalProperties":false}}]}
```

```python
# package/adapter.py

def status(arguments):
    return {"available": True}
```

Handlers return JSON-compatible values from a child interpreter. Operation names begin with the module ID and a dot; each declares `query` or `execute` and an argument schema. `dependencies.python` lists Python requirements prepared by Core in the release's own environment. Optional `procedures`, `skills` and `filter_algorithms` name directories relative to `package/`; `tui` names a contributed operation that returns terminal `argv`. Native skills are published to a client only through its separately requested integration workflow.

Packages execute trusted code. Child processes and SQL access checks are not an operating-system sandbox. Author handlers for bounded operations and document background-job lifecycle, external tools and write ownership when needed. Keep stdout for the operation's JSON protocol and use stderr for logs.

## Ordinary tables through Core

Declare structured storage in `module.json`:

```json
{"storage":{"engine":"sqlite","schema_version":1,"migrations":"migrations","compatible_versions":{"min":1,"max":1}}}
```

Put ordinary SQL in `package/migrations/001-schema.sql`, then `002-change.sql`, with one continuously numbered file per version through `schema_version`. Underscores after the number are also supported. Do not alter an applied file. Quote module-owned table, index and other object names with the `{{module}}::` prefix:

```sql
CREATE TABLE "{{module}}::sessions" (id TEXT PRIMARY KEY, title TEXT NOT NULL);
CREATE TABLE "{{module}}::messages" (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES "{{module}}::sessions" (id),
    body TEXT NOT NULL
);
```

Core creates and owns `<root>/core/storage/modules.sqlite3`, records applied versions and applies pending migrations transactionally. The inclusive compatibility range must describe schema versions the package can actually use. SQL cannot access another module's tables, attach databases, set pragmas, load extensions or manage transactions. Schema changes belong in migrations; runtime execute operations use DML. Do not open the catalog directly or make a separate installer.

Storage-aware operations declare `"protocol":"contextopus-core-v1"` and use a two-argument handler:

```python
def messages(arguments, core):
    return core.storage.query(
        'SELECT id, body FROM "{{module}}::messages" WHERE session_id = ?',
        [arguments["session_id"]],
    )

def save(arguments, core):
    return core.storage.execute(
        'INSERT INTO "{{module}}::sessions" (id, title) VALUES (?, ?)',
        [arguments["id"], arguments["title"]],
    )
```

`query(sql, parameters=())` returns `columns` and a `rows` list of dictionaries. `execute(sql, parameters=())` returns `rowcount` and `lastrowid`. Core owns the connection; query operations cannot write. The complete runnable `examples/modules/catalog-demo` example uses this bridge for sessions and linked messages, including joins and aggregation. Legacy one-argument handlers continue to work without storage access.

Domain tables and RAG are separate services. Use the common Core index and supported source-adapter integration for searchable material; do not create a module-specific vector database. An operation manifest alone does not register an index source.

## Update and verify

Mutable user files belong in `data/` and `config/`. An authorized `core.module_update(module=<id>, source=<unpacked release>)` stages the new package and prepares its dependencies and schema before activation. Previously disabled modules stay disabled. Preserve user files and retained releases; incompatible code must not resume against a changed schema. Disabling removes operations and keeps data.

Test installation through an actual Application in an isolated root, exercise relevant query/write operations, then rebuild the Application to verify persisted state and existing rows. Test schema failure and retry, incompatible versions, and passive discovery. Fetch unknown signatures through `guide(operation=...)` rather than inventing API calls. This guide and its template describe module authoring; they do not authorize unrelated installation or publication.

Implementation references: `src/contextopus/core/module_management/`, `src/contextopus/core/module_storage/`, `src/contextopus/core/module_management/child.py`. Detailed procedure: `modules`; runnable repository example: `examples/modules/catalog-demo`.

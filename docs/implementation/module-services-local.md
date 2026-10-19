# Local module services and session-search handoff

> Historical document: release/verification conditions below apply to the named
> version or dated check. The independent repository layout is unreleased; see
> [current development instructions](../development.md).

The base module-service extension and per-module SQLite storage are implemented,
verified and installed locally in an unreleased Core 1.4.0 build. The adapter
replacement follow-up described below is currently source-only. Neither the
installation nor an empty-root module check establishes a production
session-search data migration. Live migration and publication require separate
authorization.

## Ownership and lifecycle

Core discovers manifests passively. A manifest can declare a persistent
`service` with `factory: "worker.py:create_service"`, `ready_timeout` and
`stop_timeout` in seconds. Alternatively use `command: ["executable", ...]`
and `protocol: "contextopus-service-v1"`. Paths belong to `package/`.
An operation routed to the service declares `service: true` instead of a handler.
Existing one-shot handlers and commands retain their protocols.

The Python factory receives the child Core SDK and returns an object with
optional `start()`, required `dispatch(operation, arguments, context)` and
optional `close()`. `context` is the selected context name or null. Start work
in `start()`, return promptly, stop and join workers in `close()`. Keep stdout
for the JSON protocol; log to stderr. Background threads may call the SDK.
Query dispatch cannot write; background work has execute access. These are
trusted modules, not an OS sandbox.

Core's root owner starts enabled services and keeps one runtime per root/module;
listing manifests does not start them. Readiness follows successful factory and
start. `core.modules` reports `service.state` (`stopped`, `starting`, `running`,
`stopping` or `error`), PID and any error. A service process being ready does not prove its
background queue is healthy: publish domain status through a registered query.
Disable, update and owner shutdown stop the runtime; stop timeout leads to
process-group termination. Recover durable jobs in `start()`. A crashed service
needs explicit re-enablement rather than an implicit restart loop.

A model/provider call or native RAG call already executing in Core cannot be
forcibly interrupted. Core can disconnect and stop the child; cleanup of that
in-flight parent call waits asynchronously for completion. The child stop
timeout does not bound the duration of the underlying provider/native call.

### Legacy adapter replacement

The local source also supports explicitly replacing a compatibility adapter with
a folder module of the same ID. This follow-up is not included in the installed
local wheel `73fb6ef0b09863a4197c49338668841e9830f1c19b94154d424c1fd84daf72bc`.
For `session_search`, keep the installed external launcher in place and install
the folder package through `core.module_install`. Core prepares the package and
storage, checks the service's readiness, persists folder ownership, then replaces
the complete adapter operation contribution. It does not import or delete the
external program's index or source sessions. Core and Workspace remain protected
from this replacement mechanism.

Until the first successful switch, preparation or readiness failure leaves the
legacy adapter usable. Enablement without a running owner is
`activation_pending`: the adapter remains available until the owner starts the
candidate successfully. Discovery remains passive. Once selected, the folder
implementation survives restart; disablement or a later error never silently
restores the legacy adapter. Other applications sharing the root reconcile this
choice before their next description or dispatch.

Verification for this follow-up:

```console
timeout 90 .venv/bin/python -m pytest -q tests/test_module_adapter_replacement.py tests/test_module_services.py tests/test_module_install.py tests/test_module_interfaces.py
```

Result: **70 passed in 20.15 seconds** on Linux. The 22 replacement cases include
an available legacy executable and a real isolated Unix-socket response, failed
dependencies/schema/readiness, failures around durable publication, first-update
rollback, pending activation, historical disabled modules and protected native
modules. A deterministic dispatch test covers replacement while a request is
waiting for the old operation's root guard. Read-only review found no remaining
blocking findings.

An independent integration used the actual session-search 0.7.6 folder candidate
from `/tmp/session-search-final-ntmd5wua/session_search`, copied into a temporary
root. The installed `/usr/bin/session-search` remained available and unchanged.
Failed first readiness preserved legacy commands; successful installation
returned `integration: core` and a live worker. Two contexts used one process;
restart, disable, restart while disabled and re-enable passed. No user sessions
were configured or imported, and no embedding model was loaded. This verifies
the service transition, not retrieval quality or migration of a working index.

## Child SDK

Declare `storage` and packaged migrations for SQL; declare `rag: true` for shared
embeddings and RAG. These capabilities refer to Core services, not a model or
database created by the module. Generic `core.call(method, arguments)` exposes
the same methods as the Python namespace helpers.

| Method | Arguments and result |
| --- | --- |
| `core.storage.query(sql, parameters=())` | Returns `columns` and dictionary `rows`. |
| `core.storage.execute(sql, parameters=())` | Returns `rowcount` and `lastrowid`. |
| `core.storage.transaction(timeout_seconds=5)` | Context manager; `tx.query`/`tx.execute`, commit on success, rollback on failure. Maximum 5 seconds. |
| `core.embeddings.profile()` | Active Core profile/configuration; pass this exact object to embedding and vector calls. |
| `core.embeddings.embed_documents(texts=..., profile=...)` | 1–128 texts, returns vectors using document encoding. |
| `core.embeddings.embed_query(text=..., profile=...)` | Returns one vector using query encoding. |
| `core.embeddings.count_tokens(text=..., profile=...)` | Uses the shared provider tokenizer. |
| `core.rag.put_vector(document=..., vector=..., profile=...)` | Upserts a module-owned document/vector revision. |
| `core.rag.vector_revisions(collection=..., object_ids=..., max_bytes=262144)` | Bounded lookup: returns `revisions`, explicit `missing` and `conflicts` ID lists, and `snapshot`. |
| `core.rag.vector_revisions_page(collection=..., cursor=None, limit=100, max_bytes=262144)` | Explicit inventory: returns `revisions`, `conflicts`, `snapshot` and `next_cursor`. |
| `core.rag.search_vector(collection=..., object_ids=..., vector=..., profile=..., limit=20)` | Searches only the caller's collection and supplied IDs (at most 10,000). |
| `core.rag.delete_document(key=...)` | Deletes the caller's document. |

Document shape is `{key: {collection, id}, revision, text, location, metadata}`.
`key.module` is optional and must match the caller. Operations cannot address
another module's RAG namespace. A profile change requires restarting the module;
do not silently reuse vectors produced under another profile.

RPC input and output frames are each limited to 1 MiB. The limit includes the
complete JSON envelope, UTF-8 encoded values and final newline. Both transports
and the standalone SDK use compact JSON without ASCII escaping. Call IDs must
be strings of at most 128 serialized JSON bytes. A Core result or error that
cannot fit produces a bounded, explicit error response; the child can catch it
and make another call. No partial map or truncated JSON is returned. The
1–128 document count
is an API bound, not a guarantee that every batch fits: high-dimensional vectors
can make the response exceed the frame limit. Keep batches within both input
and output limits; reduce the batch after an explicit oversized-result error.

### Revision lookup and inventory

Use revision lookup to check the objects relevant to a job. Supply 1–1,000
distinct, nonempty UTF-8 IDs, each at most 4,096 characters; their serialized
JSON array must fit 256 KiB. Only the calling module and selected collection are
read. Matching fragments with one revision produce one entry. An ID with
disagreeing fragment revisions appears in `conflicts`, not in `revisions` or
`missing`; investigate or reindex it before considering it current. Missing
means no indexed fragments were found. These calls do not load an embedding
model or run similarity search.

The old `vector_revisions(collection=...)` call without IDs now fails with an
actionable error before opening the index. A full inventory requires the
separate page operation. Consume `next_cursor` until it is `null`, processing
each page before requesting the next; do not collect an entire large inventory
into one module response. `limit` bounds distinct objects, including conflicts,
and accepts 1–1,000. Both methods default to a 256 KiB result budget and accept
at most 768 KiB. This budget counts the complete result object, including
snapshot, missing/conflict lists and cursor. It leaves room for the transport
envelope. A point lookup that cannot fit fails instead of returning a partial
answer. A page stops earlier and returns a continuation; if one object or the
required metadata cannot fit, it fails explicitly.

Inventory is ordered by object ID. A cursor binds the root, module, collection,
active table, native table version and last completed object. Subsequent pages
read that same native snapshot, so concurrent inserts, updates and deletes do
not move the boundary. A replaced active table, unavailable snapshot or invalid
cursor fails explicitly; restart the inventory with no cursor rather than
mixing versions. Cursors are opaque continuation tokens, not authorization to
read another module. Inspect `snapshot` when comparing separate lookups; each
new lookup observes its own version.

Core now requires LanceDB 0.40 or later for native ordered queries used by
inventory paging. The lock file already selects 0.40.0. The older 0.20 dependency
floor did not provide the ordering API; this source change does not upgrade an
existing installation by itself.

Queries filter by scope and requested IDs and stream bounded batches rather
than exporting a collection into Python. Without a covering scalar index,
LanceDB may still scan filter columns internally; paging is not a promise of
constant-time I/O. Revision inventory is an explicit audit/recovery tool, not a
mandatory full scan on every service start. Resume durable jobs and deletion
records first, checking relevant revisions in bounded batches when needed.

SQL object names use `"{{module}}::table"`; migrations apply through Core.
The low-level transaction API is `storage.begin(timeout_seconds=5)` returning
`transaction_id`, followed by tagged query/execute and `commit(transaction_id)`
or `rollback(transaction_id)`. One transaction is active per capability session.
SQL errors, expiry and child disconnection roll back. Untagged reads remain
independent; untagged writes during that session's transaction are rejected.

Core creates and migrates `<root>/core/storage/modules/<module-id>.sqlite3`
through the existing storage API. Each file has its own migration ledger and
writer lock. A transaction or ordinary SQL write in one module does not hold
another module's writer lock. SQLite permits multiple connections but one writer
within each file. Keep transactions short. Do parsing, file reads,
tokenization, embeddings, RAG calls and waiting outside transactions; model/RAG
calls are rejected while a transaction is active. Transactions do not span module
files or SQL and RAG. Models, providers, embeddings and RAG remain shared Core
services; this change does not prescribe WAL configuration.

The root guard admits each SQL write briefly; database work and transaction
completion use the module's lock. Relocation acquires the root guard, waits for
existing writers to finish, then keeps all module locks through freeze, verified
copy and routing switch. Runtime lock files and disposable partition staging are
excluded from the snapshot; legacy source files and recovery backups are retained.

Only explicit Core storage apply or module installation partitions an older
`core/storage/modules.sqlite3` catalog. Core validates module ownership, copies
each module's schema/data and ledger into staged files, then publishes them with
recovery state. The original catalog and a durable recovery backup remain.
Inspection, schema preparation and queries do not migrate or create storage.
Resume an interrupted partition through the same explicit Core operation.

## Session-search adaptation

The next agent owns toolkit-session-search adaptation. Its inspected
`src/session_search/store.py` uses sessions, deduplicated blocks, occurrence
chunks, durable jobs, vectors and deletion records. Preserve these semantics
when moving structured state into Core's catalog:

| Existing state | Target responsibility |
| --- | --- |
| `sessions(id, metadata, state, checkpoint)` | Module-owned sessions table; preserve checkpoint JSON, offsets, inode, prefix/tail hashes, reader state and provenance. |
| `blocks(pk, content_hash, text)` | Module-owned deduplicated blocks; preserve stable IDs and content revisions. |
| `chunks(... session_id, block_pk, start_offset, end_offset, metadata)` | Module-owned occurrence table; keep every source location even when text deduplicates. |
| `jobs(... state, attempts, next_attempt, error, priority_ns, source_offset)` | Module-owned durable queue; atomically ingest occurrences, enqueue work and advance checkpoints. Preserve ordering/retries and recover interrupted running jobs. |
| `vectors` / `vector_deletions` | Shared Core RAG vectors plus SQL bookkeeping/deletion outbox; reconcile selected IDs through `vector_revisions`, or use explicit paged inventory for an audit. |
| `search_requests`, `search_results`, metadata | Module-owned history and explicit chunking/profile compatibility metadata. |

Use the eventual module ID consistently for every SQL prefix and RAG key.
Namespace conversion and import belong to a separate reviewed migration; copying
legacy SQL verbatim will not establish namespace safety. Preserve the source
database and JSONL files until migration counts and retrieval pass acceptance.

SQLite and LanceDB do not share a transaction. Claim a small batch in SQL,
release its transaction, embed through Core, write the matching RAG revision,
then acknowledge SQL only if the block/job revision is still current. A crash
between these steps must replay safely. Keep durable deletion records until
RAG deletion is confirmed. Resume durable jobs on restart and check their
revisions in bounded batches when needed; reject stale job
completion after source edits. Never delete the queue or assume a RAG write
committed the relational checkpoint.

## Isolated source checks

### Bounded revision API and shared framing (2026-10-18, source only)

After the adapter replacement work, the generic revision API and protocol were
checked together on Linux:

```console
timeout 150 .venv/bin/python -m pytest -q tests/test_rag_revisions.py tests/test_module_core_access.py tests/test_module_protocol.py tests/test_filtering.py tests/test_module_services.py tests/test_module_install.py tests/test_module_interfaces.py tests/test_module_transactions.py tests/test_module_adapter_replacement.py tests/test_module_service_example.py
```

Result: **178 passed in 26.18 seconds**. Real temporary LanceDB 0.40.0 and child
processes covered scoped lookup, fragment conflicts, pagination over 1,005
objects, inserts/deletes/updates between snapshot pages, expired/replaced
snapshots and exact UTF-8 byte budgets. One-shot and persistent children recover
after an oversized Core result or error and can call Core again. Malformed
framing and UTF-16/32 input are rejected. Windows newline translation was
simulated with a text wrapper; this is not a native Windows test. Embedding
providers were test doubles. Internal algorithm catalog consumers stream pages
without rebuilding the entire stored revision map in Python.

These source changes have not been installed into the running Core and do not
establish live module data migration or a release. The historical baseline
checks and installed wheel below remain distinct.

An offline verification wheel was built at
`/tmp/contextopus-bounded-rag-20261018/contextopus_core-1.4.0-py3-none-any.whl`.
All 139 packaged Python/resource files matched the source byte for byte; the
extracted standalone SDK loaded its sibling protocol and completed a Unicode
frame round trip. Wheel metadata requires `lancedb>=0.40,<1`.
SHA256: `ad3d3ad6dbf297852695450ec7657083a73065b7474784a17053d09789000403`.

### Installed baseline

Use the repository's existing environment and temporary root; do not install
over the working Core. From this checkout:

```console
PYTHONPATH=src .venv/bin/python -m pytest tests/test_module_service_example.py
```

`examples/modules/service-demo` supplies a dependency-free persistent worker
with SQL jobs and an atomic counter update. Its README shows source execution
without an external daemon. Core MCP uses the same registered module operations:
`write(operation="service-demo.enqueue", arguments={"id":"one","amount":2})`
and `read(operation="service-demo.status", arguments={})`.

The current Core verification ran from the repository root, outside the
execution sandbox (pytest configuration supplies the source import paths):

```console
timeout 180 .venv/bin/python -m pytest -q tests/test_module_services.py tests/test_module_service_example.py tests/test_module_lifecycle.py tests/test_module_processes.py tests/test_module_install.py tests/test_module_interfaces.py tests/test_startup.py tests/test_module_storage.py tests/test_module_core_access.py tests/test_module_transactions.py tests/test_module_storage_migration.py tests/test_relocation_handles.py tests/test_relocation_portability.py tests/test_relocation_repeated.py tests/test_core_regressions.py tests/test_core_foundation.py tests/test_core_mcp_extensions.py tests/test_mcp_v13.py tests/test_storage_guard_deadlines.py tests/test_utf8_dataflows.py tests/test_module_partition_integration.py
```

Result: **303 passed, 1 skipped, 9 subtests passed in 59.02 seconds**. The skipped
startup test requires a normal user site, which the virtual-environment
interpreter disables. These are Linux source tests with fake model providers,
real child processes, temporary SQLite/LanceDB storage and an isolated HTTP MCP.
They do not establish installed-module or native Windows/macOS acceptance.

The integration cases verify that beta commits while alpha's transaction remains
open, and that pending or completed legacy partitioning supports reads and
explicit installation after relocation. Repeated relocation now preserves prior
snapshot trees byte-for-byte and creates a separate hidden snapshot namespace.
Tests cover A-to-B, database edits, B-to-C, persisted v1/v2 plan retry and rollback,
WAL, archive integrity and failure during a partial raw copy. Raw copies are
checksum-checked before atomic publication; retry replaces unfinished temporary
files but refuses conflicting completed snapshots.

A fresh offline wheel was built from a temporary source copy at
`/tmp/contextopus-relocation-package-hyy6vlcs/dist/contextopus_core-1.4.0-py3-none-any.whl`.
All **137 Python/resource files** byte-matched the source. Imports from the
extracted wheel passed repeated relocation with database edits and preserved
previous snapshots. Its real `service-demo` background job reached total 7 and
its child exited on owner shutdown. That wheel was subsequently installed
locally; no release was published. Its SHA256 is
`73fb6ef0b09863a4197c49338668841e9830f1c19b94154d424c1fd84daf72bc`;
the declared package version remains 1.4.0.

Module acceptance remains separate: passive discovery, one owner across
contexts, query/write separation, concurrent readers/writers, queue recovery,
disable/update/shutdown cleanup, profile mismatch, source edits/deletions,
deduplicated occurrences and retrieval parity against a copied fixture. Only
after Core and the adapted module pass together should release and installed
update be proposed.

## Next agent: adapt session-search

1. Use the Core source checkout.
   Read this contract and `examples/modules/service-demo` before changing
   toolkit-session-search. Recheck the current module source and its schema;
   the mapping above records the inspected baseline.
2. Implement its folder manifest, packaged migrations and service factory in
   the module repository. Route registered operations to `dispatch`, recover
   durable jobs in `start`, and stop/join producers in `close`. Replace private
   model/vector access with the Core SDK. Preserve the source database and
   checkpoint/retry/provenance semantics; use Core's per-module SQLite file.
3. Copy the candidate package and small source fixtures to a temporary Core
   root. Run the local Core source through its existing environment. For direct
   `Application` tests, call `app.module_manager.start_services()` as in the
   example; ordinary CLI/TUI/MCP calls use the shared root owner.
4. Check the acceptance cases above, including queue replay across interruption,
   stale revision rejection, occurrence preservation and retrieval parity.
   Keep migration planning and fixture import explicit; a successful empty-root
   install does not validate a production data migration.
5. Report the candidate package, test command/results and remaining limitations.
   Live migration, installed updates and public release each require their own
   authorization; this handoff grants none of them.

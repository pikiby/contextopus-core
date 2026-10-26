# Web library

Run `contextopus web` and open `http://127.0.0.1:41860/`. Use `contextopus --root /path/to/data web --port 41861` for another root or port. The existing Core MCP service must be running. The web process connects to it; it does not open a second database owner or load another embedding model.

The interface is read-only. It shows enabled modules, their collections and records, plus shared Core instructions. Browse with an empty query, search titles and descriptions by text, or submit a semantic query through the existing RAG. Semantic results use configured relevance selection and expose its diagnostics; their result count is not the total size of the library. Text results and browsing are paginated after filtering. Reading a record loads its current body and declared relationships. Unavailable links are labelled rather than guessed.

Workspace opens on **Contexts**: project descriptions across the available contexts. Select a context to see its **Bound instructions**, labelled by role and source file. Open a file to read its complete rules from Core. **All records** returns to the full Workspace catalog; the collection selector narrows either view to one context.

There are no sample cards, imports, background index starts, editing, module switches or cleanup actions in this interface. Search may produce the normal Core analytics events. Each module remains responsible for its data and applicable read limits. An empty Session Search catalog does not trigger transcript ingestion.

## Module contribution

An enabled module supplies a query operation named `<module_id>.library`, exposed by `core.modules`. Core discovers it generically; no module-name branches or custom frontend build are necessary. Modules without this operation remain visible with an explicit unsupported message.

The operation accepts:

- `action`: `collections`, `records` or `record`.
- `collection`: exact collection id; empty for the module-wide view.
- `query`, `mode` (`text` or `semantic`) and `type` for record selection.
- `offset` and `limit` for paging (web requests are bounded to 100 records).
- `id`: source record id for a complete read.

Responses:

- Collections: `{collections: [{id, title}]}`.
- Records: `{records: [{key: [module, collection, id], title, description, type, ...}], total, has_more, types?, warnings?, diagnostics?}`.
- Record: `{key, title, description, type, content, metadata, links, path?, revision?}`.
- Links: `{key: [module, collection, id], title, description?}` or `{reference, title, unavailable: true}`.

Collections may also supply `views: [{title, type}]`: named shortcuts to existing type filters. The first view is selected when entering the module; an empty `type` selects all records. Record responses may supply `link_groups: [{title, links, empty_message?}]` to show important relationships above the body. Links can include a `label` and source `path`. These optional fields use the same generic navigation and read operations as ordinary links.

Return source-backed identities, not fragment ids that the read operation cannot resolve. Filter before semantic selection. Preserve relevance and truncation diagnostics. Browsing must not require vector indexing, and incomplete data or unavailable sources must not be represented as an authoritative empty catalog. A module should expose source-native collection and read limits explicitly, including bounded session histories.

## Local HTTP boundary

The server binds only to loopback and rejects foreign Host/Origin and cross-site browser requests. It serves three packaged static files and four explicit query endpoints. There is no arbitrary MCP dispatcher or filesystem path endpoint. The gateway checks that the selected enabled module declares a query operation. Source Markdown and metadata are untrusted display data; the frontend creates DOM nodes without executing source HTML. No third-party CDN or external content is loaded.

This is a local personal interface, not a remotely authenticated multi-user service. Do not publish it through a reverse proxy without a separately designed authorization boundary.

## Checks

Run `python -m pytest tests/test_web_library.py` for HTTP restrictions, module discovery, query dispatch and instruction browsing. Run `node tests/web_frontend_smoke.cjs src/contextopus/interfaces/web/static/app.js` for deterministic DOM/API interaction checks without a browser. Module repositories test their own library contributions. These checks do not replace live HTTP acceptance against an installed root or visual review.

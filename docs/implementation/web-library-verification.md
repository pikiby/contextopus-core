# Local web library verification

Verified on 2026-10-23, Linux, with the installed Core and enabled Workspace, Agents and Session Search contributions. This is local delivery, not a public release or cross-platform browser certification.

## Installed behavior

- `contextopus web` serves the packaged read-only interface at `http://127.0.0.1:41860/` and uses the existing MCP service.
- All enabled modules advertise their query-only `.library` contribution. Core has its own instruction contribution. No module-name branches are required by the web gateway.
- Workspace: all 564 records across 30 contexts were traversed through pagination, with matching total and no duplicate keys.
- A scoped text query returned 66 real matches; the selected source body was read successfully. A Context.md link to its shared Core instruction resolved and loaded the complete rules.
- Agents: three records are browsable. A semantic query about reading Git commits without changing files returned Git reader first, including when the browser supplied an empty type filter.
- Core: 31 shared instructions are browsable without requiring the embedding model for text listing or reading.
- Session Search: its actual catalog is empty. Indexing remains stopped, autostart false, with zero sessions/chunks/vectors; no transcript import was performed.
- The installed static assets match source bytes. The former demonstration records and server were removed from the example; it now points to the standard command.

## Focused checks

- Core web tests: 16 passed; HTTP Host/Origin isolation, no arbitrary file/operation routing, readonly dispatch, module availability, pagination and instruction sources covered. The earlier shared instruction suite also passed alongside the web tests.
- Frontend Node DOM/API smoke: passed; live catalog/detail reads, semantic requests, race suppression, unavailable modules, refresh, diagnostics, folded metadata and conversation paging/retry.
- Workspace: 30 passed (library, Context.md and record link tests).
- Agents: 24 passed (library and existing file authority, deletion and empty-body checks).
- Compatible Session Search 0.7.6 package: three focused checks passed, including source-type prefiltering and oversized-block rejection.

Session Search was not upgraded to the newer source version as a side effect. Its local package was built from the installed 0.7.6 code with only the library handler, dispatch registration and manifest declaration added. Current 0.8.0 source carries the same feature separately.

## Limits

No GUI automation or browser visual acceptance was performed. Session content is displayed from existing indexed conversation blocks, not from an automatic raw-transcript import. Long content is paged; an individual block beyond 256 KiB returns an explicit error. Session semantic retrieval retains its existing nearest-20-block limit and exposes that limitation. Semantic result caps are reported rather than presented as complete catalog counts.

No commits, pushes or public releases were made for this delivery. Read operations may emit ordinary analytics events; the web interface has no authoring or cleanup endpoints.

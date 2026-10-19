"""Native FastMCP transport with one process owner for all roots and modules."""

import atexit
import json
import os
import threading
from functools import partial
from typing import Any, Literal
import anyio
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent, ToolAnnotations
from starlette.responses import JSONResponse
from contextopus.startup import Application
from contextopus.core.resources import ProcessResources


class ServerOwner:
    def __init__(self, root):
        self.root = str(Path(root).expanduser().resolve())
        self.resources = ProcessResources()
        self.applications = {}
        self._lock = threading.RLock()

    def application(self, root=None, context=None):
        from contextopus.core.storage import StorageLayout

        key = (str(StorageLayout.resolve(root or self.root).root), context)
        with self._lock:
            created = key not in self.applications
            if key not in self.applications:
                self.applications[key] = Application(
                    key[0], key[1], resources=self.resources
                )
            app = self.applications[key]
        if created and self.resources.services_started:
            self.resources.start_services()
        return app

    def current_root(self):
        import json
        from contextopus.core.storage import StorageLayout

        current = StorageLayout.resolve(self.root).root
        if str(current) != self.root:
            record = Path(self.root) / "runtime/service.json"
            if (
                record.is_file()
                and json.loads(record.read_text()).get("pid") == os.getpid()
            ):
                target = current / "runtime/service.json"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    json.dumps({"pid": os.getpid(), "root": str(current)})
                )
        return str(current)

    def close(self):
        failures = []
        for app in list(self.applications.values()):
            try:
                app.close()
            except Exception as exc:
                failures.append(exc)
        self.applications.clear()
        try:
            self.resources.close()
        except Exception as exc:
            failures.append(exc)
        if failures:
            raise ExceptionGroup('MCP owner failed to close', failures)


def create_server(root, host="127.0.0.1", port=8765, *, legacy_tools=None):
    owner = ServerOwner(root)
    owner.application()
    owner.resources.start_services()
    mcp = FastMCP(
        "Contextopus",
        host=host,
        port=port,
        instructions=(
            "Use the Contextopus MCP tools advertised by this client for Contextopus context discovery, "
            "instructions, knowledge retrieval and memory changes. Their native names may include a server "
            "prefix; select those advertised tools, not similarly named local tools. A supplied work_root "
            "identifies Contextopus data, not a code directory to explore. Obtain and read the applicable "
            "procedure through this server's guide tool before context operations. Do not replace Contextopus "
            "operations with shell commands, direct context-file reads, generic code search or web search. "
            "Native skill loading and obtaining declared external sources still use the readers required by "
            "the client and procedure. If Contextopus MCP is unavailable, report the connection failure "
            "instead of bypassing it. Use this server's read tool for queries and write tool only for "
            "authorized changes under the existing approval rules. Enabled modules contribute their own "
            "operations and procedures. guide() returns the active default procedure, or the module "
            "installation procedure for Core alone. guide(operation=...) returns only an operation "
            "signature and does not replace a procedure. Request signatures only when unknown. "
            "Reuse procedures already obtained for the same task; reload when changed or lost."
        ),
    )
    atexit.register(owner.close)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request):
        return JSONResponse({"root": owner.current_root(), "pid": os.getpid()})

    def route(kind, operation, arguments, work_root=None, context=None, workspace=None):
        if context is not None and workspace is not None and context != workspace:
            raise ValueError("context and workspace disagree")
        app = owner.application(work_root, context or workspace)
        # Reaching transport dispatch proves this owner is serving requests.
        # It provides no evidence about a particular native client's identity.
        app.services.runtime_mcp["server"] = "running"
        return getattr(app, kind)(app.normalize_operation(operation), arguments)

    def normalize(operation, work_root=None, context=None, workspace=None):
        return owner.application(work_root, context or workspace).normalize_operation(operation)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    async def guide(
        procedure: str | None = None,
        operation: str | None = None,
        catalog: bool = False,
        work_root: str | None = None,
        context: str | None = None,
        workspace: str | None = None,
    ) -> dict:
        """guide() reads the active default procedure; operation=... gives only a signature, not a replacement for a procedure. Catalog is opt-in."""
        if sum((procedure is not None, operation is not None, catalog)) > 1:
            raise ValueError('Choose procedure, operation or catalog')
        if operation is not None or catalog:
            return await anyio.to_thread.run_sync(partial(route, 'query', 'describe',
                {'operation': normalize(operation, work_root, context, workspace)} if operation is not None else {}, work_root, context, workspace))
        return await anyio.to_thread.run_sync(partial(route, 'query', 'procedure',
            {'name': procedure or 'default'}, work_root, context, workspace))

    async def dispatch(kind, operation, arguments, work_root, context, workspace, detail):
        # Validate before executing a mutation. Presentation runs only after the
        # existing registry has completed approval checks and observation.
        if detail not in ('compact', 'full'):
            raise ValueError('detail must be compact or full')
        result = await anyio.to_thread.run_sync(partial(route, kind, operation, arguments, work_root, context, workspace))
        from .presentation import present
        result = present(result, operation=normalize(operation, work_root, context, workspace), arguments=arguments, detail=detail)
        if isinstance(result, dict):
            return result
        # FastMCP otherwise expands a list into separate content blocks, losing
        # its JSON shape (and making empty/multiple results undecodable).
        return [TextContent(type='text', text=json.dumps(result, ensure_ascii=False))]

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    async def read(
        operation: str, arguments: dict | None = None,
        work_root: str | None = None, context: str | None = None,
        workspace: str | None = None, detail: Literal['compact', 'full'] = 'compact',
    ) -> Any:
        """Run a query; compact metadata is standard, full detail preserves all evidence."""
        return await dispatch('query', operation, arguments, work_root, context, workspace, detail)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False))
    async def write(
        operation: str, arguments: dict | None = None,
        work_root: str | None = None, context: str | None = None,
        workspace: str | None = None, detail: Literal['compact', 'full'] = 'compact',
    ) -> Any:
        """Run an authorized mutation under its existing review and approval policy."""
        return await dispatch('execute', operation, arguments, work_root, context, workspace, detail)

    @mcp.tool(annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False,
    ))
    async def finish(
        cycle_id: str,
        expected_revision: str | None = None,
        confirmation: str | None = None,
        cancel: bool = False,
        work_root: str | None = None,
        context: str | None = None,
        workspace: str | None = None,
    ) -> Any:
        """Close one reviewed work cycle and remove only its temporary files.

        Read workspace.status for the exact cleanup revision and deletion scope.
        Follow cleanup_approval_required independently of knowledge approval.
        Pending proposals, indexing and incoming dependencies block completion.
        Cancellation needs the user's actual cancellation. Native clients can
        authorize this bounded tool separately from general write operations.
        """
        return await dispatch('execute', 'finish', {
            'cycle_id': cycle_id, 'expected_revision': expected_revision,
            'confirmation': confirmation, 'cancel': cancel,
        }, work_root, context, workspace, 'compact')

    # Explicit temporary compatibility for old clients. It preserves full legacy
    # responses and is never advertised by the default server.
    if legacy_tools is None:
        legacy_tools = os.environ.get('CONTEXTOPUS_LEGACY_TOOLS') == '1'
    if legacy_tools:
        async def legacy_query(operation: str, arguments: dict | None = None,
                               work_root: str | None = None, context: str | None = None,
                               workspace: str | None = None) -> Any:
            return await dispatch('query', operation, arguments, work_root, context, workspace, 'full')
        async def legacy_execute(operation: str, arguments: dict | None = None,
                                 work_root: str | None = None, context: str | None = None,
                                 workspace: str | None = None) -> Any:
            return await dispatch('execute', operation, arguments, work_root, context, workspace, 'full')
        for name in ('contextopus_query', 'pcw_query'):
            mcp.tool(name=name, annotations=ToolAnnotations(readOnlyHint=True))(legacy_query)
        for name in ('contextopus_execute', 'pcw_execute'):
            mcp.tool(name=name, annotations=ToolAnnotations(readOnlyHint=False))(legacy_execute)
    return mcp


def run(root, transport="streamable-http", host="127.0.0.1", port=8765):
    import json
    from contextopus.core import locking
    from contextopus.core.storage import StorageLayout
    root = StorageLayout.resolve(root).root
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "mcp-owner.lock").open("a") as owner_lock:
        # Every launch route, including native OS services, shares one ownership guard.
        locking.flock(owner_lock, locking.LOCK_EX | locking.LOCK_NB)
        (runtime / "service.json").write_text(json.dumps({"pid": os.getpid(), "root": str(root)}))
        create_server(root, host=host, port=port).run(transport=transport)

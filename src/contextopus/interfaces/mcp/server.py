"""Native FastMCP transport with one process owner for all roots and modules."""

import atexit
import os
import threading
from functools import partial
import anyio
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
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
            if key not in self.applications:
                self.applications[key] = Application(
                    key[0], key[1], resources=self.resources
                )
            return self.applications[key]

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
        from contextopus.modules.workspace.server import close_runtimes

        close_runtimes()
        self.resources.close()


def create_server(root, host="127.0.0.1", port=8765):
    owner = ServerOwner(root)
    mcp = FastMCP(
        "Contextopus",
        host=host,
        port=port,
        instructions=(
            "Use contextopus_query and contextopus_execute. describe lists module-owned operations. "
            "Core operations require no Workspace. Workspace operations use explicit context and retain their approval rules. "
            "Read procedure(name=workspace) before Workspace work."
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
        from contextopus.modules.workspace.operations import _DESCRIPTIONS

        if operation in _DESCRIPTIONS:
            operation = "workspace." + operation
        return getattr(app, kind)(operation, arguments)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    async def contextopus_query(
        operation: str,
        arguments: dict | None = None,
        work_root: str | None = None,
        context: str | None = None,
        workspace: str | None = None,
    ) -> dict:
        return await anyio.to_thread.run_sync(partial(route, "query", operation, arguments, work_root, context, workspace))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False))
    async def contextopus_execute(
        operation: str,
        arguments: dict | None = None,
        work_root: str | None = None,
        context: str | None = None,
        workspace: str | None = None,
    ) -> dict:
        return await anyio.to_thread.run_sync(partial(route, "execute", operation, arguments, work_root, context, workspace))

    mcp.tool(name="pcw_query", annotations=ToolAnnotations(readOnlyHint=True))(
        contextopus_query
    )
    mcp.tool(name="pcw_execute", annotations=ToolAnnotations(readOnlyHint=False))(
        contextopus_execute
    )
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

"""Client facade for the central Application, shared by CLI and TUI."""

from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json


class RemoteServices:
    def __init__(self, app):
        self.app = app

    def status(self):
        return self.app.query("core.status")

    def settings(self):
        return self.app.query("core.settings")

    def preview_settings(self, changes):
        return self.app.query("core.settings_preview", {"changes": changes})

    def apply_settings(self, preview_revision):
        return self.app.execute(
            "core.settings_apply", {"preview_revision": preview_revision}
        )


class RemoteApplication:
    def __init__(self, root, context=None, endpoint="http://127.0.0.1:8765/mcp"):
        self.root, self.context, self.endpoint = str(root), context, endpoint
        self.services = RemoteServices(self)
        self._executor = ThreadPoolExecutor(max_workers=1)

    async def _call(self, tool, operation, arguments):
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(self.endpoint) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    tool,
                    {
                        "operation": operation,
                        "work_root": self.root,
                        "workspace": self.context,
                        "arguments": arguments or {},
                    },
                )
                if result.isError:
                    raise RuntimeError(
                        "; ".join(
                            item.text
                            for item in result.content
                            if hasattr(item, "text")
                        )
                    )
                if result.structuredContent is not None:
                    return result.structuredContent
                content = "\n".join(
                    item.text for item in result.content if hasattr(item, "text")
                )
                return json.loads(content)

    def _sync(self, tool, operation, arguments):
        return self._executor.submit(
            lambda: asyncio.run(self._call(tool, operation, arguments))
        ).result()

    def query(self, operation, arguments=None):
        return self._sync("contextopus_query", operation, arguments)

    def execute(self, operation, arguments=None):
        return self._sync("contextopus_execute", operation, arguments)

    def close(self):
        self._executor.shutdown()

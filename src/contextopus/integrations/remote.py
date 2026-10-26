"""Client facade for the central Application, shared by CLI and TUI."""

from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


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
    def __init__(self, root, context=None, endpoint="http://127.0.0.1:8765/mcp", *, legacy_tools=False):
        self.root, self.context, self.endpoint = str(root), context, endpoint
        self.legacy_tools = legacy_tools
        self.services = RemoteServices(self)
        self._executor = ThreadPoolExecutor(max_workers=1)

    async def _call(self, tool, operation, arguments):
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        endpoint = urlsplit(self.endpoint)
        health = urlunsplit(endpoint._replace(path='/health', query='', fragment=''))
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(health)
            response.raise_for_status()
            if Path(response.json()['root']).resolve() != Path(self.root).expanduser().resolve():
                raise RuntimeError('The MCP server owns another root; configure the service before using this client')
        async with streamable_http_client(self.endpoint) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                payload = {
                    "operation": operation,
                    "context": self.context,
                    "arguments": arguments or {},
                }
                if not self.legacy_tools:
                    # CLI/TUI consume full operation contracts; only conversational
                    # MCP tools default to compact presentation.
                    payload['detail'] = 'full'
                result = await session.call_tool(tool, payload)
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
        return self._sync("contextopus_query" if self.legacy_tools else "read", operation, arguments)

    def execute(self, operation, arguments=None):
        return self._sync("contextopus_execute" if self.legacy_tools else "write", operation, arguments)

    def close(self):
        self._executor.shutdown()

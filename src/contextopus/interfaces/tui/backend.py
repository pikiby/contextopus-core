"""Presentation adapter: all state and mutations use shared application API."""

import asyncio


class Backend:
    def __init__(self, application):
        self.application = application

    async def snapshot(self):
        local = None
        if hasattr(self.application, "endpoint"):
            from contextopus.integrations.service import status as service_status
            local = await asyncio.to_thread(service_status, self.application.root)
            if local["state"] != "running":
                return {"status": {"state": local["state"], "service": local,
                                   "mcp": {"server": local["state"], "client": "not_connected"}}, "settings": {}}
        try:
            status, settings = await asyncio.gather(
                asyncio.to_thread(self.application.query, "core.status"),
                asyncio.to_thread(self.application.query, "core.settings"),
            )
        except Exception as exc:
            if local is None:
                raise
            return {"status": {"state": "client_error", "service": local,
                               "mcp": {"server": "running", "client": "not_connected"},
                               "error": str(exc)}, "settings": {}}
        if local is not None:
            status["service"] = local
        return {"status": status, "settings": settings}

    async def service(self, action):
        from contextopus.integrations import service
        if action not in {"start", "stop", "restart"}:
            raise ValueError("Unknown lifecycle action")
        return await asyncio.to_thread(getattr(service, action), self.application.root)

    async def preview(self, changes):
        return await asyncio.to_thread(
            self.application.query, "core.settings_preview", {"changes": changes}
        )

    async def apply(self, revision):
        return await asyncio.to_thread(
            self.application.execute,
            "core.settings_apply",
            {"preview_revision": revision},
        )

    async def open_module(self, module):
        return await asyncio.to_thread(self.application.execute, module + ".open_tui")

    async def reconnect(self, client):
        from contextopus.integrations.reconnect import reconnect
        return await asyncio.to_thread(reconnect, client, self.application.root)

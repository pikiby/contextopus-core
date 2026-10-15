"""Presentation adapter: all state and mutations use shared application API."""

import asyncio


class Backend:
    def __init__(self, application):
        self.application = application

    async def snapshot(self):
        status, settings = await asyncio.gather(
            asyncio.to_thread(self.application.query, "core.status"),
            asyncio.to_thread(self.application.query, "core.settings"),
        )
        return {"status": status, "settings": settings}

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

import asyncio
from contextopus.interfaces.tui.backend import Backend

class Application:
    def __init__(self): self.calls = []
    def query(self, operation):
        self.calls.append(("query", operation))
        return {"operation": operation}
    def execute(self, operation, arguments=None):
        self.calls.append(("execute", operation, arguments))
        return {"ok": True}

def test_status_only_uses_shared_read_api():
    app = Application()
    result = asyncio.run(Backend(app).snapshot())
    assert result["status"]["operation"] == "core.status"
    assert sorted(app.calls) == [("query", "core.settings"), ("query", "core.status")]

def test_apply_requires_exact_preview_revision_in_api():
    app = Application()
    backend = Backend(app)
    asyncio.run(backend.apply("revision123"))
    assert app.calls == [("execute", "core.settings_apply", {"preview_revision": "revision123"})]

import pytest
from contextopus.interfaces.tui.app import ContextopusApp
from contextopus.interfaces.tui.render import main, settings
from contextopus.interfaces.tui.charts import History


class DemoApplication:
    """Explicit synthetic data; never used as a runtime fallback."""

    def __init__(self):
        self.archived = False
        self.calls = []

    def query(self, op, args=None):
        self.calls.append((op, args))
        if op == "core.status":
            return {
                "state": "idle",
                "database": {
                    "state": "available",
                    "stored_items": 1200,
                    "bytes": 25165824,
                },
                "index": {
                    "state": "ready",
                    "processed": 1200,
                    "total": 1200,
                    "remaining": 0,
                },
                "resources": {
                    "cpu_percent": 0,
                    "memory_percent": 3,
                    "memory_bytes": 515396075,
                },
                "usage": {"requests": 12, "errors": 0, "average_seconds": 0.04},
                "mcp": {"server": "running · HTTP", "verified_client": "unknown"},
                "modules": [
                    {"name": "workspace", "state": "available"},
                    {"name": "session_search", "state": "available"},
                ],
            }
        if op == "core.settings":
            return {
                "values": {
                    "include_archived": self.archived,
                    "searchN": 20,
                    "chunk_size": 512,
                },
                "sources": {},
            }
        if op == "core.settings_preview":
            return {
                "preview_revision": "demo",
                "consequences": "Future requests include archived objects.",
            }
        raise ValueError(op)

    def execute(self, op, args=None):
        self.calls.append((op, args))
        if op == "core.settings_apply":
            self.archived = True
            return {"saved": True}
        return {"ok": True}


def test_narrow_layout_and_unknown_are_honest():
    for width in (40, 79):
        text, actions = main({"status": {}, "settings": {}}, width)
        assert max(map(len, text.splitlines())) <= width
        assert "—" in text
        text, _ = settings({"settings": {"values": {}}}, width)
        assert max(map(len, text.splitlines())) <= width
    assert "Open Workspace" not in actions


def test_resize_does_not_add_samples():
    history = History()
    history.append(1, None)
    history.append(2, 0)
    history.lines(2)
    history.lines(2, width=25)
    assert len(history.samples) == 2


@pytest.mark.asyncio
async def test_keyboard_settings_preview_apply():
    app = ContextopusApp(DemoApplication())
    async with app.run_test(size=(79, 70)) as pilot:
        await pilot.press("down", "enter")
        assert app.page == "settings"
        await pilot.press("right", "down", "enter")
        assert app.preview["preview_revision"] == "demo"
        await pilot.press("down", "enter")
        assert app.backend.application.archived is True
        await pilot.press("q")
        assert app.page == "main"


def test_render_distinguishes_process_states_and_saved_counts():
    for state in ("processing", "idle", "stopped", "unavailable"):
        text, _ = main(
            {"status": {"state": state, "database": {"stored_items": 7}}}, 40
        )
        assert "Core " + state in text
        assert "Stored items    7" in text


@pytest.mark.asyncio
async def test_short_terminal_menu_bindings_open_settings_back_and_quit_without_execute():
    backend = DemoApplication()
    app = ContextopusApp(backend)
    async with app.run_test(size=(79, 24)) as pilot:
        viewport = app.query_one("#viewport")
        viewport.focus()
        assert viewport.max_scroll_y > 0
        await pilot.press("down")
        assert app.selected == 1
        await pilot.press("enter")
        assert app.page == "settings"
        await pilot.press("q")
        assert app.page == "main"
        await pilot.press("q")
    assert all(
        operation in {"core.status", "core.settings"} for operation, _ in backend.calls
    )


def test_real_fractional_duration_keeps_stat_columns_separate():
    snapshot = {"status": {"usage": {"average_seconds": 3.7808823883529374}}}
    wide, _ = main(snapshot, 79)
    assert "3.78 s" in wide
    assert "3.780882" not in wide
    assert "sEmpty" not in wide
    assert max(map(len, wide.splitlines())) <= 79

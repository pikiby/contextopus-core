"""Keyboard-only interface backed exclusively by the shared application API."""

import asyncio
import time
import subprocess
import textwrap
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Static
from .backend import Backend
from .charts import History
from . import render


class ContextopusApp(App):
    TITLE = "Contextopus"
    CSS = """
    Screen { background: transparent; }
    #viewport { height: auto; max-height: 100%; width: 100%; background: transparent; }
    #content { width: 79; max-width: 100%; height: auto; background: transparent; }
    """
    BINDINGS = [
        Binding("up", "up", "Select", priority=True),
        Binding("down", "down", "Select", priority=True),
        Binding("left", "change", "Change", priority=True),
        Binding("right", "change", "Change", priority=True),
        Binding("enter", "apply", "Apply", priority=True),
        Binding("q", "back", "Quit", priority=True),
    ]

    def __init__(self, application):
        super().__init__()
        self.backend = Backend(application)
        self.snapshot = {"status": {"state": "loading"}, "settings": {}}
        self.selected = 0
        self.page = "main"
        self.draft = None
        self.preview = None
        self.message = None
        self.history = {key: History() for key in ("cpu", "ram", "rate")}
        self.sample_time = time.monotonic()
        self.polling = False
        self.busy = False

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="viewport"):
            yield Static("", id="content")

    async def on_mount(self):
        await self.poll()
        self.set_interval(3, self.poll)

    async def poll(self):
        if self.polling:
            return
        self.polling = True
        try:
            self.snapshot = await self.backend.snapshot()
            observed_error = self.snapshot["status"].get("database", {}).get("error")
            if observed_error:
                self.message = observed_error
            self.sample_time = time.monotonic()
            r = self.snapshot["status"].get("resources", {})
            p = self.snapshot["status"].get("processing", {})
            for key, val in [
                ("cpu", r.get("cpu_percent")),
                ("ram", r.get("memory_percent")),
                ("rate", p.get("rate_per_minute")),
            ]:
                self.history[key].append(self.sample_time, val)
        except Exception as exc:
            self.message = str(exc)
            self.snapshot["status"]["state"] = "unavailable"
        finally:
            self.polling = False
            self.draw()

    def on_resize(self):
        self.draw()

    def draw(self):
        if not self.is_mounted:
            return
        width = min(79, self.size.width)
        if self.page == "settings":
            text, self.actions = render.settings(
                self.snapshot,
                width,
                self.selected,
                self.draft,
                self.preview,
                self.message,
            )
        elif self.page == "errors":
            text = (
                " CONTEXTOPUS · ERROR DETAILS\n\n "
                + textwrap.fill(self.message or "No observed error", max(1, width - 2))
                + "\n\n Q Back"
            )
            self.actions = ["Back"]
        else:
            text, self.actions = render.main(
                self.snapshot,
                width,
                self.selected,
                self.history,
                self.sample_time,
                self.message,
            )
        styled = Text(text, no_wrap=True, overflow="crop")
        position = 0
        resource = None
        resource_columns = []
        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            color = (
                "#56b6c2 bold"
                if line.startswith("▶") or stripped.startswith("CONTEXTOPUS")
                else "#56b6c2"
                if stripped == "CPU"
                else "#98c379"
                if stripped in ("RAM", "DATA & PROCESSING")
                else "#e5c07b"
                if stripped == "Processing"
                else "#808080"
                if "unavailable" in line or "stopped" in line
                else "#e06c75"
                if "error:" in line.lower()
                else "#e06c75"
                if stripped.startswith("Core error")
                else "#e5c07b"
                if stripped.startswith("Core idle")
                or stripped.startswith("Core processing")
                else None
            )
            if stripped == "DATA & PROCESSING":
                resource_columns = []
            if (
                self.page == "main"
                and any(word in line for word in ("CPU", "RAM", "Processing"))
                and not line.startswith(" Process:")
            ):
                resource_columns = [
                    (line.index(label), tint)
                    for label, tint in [
                        ("CPU", "#56b6c2"),
                        ("RAM", "#98c379"),
                        ("Processing", "#e5c07b"),
                    ]
                    if label in line
                ]
            for offset, tint in resource_columns:
                if offset < len(line):
                    styled.stylize(
                        tint,
                        position + offset,
                        min(position + offset + 25, position + len(line)),
                    )
            if stripped in ("CPU", "RAM", "Processing"):
                resource = {
                    "CPU": "#56b6c2",
                    "RAM": "#98c379",
                    "Processing": "#e5c07b",
                }[stripped]
            if stripped == "DATA & PROCESSING":
                resource = None
            if "[" in line and ("█" in line or "░" in line):
                if (
                    width >= 77
                    and self.page == "main"
                    and "[" in line[:26]
                    and "[" in line[26:51]
                ):
                    for offset, tint in (
                        (1, "#56b6c2"),
                        (26, "#98c379"),
                        (51, "#e5c07b"),
                    ):
                        styled.stylize(
                            tint,
                            position + offset,
                            min(position + offset + 25, position + len(line)),
                        )
                else:
                    styled.stylize(
                        resource or "#98c379", position, position + len(line)
                    )
            if color:
                styled.stylize(color, position, position + len(line))
            position += len(line)
        self.query_one("#content", Static).update(styled)

    def action_up(self):
        self.selected = (self.selected - 1) % len(self.actions)
        self.draw()

    def action_down(self):
        self.selected = (self.selected + 1) % len(self.actions)
        self.draw()

    def action_change(self):
        if self.page == "settings" and self.selected == 0:
            current = (
                self.snapshot.get("settings", {})
                .get("values", {})
                .get("include_archived", False)
                if self.draft is None
                else self.draft
            )
            self.draft = not current
            self.preview = None
            self.draw()

    def action_back(self):
        if self.page == "main":
            self.exit()
        else:
            self.page = "main"
            self.selected = 0
            self.preview = None
            self.draft = None
            self.draw()

    async def action_apply(self):
        if self.busy:
            return
        self.busy = True
        try:
            action = self.actions[self.selected]
            if action == "Quit":
                self.exit()
            elif action == "Back":
                self.action_back()
            elif action == "Settings":
                self.page = "settings"
                self.selected = 0
                self.message = None
            elif action == "Error details":
                self.page = "errors"
                self.selected = 0
            elif action.startswith("Include archived"):
                self.action_change()
            elif action == "Preview changes":
                draft = (
                    self.snapshot["settings"]["values"].get("include_archived", False)
                    if self.draft is None
                    else self.draft
                )
                self.preview = await self.backend.preview({"include_archived": draft})
                self.message = self.preview["consequences"]
            elif action == "Apply preview":
                if self.preview is None:
                    self.message = "Preview changes before applying."
                else:
                    await self.backend.apply(self.preview["preview_revision"])
                    self.preview = None
                    self.message = "Saved. Applies to future requests."
                    await self.poll()
            elif action == "Open Session search":
                # Child owns the terminal while the parent display is suspended.
                descriptor = await self.backend.open_module("session_search")
                with self.suspend():
                    child = await asyncio.to_thread(
                        subprocess.run, descriptor["argv"], check=False
                    )
                self.message = (
                    "Module closed."
                    if child.returncode == 0
                    else "Module failed: " + str(child.returncode)
                )
        except Exception as exc:
            self.message = str(exc)
        finally:
            self.busy = False
            self.draw()

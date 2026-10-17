"""Keyboard-only interface backed exclusively by the shared application API."""

import asyncio
import time
import subprocess
import textwrap
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Static, Input
from textual.screen import ModalScreen
from .backend import Backend
from .charts import History
from . import render


class ModuleSourceScreen(ModalScreen):
    """Collect an unpacked release path; Escape cancels without mutation."""
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, title="Update module: enter unpacked release directory; Escape cancels", value=""):
        super().__init__()
        self.prompt, self.initial = title, value

    def compose(self):
        yield Static(self.prompt)
        yield Input(value=self.initial, placeholder="Enter value", id="module-source")

    def on_mount(self):
        self.query_one(Input).focus()

    def on_input_submitted(self, event):
        if event.value.strip():
            self.dismiss(event.value.strip())

    def action_cancel(self):
        self.dismiss(None)


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
        self.module_items = []
        self.algorithm_catalog = []
        self.selection_scope = {"module": None, "context": None}
        self.selection_settings = {}
        self.selection_draft = None
        self.selection_preview = None
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
        elif self.page == "selection":
            text, self.actions = render.selection(self.selection_settings, self.algorithm_catalog, self.selection_draft, self.selection_scope, width, self.selected, self.selection_preview, self.message)
        elif self.page == "modules":
            text, self.actions = render.modules(self.module_items, width, self.selected, self.message)
        elif self.page == "connections":
            text, self.actions = render.connections(width, self.selected, self.message)
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
        self.selected_line = next(
            (row for row, line in enumerate(text.splitlines()) if line.startswith("▶")),
            None,
        )
        self.query_one("#content", Static).update(styled)

    def show_selected(self):
        viewport = self.query_one("#viewport", VerticalScroll)
        row = self.selected_line
        if row is None:
            return
        top = int(viewport.scroll_y)
        height = viewport.size.height
        if row < top:
            viewport.scroll_to(y=row, animate=False)
        elif row >= top + height:
            viewport.scroll_to(y=row - height + 1, animate=False)

    def check_action(self, action, parameters):
        if isinstance(self.screen, ModuleSourceScreen) and action in {"up", "down", "change", "apply", "back"}:
            return False
        return True

    async def perform_module_action(self, action, module, source=None):
        try:
            return await self.backend.module_action(action, module, source)
        finally:
            # A failed install/update can disable the old package. Never keep
            # a stale enabled row if the mutation or its status refresh fails.
            self.module_items = []
            self.module_items = await self.backend.modules()

    async def update_module_source(self, module, source):
        if not source:
            return
        self.busy = True
        self.message = "Updating " + module + "…"
        self.draw()
        try:
            result = await self.perform_module_action("update", module, source)
            self.message = module + ": " + result["state"]
        except Exception as exc:
            self.message = str(exc)
        finally:
            self.busy = False
            self.draw()

    async def run_module_tui(self, module, operation=None):
        descriptor = await self.backend.open_module(module, operation)
        argv = descriptor["argv"]
        if not isinstance(argv, list) or not argv or any(not isinstance(arg, str) for arg in argv):
            raise ValueError("Module TUI must return a nonempty argv list")
        with self.suspend():
            child = await asyncio.to_thread(subprocess.run, argv, check=False)
        self.message = "Module closed." if child.returncode == 0 else "Module failed: " + str(child.returncode)

    def action_up(self):
        self.selected = (self.selected - 1) % len(self.actions)
        self.draw()
        self.call_after_refresh(self.show_selected)

    def action_down(self):
        self.selected = (self.selected + 1) % len(self.actions)
        self.draw()
        self.call_after_refresh(self.show_selected)

    def cycle_algorithm(self):
        if not self.algorithm_catalog:
            raise ValueError("No search algorithms available")
        current = (self.selection_draft or self.selection_settings.get('values', {}).get('selection', {})).get('algorithm')
        ids = [item['id'] for item in self.algorithm_catalog]
        description = self.algorithm_catalog[(ids.index(current) + 1) % len(ids) if current in ids else 0]
        self.selection_draft = {'algorithm': description['id'], 'parameters': dict(description['defaults'])}
        self.selection_preview = None
        self.draw()

    async def selection_input(self, kind, value):
        if value is None:
            return
        import json
        try:
            parsed = json.loads(value)
            if kind == 'scope':
                if not isinstance(parsed, dict) or set(parsed) - {'module', 'context'}:
                    raise ValueError('Scope requires module and context keys')
                scope = {'module': parsed.get('module'), 'context': parsed.get('context')}
                if any(v is not None and (not isinstance(v, str) or not v.strip()) for v in scope.values()) or scope['context'] and not scope['module']:
                    raise ValueError('Context scope requires a module; names must be nonempty strings')
                settings = await self.backend.scoped_settings(**scope)
                self.selection_scope, self.selection_settings = scope, settings
                self.selection_draft = None
            else:
                import copy
                import jsonschema
                draft = copy.deepcopy(self.selection_draft or self.selection_settings['values']['selection'])
                description = next(item for item in self.algorithm_catalog if item['id'] == draft['algorithm'])
                jsonschema.validate(parsed, description['parameters_schema'])
                draft['parameters'] = parsed
                self.selection_draft = draft
            self.selection_preview = None
            self.message = None
        except Exception as exc:
            self.message = str(exc)
        self.draw()

    def action_change(self):
        if self.page == "selection" and self.actions[self.selected] == "Algorithm":
            self.cycle_algorithm()
            return
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
            elif action == "Search selection":
                self.selection_preview, self.selection_draft = None, None
                self.algorithm_catalog = await self.backend.algorithms()
                if isinstance(self.algorithm_catalog, dict):
                    self.algorithm_catalog = self.algorithm_catalog.get('algorithms', [])
                self.selection_settings = await self.backend.scoped_settings(**self.selection_scope)
                self.page, self.selected, self.message = "selection", 0, None
            elif self.page == "selection" and action != "Back":
                import json
                if action == "Algorithm":
                    self.cycle_algorithm()
                elif action in {"Scope", "Parameters JSON"}:
                    kind = 'scope' if action == 'Scope' else 'parameters'
                    value = self.selection_scope if kind == 'scope' else (self.selection_draft or self.selection_settings['values']['selection'])['parameters']
                    title = 'Scope JSON: root {"module":null,"context":null}; module or module+context' if kind == 'scope' else 'Parameters JSON; see algorithm schema and guidance below'
                    self.push_screen(ModuleSourceScreen(title, json.dumps(value)), lambda value: self.run_worker(self.selection_input(kind, value)) if value else None)
                elif action == "Preview selection":
                    draft = self.selection_draft or self.selection_settings['values']['selection']
                    self.selection_preview = await self.backend.preview({'selection': draft}, **self.selection_scope)
                    self.message = self.selection_preview['consequences']
                elif action == "Apply selection":
                    if self.selection_preview is None:
                        self.message = "Preview selection before applying."
                    else:
                        await self.backend.apply(self.selection_preview['preview_revision'])
                        self.selection_preview = None
                        self.selection_draft = None
                        self.selection_settings = await self.backend.scoped_settings(**self.selection_scope)
                        self.message = "Saved for future searches."
            elif action == "Modules":
                self.module_items = await self.backend.modules()
                self.page, self.selected, self.message = "modules", 0, None
            elif self.page == "modules" and action != "Back":
                verb, module = action.split(" ", 1)
                if verb == "Update":
                    self.push_screen(ModuleSourceScreen(), lambda source: self.run_worker(self.update_module_source(module, source)) if source else None)
                elif verb == "Open":
                    item = next(item for item in self.module_items if item["id"] == module)
                    await self.run_module_tui(module, item["open_tui"])
                else:
                    self.message = verb + " " + module + "…"
                    self.draw()
                    result = await self.perform_module_action(verb.lower(), module)
                    self.message = module + ": " + result["state"]
            elif action == "Error details":
                self.page = "errors"
                self.selected = 0
            elif action == "Client connections":
                self.page, self.selected, self.message = "connections", 0, None
            elif action in {"Reload Codex (all loaded threads)", "Claude Code recovery", "OpenCode recovery", "Crush recovery"}:
                client = {"Reload Codex (all loaded threads)": "codex", "Claude Code recovery": "claude-code",
                          "OpenCode recovery": "opencode", "Crush recovery": "crush"}[action]
                result = await self.backend.reconnect(client)
                self.message = result.get("instruction", result.get("note", result["status"]))
            elif action in {"Start MCP", "Stop MCP", "Restart MCP"}:
                result = await self.backend.service(action.split()[0].lower())
                self.message = "MCP: " + result["state"]
                self.selected = 0
                await self.poll()
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
                await self.run_module_tui("session_search")
        except Exception as exc:
            self.message = str(exc)
        finally:
            self.busy = False
            self.draw()

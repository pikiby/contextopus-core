"""Headless real TUI renders; all displayed state is an explicit synthetic fixture."""
import asyncio
from pathlib import Path
import runpy

from contextopus.core.filtering import AlgorithmRegistry
from contextopus.interfaces.tui.app import ContextopusApp
from contextopus.interfaces.tui import render

Demo = runpy.run_path('tests/test_contextopus_tui.py')['DemoApplication']
OUTPUT = Path('docs/media/tui')


async def main():
    app = ContextopusApp(Demo())
    async with app.run_test(size=(79, 60)) as pilot:
        app.page = 'selection'
        app.algorithm_catalog = AlgorithmRegistry().catalog()
        app.selection_scope = {'module': 'workspace', 'context': 'example-project'}
        app.selection_settings = {
            'values': {'selection': {'algorithm': 'distance_jump', 'parameters': {'N': 20}}},
            'sources': {'selection': {'algorithm': 'root', 'parameters': {'N': 'root'}}},
        }
        app.selection_draft = {'algorithm': 'nearest_n', 'parameters': {'N': 8}}
        app.selection_preview = {'preview_revision': 'synthetic-example-revision'}
        app.selected = 3
        app.message = 'EXAMPLE · synthetic fixture · pending nearest_n choice; no settings applied'
        app.draw()
        text, _ = render.selection(app.selection_settings, app.algorithm_catalog,
            app.selection_draft, app.selection_scope, 79, app.selected,
            app.selection_preview, app.message)
        await pilot.resize_terminal(79, len(text.splitlines()) + 2)
        await pilot.pause()
        app.save_screenshot(str(OUTPUT / 'selection-1.2-wide.svg'))
        app.page = 'modules'
        app.module_items = [
            {'id': 'synk', 'version': '1.0.0', 'state': 'enabled'},
            {'id': 'example_notes', 'version': '0.1.0', 'state': 'discovered'},
        ]
        app.selected = 2
        app.message = 'EXAMPLE · synthetic fixture · no module prepared, enabled or updated by this capture'
        app.draw()
        text, _ = render.modules(app.module_items, 79, app.selected, app.message)
        await pilot.resize_terminal(79, len(text.splitlines()) + 2)
        await pilot.pause()
        app.save_screenshot(str(OUTPUT / 'modules-1.2-wide.svg'))
        app.exit()


asyncio.run(main())

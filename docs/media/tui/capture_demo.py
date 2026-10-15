import asyncio,runpy
from pathlib import Path
from contextopus.interfaces.tui.app import ContextopusApp
from contextopus.interfaces.tui import render
Demo=runpy.run_path('tests/test_contextopus_tui.py')['DemoApplication']
async def main():
    folder=Path('docs/media/tui')
    for width,height,label in [(79,47,'wide'),(40,75,'narrow')]:
        app=ContextopusApp(Demo())
        async with app.run_test(size=(width,height)) as pilot:
            app.message='EXAMPLE · synthetic demonstration data'
            app.draw(); await pilot.resize_terminal(width,len(render.main(app.snapshot,width)[0].splitlines())+2); await pilot.pause()
            app.save_screenshot(str(folder/f'main-{label}.svg'))
            await pilot.press('down','enter'); await pilot.resize_terminal(width,len(render.settings(app.snapshot,width)[0].splitlines())+2); await pilot.pause()
            app.message='EXAMPLE · synthetic demonstration data'; app.draw(); await pilot.pause()
            app.save_screenshot(str(folder/f'settings-{label}.svg'))
            await pilot.press('right','down','enter'); app.message='EXAMPLE · synthetic demonstration data'; app.draw(); await pilot.pause()
            app.save_screenshot(str(folder/f'preview-{label}.svg'))
    app=ContextopusApp(Demo())
    async with app.run_test(size=(79,43)) as pilot:
        for state in ('processing','stopped','unavailable'):
            app.snapshot['status']['state']=state
            if state=='unavailable': app.snapshot['status']['resources']={}
            app.message='EXAMPLE · synthetic '+state+' state'
            app.draw(); await pilot.pause()
            app.save_screenshot(str(folder/f'state-{state}.svg'))
asyncio.run(main())

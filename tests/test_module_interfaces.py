import json
import pytest
from contextopus.interfaces.cli.main import main
from contextopus.interfaces.tui.app import ContextopusApp, ModuleSourceScreen
from contextopus.interfaces.tui.backend import Backend


class ModuleAPI:
    def __init__(self, *args, **kwargs):
        self.calls = []
        self.state = 'discovered'

    def close(self):
        pass

    def query(self, operation, arguments=None):
        self.calls.append(('query', operation, arguments))
        if operation == 'core.modules':
            return [{'id':'sample', 'state':self.state, 'version':'1', 'open_tui':'sample.launch'}]
        if operation == 'describe':
            return {'kind':'query'}
        return {'values': {}} if operation == 'core.settings' else {'state':'idle'}

    def execute(self, operation, arguments=None):
        self.calls.append(('execute', operation, arguments))
        self.state = {'prepare':'prepared','enable':'enabled','disable':'prepared','update':'enabled'}[operation.removeprefix('core.module_')]
        return {'state':self.state}


def test_cli_routes_module_commands_to_shared_operations(tmp_path, monkeypatch, capsys):
    api = ModuleAPI()
    monkeypatch.setattr('contextopus.integrations.remote.RemoteApplication', lambda *a, **kw: api)
    assert main(['--root', str(tmp_path), 'modules']) == 0
    assert json.loads(capsys.readouterr().out)[0]['id'] == 'sample'
    assert main(['--root', str(tmp_path), 'modules', 'update', 'sample', '--source', str(tmp_path)]) == 0
    assert api.calls[-1] == ('execute', 'core.module_update', {'module':'sample', 'source':str(tmp_path)})


@pytest.mark.asyncio
async def test_keyboard_module_lifecycle_and_update_path(monkeypatch):
    async def inline(function, *args, **kwargs):
        return function(*args, **kwargs)
    monkeypatch.setattr('contextopus.interfaces.tui.backend.asyncio.to_thread', inline)
    api = ModuleAPI()
    app = ContextopusApp(api)
    async with app.run_test(size=(79, 40)) as pilot:
        app.selected = app.actions.index('Modules')
        await pilot.press('enter')
        assert app.page == 'modules'
        await pilot.press('enter')
        assert api.state == 'prepared'
        await pilot.press('down', 'enter')
        assert api.state == 'enabled'
        await pilot.press('down', 'enter')
        assert isinstance(app.screen, ModuleSourceScreen)
        # Q must reach the input instead of closing the parent page.
        await pilot.press('q')
        assert app.screen.query_one('Input').value == 'q'
        await pilot.press('escape')
        assert app.page == 'modules'
        await pilot.press('enter')
        app.screen.query_one('Input').value = '/tmp/release'
        await pilot.press('enter')
        await app.workers.wait_for_complete()
        assert api.calls[-2] == ('execute', 'core.module_update', {'module':'sample', 'source':'/tmp/release'})
        await pilot.press('q')
        assert app.page == 'main'
        await pilot.press('q')



@pytest.mark.asyncio
async def test_dynamic_open_uses_declared_operation_kind(monkeypatch):
    async def inline(function, *args, **kwargs):
        return function(*args, **kwargs)
    monkeypatch.setattr('contextopus.interfaces.tui.backend.asyncio.to_thread', inline)
    api = ModuleAPI()
    await Backend(api).open_module('sample', 'sample.launch')
    assert api.calls == [('query','describe',{'operation':'sample.launch'}), ('query','sample.launch',None)]


@pytest.mark.asyncio
async def test_selection_catalog_scope_validation_and_preview(monkeypatch):
    import copy
    from contextopus.core.filtering import AlgorithmRegistry
    class SelectionAPI(ModuleAPI):
        def query(self, operation, arguments=None):
            self.calls.append(('query', operation, arguments))
            if operation == 'core.algorithms':
                return AlgorithmRegistry().catalog()
            if operation == 'core.settings':
                return {'values': {'selection': {'algorithm':'distance_jump', 'parameters':{'N':20, 'min_jump':0.01}}}, 'sources':{'selection':{'algorithm':'root', 'parameters':{'N':'root'}}}}
            if operation == 'core.settings_preview':
                return {'preview_revision':'selection-revision', 'consequences':'Future searches'}
            return {'state':'idle'}
        def execute(self, operation, arguments=None):
            self.calls.append(('execute', operation, arguments))
            return {'saved':True}
    async def inline(function, *args, **kwargs):
        return function(*args, **kwargs)
    monkeypatch.setattr('contextopus.interfaces.tui.backend.asyncio.to_thread', inline)
    api = SelectionAPI()
    app = ContextopusApp(api)
    async with app.run_test(size=(79, 45)) as pilot:
        app.page = 'settings'
        app.draw()
        app.selected = app.actions.index('Search selection')
        await pilot.press('enter')
        assert app.page == 'selection'
        assert app.algorithm_catalog == AlgorithmRegistry().catalog()
        await app.selection_input('scope', '{"module":"workspace","context":"demo"}')
        assert app.selection_scope == {'module':'workspace','context':'demo'}
        app.selected = app.actions.index('Algorithm')
        for _ in app.algorithm_catalog:
            await pilot.press('right')
            if app.selection_draft['algorithm'] == 'nearest_n':
                break
        assert app.selection_draft['algorithm'] == 'nearest_n'
        assert 'min_jump' not in app.selection_draft['parameters']
        before = copy.deepcopy(app.selection_draft)
        await app.selection_input('parameters', '{"N":"wrong"}')
        assert app.selection_draft == before
        assert app.message
        await app.selection_input('parameters', '{"N":3}')
        app.selected = app.actions.index('Apply selection')
        await pilot.press('enter')
        assert 'Preview selection' in app.message
        assert not any(call[0] == 'execute' for call in api.calls)
        app.selected = app.actions.index('Preview selection')
        await pilot.press('enter')
        assert ('query','core.settings_preview', {'changes':{'selection':{'algorithm':'nearest_n','parameters':{'N':3}}},'module':'workspace','context':'demo'}) in api.calls
        app.selected = app.actions.index('Apply selection')
        await pilot.press('enter')
        assert ('execute','core.settings_apply',{'preview_revision':'selection-revision'}) in api.calls

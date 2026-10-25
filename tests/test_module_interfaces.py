import json
from pathlib import Path
import shutil
import pytest
from contextopus.interfaces.cli.main import main


def test_catalog_example_installs_and_keeps_linked_records_after_restart(tmp_path):
    from contextopus.startup import Application

    example = Path(__file__).resolve().parents[1] / 'examples/modules/catalog-demo'
    shutil.copytree(example, tmp_path / 'modules/catalog-demo')
    app = Application(tmp_path, discover=False)
    try:
        assert app.query('core.modules')[0]['state'] == 'storage_pending'
        assert not (tmp_path / 'core/storage/modules').exists()
        assert app.execute('core.module_install', {'module':'catalog-demo'})['state'] == 'enabled'
        app.execute('catalog-demo.session_put', {'id':'s1', 'title':'A session'})
        app.execute('catalog-demo.message_put', {'id':'m1', 'session_id':'s1', 'body':'Linked text'})
        assert app.query('catalog-demo.sessions')['rows'] == [
            {'id':'s1', 'title':'A session', 'message_count':1}]
        assert app.query('catalog-demo.messages', {'session_id':'s1'})['rows'] == [
            {'id':'m1', 'session_id':'s1', 'title':'A session', 'body':'Linked text'}]
    finally:
        app.close()
    rebuilt = Application(tmp_path, discover=False)
    try:
        assert rebuilt.execute('core.module_install', {'module':'catalog-demo'})['state'] == 'enabled'
        assert rebuilt.query('catalog-demo.sessions')['rows'][0]['message_count'] == 1
        rebuilt.execute('core.module_disable', {'module':'catalog-demo'})
        assert rebuilt.query('core.modules')[0]['state'] == 'prepared'
        rebuilt.execute('core.module_install', {'module':'catalog-demo'})
        assert rebuilt.query('catalog-demo.messages', {'session_id':'s1'})['rows'][0]['body'] == 'Linked text'
    finally:
        rebuilt.close()


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
        self.state = {'install':'enabled','prepare':'prepared','enable':'enabled','disable':'prepared','update':'enabled'}[operation.removeprefix('core.module_')]
        return {'state':self.state}


def test_cli_routes_module_commands_to_shared_operations(tmp_path, monkeypatch, capsys):
    api = ModuleAPI()
    monkeypatch.setattr('contextopus.integrations.remote.RemoteApplication', lambda *a, **kw: api)
    assert main(['--root', str(tmp_path), 'modules']) == 0
    assert json.loads(capsys.readouterr().out)[0]['id'] == 'sample'
    assert main(['--root', str(tmp_path), 'modules', 'install', 'sample']) == 0
    assert api.calls[-1] == ('execute', 'core.module_install', {'module':'sample'})
    assert json.loads(capsys.readouterr().out)['state'] == 'enabled'
    assert main(['--root', str(tmp_path), 'modules', 'update', 'sample', '--source', str(tmp_path)]) == 0
    assert api.calls[-1] == ('execute', 'core.module_update', {'module':'sample', 'source':str(tmp_path)})

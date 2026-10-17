"""Folder modules use Core-owned schema and data APIs through their real child."""
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import time

import pytest

from contextopus.core.module_management import ModuleManager, ModuleManifestReader
from contextopus.core.operations import OperationRegistry, OperationSpec
from contextopus.core.storage import StorageLayout
from contextopus.startup import Application

FIRST = 'CREATE TABLE "{{module}}::sessions" (id TEXT PRIMARY KEY, title TEXT NOT NULL);'
SECOND = 'ALTER TABLE "{{module}}::sessions" ADD COLUMN archived INTEGER NOT NULL DEFAULT 0;'
ADAPTER = '''def save(args, core):
    print('handler log belongs on stderr')
    return core.storage.execute('INSERT INTO "{{module}}::sessions" (id,title) VALUES (?,?)', [args['id'],args['title']])
def read(args, core):
    return core.storage.query('SELECT id,title FROM "{{module}}::sessions" ORDER BY id')
def forbidden(args, core):
    return core.storage.execute('DELETE FROM "{{module}}::sessions"')
'''


def release(path, version=1, *, second=SECOND, maximum=None):
    package = path / 'package'
    (package / 'migrations').mkdir(parents=True)
    (package / 'migrations/001-schema.sql').write_text(FIRST)
    if version == 2:
        (package / 'migrations/002-upgrade.sql').write_text(second)
    (package / 'adapter.py').write_text(ADAPTER)
    manifest = {'id': 'sample', 'version': str(version),
        'storage': {'engine': 'sqlite', 'schema_version': version, 'migrations': 'migrations',
                    'compatible_versions': {'min': version, 'max': maximum or version}},
        'operations': [{'name': 'sample.' + name, 'kind': kind, 'handler': 'adapter.py:' + name,
                        'protocol': 'contextopus-core-v1'}
                       for name, kind in [('save', 'execute'), ('read', 'query'), ('forbidden', 'query')]]}
    (path / 'module.json').write_text(json.dumps(manifest))
    return manifest


def manager(root):
    return ModuleManager(SimpleNamespace(layout=StorageLayout(root), registry=OperationRegistry()))


def test_folder_install_uses_parent_storage_and_application_guard(tmp_path, monkeypatch):
    release(tmp_path / 'modules/sample')
    with Application(tmp_path, discover=False) as app:
        assert app.query('core.modules')[0]['state'] == 'storage_pending'
        assert not app.module_storage.path.exists()
        app.execute('core.module_prepare', {'module': 'sample'})
        with pytest.raises(ValueError, match='not ready'):
            app.execute('core.module_enable', {'module': 'sample'})
        assert not app.module_storage.path.exists()
        installed = app.execute('core.module_install', {'module': 'sample'})
        assert installed['state'] == 'enabled'
        assert installed['storage']['current_version'] == 1
        from contextopus.core.storage import _root_lock
        observed = []
        execute = app.module_storage.execute
        def checked(*args, **kwargs):
            observed.append(getattr(_root_lock(tmp_path)[1], 'depth', 0))
            return execute(*args, **kwargs)
        monkeypatch.setattr(app.module_storage, 'execute', checked)
        app.execute('sample.save', {'id': 'one', 'title': 'First session'})
        assert observed and observed[0] > 0
        assert app.query('sample.read')['rows'] == [{'id': 'one', 'title': 'First session'}]
        with pytest.raises(RuntimeError, match='Query operations cannot write'):
            app.query('sample.forbidden')
        assert len(app.query('sample.read')['rows']) == 1
        assert app.execute('core.module_install', {'module': 'sample'})['state'] == 'enabled'
    with Application(tmp_path, discover=False) as restored:
        assert restored.query('sample.read')['rows'][0]['title'] == 'First session'


@pytest.mark.parametrize('storage', [None, {'engine': 'postgres'},
    {'engine': 'sqlite', 'schema_version': 1, 'migrations': '../outside', 'compatible_versions': {'min': 1,'max': 1}}])
def test_manifest_storage_is_validated_without_creation(tmp_path, storage):
    path = tmp_path / 'modules/sample'
    manifest = release(path)
    manifest['storage'] = storage
    (path / 'module.json').write_text(json.dumps(manifest))
    app = manager(tmp_path)
    assert app.discover()[0]['state'] == 'error'
    assert not app.app.module_storage.path.exists()
    with pytest.raises(ValueError):
        app.install('sample')


def test_failed_migration_retains_old_code_and_data_then_retry_succeeds(tmp_path):
    path = tmp_path / 'modules/sample'
    release(path)
    app = manager(tmp_path)
    app.install('sample')
    app.app.registry.dispatch('execute', 'sample.save', {'id': 'one', 'title': 'Keep'})
    replacement = tmp_path / 'next'
    release(replacement, 2, second=SECOND + '\nINVALID SQL;')
    with pytest.raises(ValueError):
        app.update('sample', str(replacement))
    assert app._code(path) == path
    assert app.state['sample']['enabled'] is True
    assert app._storage('sample', app._manifest('sample'))['current_version'] == 1
    assert app.app.registry.dispatch('query', 'sample.read')['rows'][0]['title'] == 'Keep'
    (replacement / 'package/migrations/002-upgrade.sql').write_text(SECOND)
    assert app.update('sample', str(replacement))['state'] == 'enabled'
    assert app._storage('sample', app._manifest('sample'))['current_version'] == 2
    assert app.app.registry.dispatch('query', 'sample.read')['rows'][0]['title'] == 'Keep'
    with pytest.raises(ValueError, match='preflight failed'):
        # Code-only rollback must not reactivate old unsupported code.
        (path / '.current.json').unlink()
        app.prepare('sample')
        app.enable('sample')
    app.refresh()
    assert 'sample.read' not in app.app.registry._operations


def test_schema_advanced_activation_failure_leaves_old_code_disabled(tmp_path):
    path = tmp_path / 'modules/sample'
    release(path)
    app = manager(tmp_path)
    app.install('sample')
    app.app.registry.dispatch('execute', 'sample.save', {'id': 'one', 'title': 'Keep'})
    # A conflicting registry contribution rejects activation after schema commit.
    app.app.registry.register(OperationSpec('sample.conflict', 'query', {}, lambda context: None))
    replacement = tmp_path / 'next'
    manifest = release(replacement, 2)
    manifest['operations'].append({'name':'sample.conflict','kind':'query','handler':'adapter.py:read'})
    (replacement / 'module.json').write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match='previous code cannot reactivate'):
        app.update('sample', str(replacement))
    assert app._code(path) == path
    assert app.state['sample']['enabled'] is False
    assert 'sample.read' not in app.app.registry._operations
    assert app.app.module_storage.query('sample', 'SELECT title FROM "{{module}}::sessions"')['rows'] == [{'title': 'Keep'}]
    assert manager(tmp_path).discover()[0]['storage']['current_version'] == 2
    app.app.registry._operations.pop('sample.conflict')
    assert app.update('sample', str(replacement))['state'] == 'prepared'
    assert app.install('sample')['state'] == 'enabled'


def test_compatible_rollback_keeps_new_schema(tmp_path):
    path = tmp_path / 'modules/sample'
    release(path, maximum=2)
    app = manager(tmp_path)
    app.install('sample')
    replacement = tmp_path / 'next'
    release(replacement, 2)
    app.update('sample', str(replacement))
    (path / '.current.json').unlink()
    app.prepare('sample')
    assert app.enable('sample')['state'] == 'enabled'
    assert app._storage('sample', app._manifest('sample'))['current_version'] == 2


def test_refresh_and_algorithm_source_reader_never_migrate(tmp_path, monkeypatch):
    release(tmp_path / 'modules/sample')
    app = manager(tmp_path)
    app.prepare('sample')
    monkeypatch.setattr(app.app.module_storage, 'apply', lambda *a, **kw: pytest.fail('implicit migration'))
    app.state['sample']['enabled'] = True
    app._save()
    app.refresh()
    assert 'sample.read' not in app.app.registry._operations
    directories, _, errors = ModuleManifestReader(StorageLayout(tmp_path)).inspect_sources('procedures')
    assert directories == [] and errors
    assert not app.app.module_storage.path.exists()


def test_command_protocol_is_language_independent(tmp_path):
    path = tmp_path / 'modules/sample'
    manifest = release(path)
    script = path / 'package/wire.py'
    script.write_text('''import json,sys
request=json.loads(sys.stdin.readline())
print(json.dumps({'type':'call','id':'read','method':'storage.query','arguments':{'sql':'SELECT count(*) AS n FROM "{{module}}::sessions"'}}),flush=True)
response=json.loads(sys.stdin.readline())
print(json.dumps({'type':'result','result':{'n':response['result']['rows'][0]['n']}}),flush=True)
''')
    manifest['operations'] = [{'name':'sample.wire','kind':'query','protocol':'contextopus-core-v1',
                               'command':[sys.executable, 'wire.py']}]
    (path / 'module.json').write_text(json.dumps(manifest))
    app = manager(tmp_path)
    app.install('sample')
    assert app.app.registry.dispatch('query', 'sample.wire') == {'n': 0}


def test_child_uses_one_absolute_deadline_and_is_reaped(tmp_path):
    path = tmp_path / 'modules/sample'
    manifest = release(path)
    (path / 'package/adapter.py').write_text('''import os,time
from pathlib import Path
def read(args, core):
    Path(args['pidfile']).write_text(str(os.getpid()))
    for i in range(100):
        core.storage.query('SELECT count(*) AS n FROM "{{module}}::sessions"')
        time.sleep(.1)
''')
    manifest['operations'] = [{'name':'sample.read','kind':'query','handler':'adapter.py:read',
                               'protocol':'contextopus-core-v1','timeout':.35}]
    (path / 'module.json').write_text(json.dumps(manifest))
    app = manager(tmp_path)
    app.install('sample')
    before = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        app.app.registry.dispatch('query','sample.read',{'pidfile':str(tmp_path/'pid')})
    assert time.monotonic() - before < 3
    # The bridge waits/reaps its direct child; verify with the platform API.
    pid = int((tmp_path/'pid').read_text())
    if sys.platform != 'win32':
        import os
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


def test_python_module_venv_needs_no_core_install(tmp_path, monkeypatch):
    import venv
    path = tmp_path / 'modules/sample'
    release(path)
    monkeypatch.delenv('PYTHONPATH', raising=False)
    venv.EnvBuilder(with_pip=False).create(path / '.venv')
    adapter = path / 'package/adapter.py'
    (path / 'package/helper.py').write_text('VALUE = 1\n')
    adapter.write_text('import helper, importlib.util\nassert helper.VALUE == 1\nassert importlib.util.find_spec("contextopus") is None\n' + ADAPTER)
    app = manager(tmp_path)
    app.install('sample')
    app.app.registry.dispatch('execute','sample.save',{'id':'standalone','title':'No Core imports'})
    assert app.app.registry.dispatch('query','sample.read')['rows'] == [{'id':'standalone','title':'No Core imports'}]
    assert not (path / 'package/__pycache__').exists()


def assert_terminated(pid):
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, __import__('ctypes').POINTER(wintypes.DWORD)]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x1000, False, pid)
        if handle:
            try:
                status = wintypes.DWORD()
                assert api.GetExitCodeProcess(handle, __import__('ctypes').byref(status))
                assert status.value != 259  # STILL_ACTIVE
            finally:
                api.CloseHandle(handle)
    else:
        import os
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        # An orphan may briefly remain as an already terminated zombie under PID 1.
        state = Path(f'/proc/{pid}/stat')
        assert state.exists() and state.read_text().split()[2] == 'Z'


def test_rejected_write_reaps_handler(tmp_path):
    path = tmp_path / 'modules/sample'
    manifest = release(path)
    (path / 'package/adapter.py').write_text('''from pathlib import Path
import os
def save(args, core):
    Path(args['pidfile']).write_text(str(os.getpid()))
    return core.storage.execute('INSERT INTO "{{module}}::sessions" (id,title) VALUES (?,?)', ['bad',None])
''')
    manifest['operations'] = [manifest['operations'][0]]
    (path / 'module.json').write_text(json.dumps(manifest))
    app = manager(tmp_path)
    app.install('sample')
    with pytest.raises(RuntimeError, match='NOT NULL'):
        app.app.registry.dispatch('execute','sample.save',{'pidfile':str(tmp_path/'pid')})
    assert_terminated(int((tmp_path/'pid').read_text()))
    assert app.app.module_storage.query('sample','SELECT * FROM "{{module}}::sessions"')['rows'] == []


def test_child_descendants_terminated_after_final_result(tmp_path):
    path = tmp_path / 'modules/sample'
    manifest = release(path)
    (path / 'package/adapter.py').write_text('''import subprocess,sys,time
from pathlib import Path
def read(args, core):
    child = subprocess.Popen([sys.executable,'-c',"import os,sys,time; from pathlib import Path; Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(100)",args['pidfile']])
    for i in range(100):
        if Path(args['pidfile']).exists(): return {'ok':True}
        time.sleep(.01)
    raise RuntimeError('descendant did not start')
''')
    manifest['operations'] = [{'name':'sample.read','kind':'query','handler':'adapter.py:read',
                               'protocol':'contextopus-core-v1','timeout':5}]
    (path / 'module.json').write_text(json.dumps(manifest))
    app = manager(tmp_path)
    app.install('sample')
    assert app.app.registry.dispatch('query','sample.read',{'pidfile':str(tmp_path/'pid')}) == {'ok':True}
    deadline = time.monotonic() + 2
    while True:
        try:
            assert_terminated(int((tmp_path/'pid').read_text()))
            break
        except AssertionError:
            if time.monotonic() > deadline:
                raise
            time.sleep(.01)


def test_python_client_preserves_named_sql_parameters(tmp_path):
    path = tmp_path / 'modules/sample'
    manifest = release(path)
    (path / 'package/adapter.py').write_text('''def save(args, core):
    core.storage.execute('INSERT INTO "{{module}}::sessions" (id,title) VALUES (:id,:title)', {'id':args['id'], 'title':args['title']})
    return core.storage.query('SELECT id,title FROM "{{module}}::sessions" WHERE id=:id', {'id':args['id']})
''')
    manifest['operations'] = [manifest['operations'][0]]
    (path / 'module.json').write_text(json.dumps(manifest))
    app = manager(tmp_path)
    app.install('sample')
    assert app.app.registry.dispatch('execute','sample.save',{'id':'actual-id','title':'Actual title'})['rows'] == [{'id':'actual-id','title':'Actual title'}]


def test_refresh_rechecks_schema_even_when_code_fingerprint_is_unchanged(tmp_path):
    release(tmp_path / 'modules/sample')
    app = manager(tmp_path)
    app.install('sample')
    fingerprint = app._active_fingerprints['sample']
    replacement = tmp_path / 'next'
    manifest = release(replacement, 2)
    service = app.app.module_storage
    plan = service.prepare('sample', manifest['storage'], replacement/'package')
    service.apply('sample', manifest['storage'], replacement/'package', plan['revision'])
    assert app._digest('sample') == fingerprint
    app.refresh()
    assert 'sample.read' not in app.app.registry._operations
    assert app.discover()[0]['storage']['current_version'] == 2


def test_native_registered_module_is_not_taken_over(tmp_path):
    release(tmp_path / 'modules/sample')
    registry = OperationRegistry()
    registry.register_module('sample', state='available')
    registry.register(OperationSpec('sample.native','query',{},lambda context: {'native': True}))
    app = ModuleManager(SimpleNamespace(layout=StorageLayout(tmp_path),registry=registry))
    with pytest.raises(ValueError, match='Built-in'):
        app.install('sample')
    assert registry.dispatch('query','sample.native') == {'native':True}
    assert not app.app.module_storage.path.exists()


def test_native_entrypoint_receives_shared_storage_before_registration(tmp_path, monkeypatch):
    seen = []
    def register(app):
        seen.append(app.module_storage)
        assert app.module_storage.path == tmp_path / 'core/storage/modules.sqlite3'
        assert not app.module_storage.path.exists()
        app.registry.register_module('native-catalog', state='available')
        app.registry.register(OperationSpec('native-catalog.status','query',{},
            lambda context: {'ready': True}))
    entry = SimpleNamespace(name='native-catalog',load=lambda:register)
    monkeypatch.setattr('contextopus.startup.metadata.entry_points',lambda **kwargs:[entry])
    with Application(tmp_path) as app:
        assert seen == [app.module_storage]
        assert app.query('native-catalog.status') == {'ready': True}
        assert not app.module_storage.path.exists()


def test_mcp_installs_folder_module_then_saves_and_reads_catalog(tmp_path, monkeypatch):
    import asyncio
    from contextopus.interfaces.mcp import server
    from test_mcp_v13 import value
    release(tmp_path / 'modules/sample')
    with Application(tmp_path, discover=False) as app:
        owner = SimpleNamespace(application=lambda *a, **kw: app,
            resources=SimpleNamespace(start_services=lambda:None),
            current_root=lambda:str(tmp_path), close=lambda:None)
        monkeypatch.setattr(server,'ServerOwner',lambda root:owner)
        mcp = server.create_server(tmp_path)
        def call(tool, operation, arguments=None):
            return value(asyncio.run(mcp.call_tool(tool,{'operation':operation,
                'arguments':arguments or {},'work_root':str(tmp_path)})))
        assert call('read','core.modules')[0]['state'] == 'storage_pending'
        assert call('write','core.module_install',{'module':'sample'})['state'] == 'enabled'
        assert call('write','sample.save',{'id':'mcp-session','title':'Saved through MCP'})['rowcount'] == 1
        assert call('read','sample.read')['rows'] == [{'id':'mcp-session','title':'Saved through MCP'}]
        with pytest.raises(Exception,match='requires execute'):
            call('read','sample.save',{'id':'wrong','title':'Rejected'})
        assert len(call('read','sample.read')['rows']) == 1


def test_install_orders_dependencies_before_schema_and_activation(tmp_path, monkeypatch):
    path = tmp_path / 'modules/sample'
    manifest = release(path)
    manifest['dependencies'] = {'python':['example-dependency==1']}
    (path/'module.json').write_text(json.dumps(manifest))
    app = manager(tmp_path)
    observed = []
    def dependency(argv, **kwargs):
        observed.append('venv' if argv[:2] == ['uv','venv'] else 'dependencies')
    monkeypatch.setattr('contextopus.core.module_management.subprocess.run', dependency)
    apply = app.app.module_storage.apply
    def schema(*args, **kwargs):
        observed.append('schema')
        return apply(*args, **kwargs)
    monkeypatch.setattr(app.app.module_storage,'apply',schema)
    activate = app._activate
    def activation(*args, **kwargs):
        observed.append('activation')
        return activate(*args, **kwargs)
    monkeypatch.setattr(app,'_activate',activation)
    assert app.install('sample')['state'] == 'enabled'
    assert observed == ['venv','dependencies','schema','activation']


def test_failed_dependencies_do_not_create_schema_or_enable(tmp_path, monkeypatch):
    path = tmp_path / 'modules/sample'
    manifest = release(path)
    manifest['dependencies'] = {'python':['missing-dependency==1']}
    (path/'module.json').write_text(json.dumps(manifest))
    app = manager(tmp_path)
    def fail(argv, **kwargs):
        raise subprocess.CalledProcessError(1,argv)
    monkeypatch.setattr('contextopus.core.module_management.subprocess.run',fail)
    with pytest.raises(subprocess.CalledProcessError):
        app.install('sample')
    assert not app.app.module_storage.path.exists()
    assert app.state['sample']['enabled'] is False
    assert not app.loaded

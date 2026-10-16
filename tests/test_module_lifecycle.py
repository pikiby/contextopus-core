import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from contextopus.core.operations import OperationRegistry, OperationSpec
from contextopus.core.module_management import ModuleManager


def release(path, version='1.0', **changes):
    (path / 'package').mkdir(parents=True)
    (path / 'package/adapter.py').write_text('def status(args):\n    return {"version": "' + version + '"}\n')
    manifest = dict(id='sample', version=version, core_requires='>=1', operations=[dict(name='sample.status', kind='query', handler='adapter.py:status', arguments_schema={'type':'object', 'additionalProperties':False})])
    manifest.update(changes)
    (path / 'module.json').write_text(json.dumps(manifest))


def manager(root):
    return ModuleManager(SimpleNamespace(layout=SimpleNamespace(root=root), registry=OperationRegistry()))


def test_opt_in_persistence_update_preserves_data(tmp_path):
    path = tmp_path / 'modules/sample'
    release(path)
    app = manager(tmp_path)
    assert app.discover()[0]['state'] == 'discovered'
    assert not app.app.registry._operations
    app.prepare('sample')
    app.enable('sample')
    assert app.app.registry.dispatch('query', 'sample.status') == {'version':'1.0'}
    (path / 'data/important').write_text('keep')
    (path / 'config/options').write_text('keep too')
    replacement = tmp_path / 'replacement'
    release(replacement, '2.0')
    app.update('sample', str(replacement))
    assert app.app.registry.dispatch('query', 'sample.status') == {'version':'2.0'}
    rebuilt = manager(tmp_path)
    assert rebuilt.discover()[0]['state'] == 'enabled'
    assert (path / 'data/important').read_text() == 'keep'
    assert (path / 'config/options').read_text() == 'keep too'
    rebuilt.disable('sample')
    assert manager(tmp_path).discover()[0]['state'] == 'prepared'


def test_broken_module_isolation_and_changed_code(tmp_path):
    release(tmp_path / 'modules/sample')
    broken = tmp_path / 'modules/broken'
    broken.mkdir()
    (broken / 'module.json').write_text('bad json')
    app = manager(tmp_path)
    assert {x['id']:x['state'] for x in app.discover()} == {'broken':'error','sample':'discovered'}
    app.prepare('sample')
    (tmp_path / 'modules/sample/package/adapter.py').write_text('raise RuntimeError("must not execute discovery")')
    with pytest.raises(ValueError, match='changed'):
        app.enable('sample')
    assert not app.app.registry._operations


def test_registry_batch_is_atomic():
    registry = OperationRegistry()
    spec = lambda name: OperationSpec(name, 'query', {}, lambda c: None)
    registry.register(spec('existing'))
    with pytest.raises(ValueError):
        registry.replace_owned('sample', [spec('sample.good'), spec('existing')])
    assert set(registry._operations) == {'existing'}


def test_incompatible_and_invalid_update_do_not_replace(tmp_path):
    release(tmp_path / 'modules/sample')
    app = manager(tmp_path)
    app.prepare('sample')
    app.enable('sample')
    replacement = tmp_path / 'replacement'
    release(replacement, '2.0', core_requires='>999')
    with pytest.raises(RuntimeError, match='incompatible'):
        app.update('sample', str(replacement))
    assert app.app.registry.dispatch('query', 'sample.status') == {'version':'1.0'}


def test_failed_preparation_restores_release_and_enablement(tmp_path, monkeypatch):
    release(tmp_path / 'modules/sample')
    app = manager(tmp_path)
    app.prepare('sample')
    app.enable('sample')
    replacement = tmp_path / 'replacement'
    release(replacement, '2.0')
    original = app.prepare
    def fail_new(module):
        if app._manifest(module)['version'] == '2.0':
            raise RuntimeError('dependency resolution failed')
        return original(module)
    monkeypatch.setattr(app, 'prepare', fail_new)
    with pytest.raises(RuntimeError, match='dependency resolution'):
        app.update('sample', str(replacement))
    assert app.app.registry.dispatch('query', 'sample.status') == {'version': '1.0'}
    assert manager(tmp_path).discover()[0]['state'] == 'enabled'


def test_python_dependencies_use_uv_only_on_prepare(tmp_path, monkeypatch):
    release(tmp_path / 'modules/sample', dependencies={'python': ['example==1']})
    calls = []
    monkeypatch.setattr('contextopus.core.module_management.subprocess.run', lambda argv, **kw: calls.append(argv))
    app = manager(tmp_path)
    assert calls == []
    app.prepare('sample')
    assert calls[0][:2] == ['uv', 'venv']
    assert calls[1][:3] == ['uv', 'pip', 'install']
    assert calls[1][-1] == 'example==1'


def test_builtin_cannot_be_disabled(tmp_path):
    app = manager(tmp_path)
    app.app.registry.register_module('workspace', state='available')
    with pytest.raises(ValueError, match='Built-in'):
        app.disable('workspace')
    assert 'workspace' in app.app.registry.modules


@pytest.mark.parametrize('changes', [{'dependencies': {'python': 'bad'}}, {'operations': [{'name':'sample.run', 'kind':'query', 'command':[123]}]}])
def test_malformed_manifest_is_isolated(tmp_path, changes):
    release(tmp_path / 'modules/sample', **changes)
    assert manager(tmp_path).discover()[0]['state'] == 'error'


def test_update_keeps_previous_python_environment_and_fingerprint(tmp_path, monkeypatch):
    import os
    import subprocess
    from types import SimpleNamespace
    path = tmp_path / 'modules/sample'
    release(path, dependencies={'python':['original==1']})
    app = manager(tmp_path)
    calls = []
    executable = Path('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    def run(argv, **kwargs):
        calls.append(argv)
        if argv[:2] == ['uv','venv']:
            python = Path(argv[2]) / executable
            python.parent.mkdir(parents=True)
            python.write_text('original environment' if '.releases' not in argv[2] else 'new environment')
        elif argv[:3] == ['uv','pip','install']:
            if argv[-1] == 'broken==2':
                Path(argv[4]).write_text('partially installed failed environment')
                raise subprocess.CalledProcessError(1, argv)
        else:
            return SimpleNamespace(stdout=json.dumps({'interpreter':argv[0]}))
    monkeypatch.setattr('contextopus.core.module_management.subprocess.run', run)
    app.prepare('sample')
    app.enable('sample')
    fingerprint = app.state['sample']['prepared']
    app.prepare('sample')
    assert len([argv for argv in calls if argv[:2] == ['uv','venv']]) == 1
    replacement = tmp_path / 'replacement'
    release(replacement, '2.0', dependencies={'python':['broken==2']})
    with pytest.raises(subprocess.CalledProcessError):
        app.update('sample', str(replacement))
    assert (path / '.venv' / executable).read_text() == 'original environment'
    assert app.state['sample']['prepared'] == fingerprint
    assert app.state['sample']['enabled'] is True
    assert app._code(path) == path
    result = app.app.registry.dispatch('query', 'sample.status')
    assert result['interpreter'] == str(path / '.venv' / executable)
    attempted = [argv[4] for argv in calls if argv[:3] == ['uv','pip','install'] and argv[-1] == 'broken==2']
    assert len(attempted) == 1 and '/.releases/' in attempted[0]


def test_source_reader_does_not_activate_or_prepare(tmp_path, monkeypatch):
    from contextopus.core.module_management import ModuleManifestReader
    from contextopus.core.storage import StorageLayout
    release(tmp_path / 'modules/sample')
    app = manager(tmp_path)
    app.prepare('sample')
    app.enable('sample')
    monkeypatch.setattr(ModuleManager, '_activate', lambda *args: pytest.fail('reader activated module'))
    directories, signature, errors = ModuleManifestReader(StorageLayout(tmp_path)).inspect_sources('filter_algorithms')
    assert directories == [tmp_path / 'modules/sample/package/filter_algorithms']
    assert signature == [('sample', app.state['sample']['prepared'])]
    assert errors == []


def test_invalid_python_is_rejected_before_dependency_install(tmp_path, monkeypatch):
    path = tmp_path / 'modules/sample'
    release(path, dependencies={'python':['example==1']})
    (path / 'package/adapter.py').write_text('def broken(:')
    monkeypatch.setattr('contextopus.core.module_management.subprocess.run', lambda *a, **kw: pytest.fail('installed invalid release'))
    app = manager(tmp_path)
    assert app.discover()[0]['state'] == 'error'
    with pytest.raises(ValueError, match="handler syntax"):
        app.prepare('sample')


def test_same_root_applications_refresh_enable_update_disable(tmp_path):
    from contextopus.startup import Application
    release(tmp_path / 'modules/sample')
    first = Application(tmp_path, context='alpha', discover=False)
    second = Application(tmp_path, context='beta', discover=False)
    try:
        assert 'sample.status' not in second.query('describe')['operations']['query']
        first.execute('core.module_prepare', {'module':'sample'})
        first.execute('core.module_enable', {'module':'sample'})
        assert second.query('sample.status') == {'version':'1.0'}
        replacement = tmp_path / 'replacement'
        release(replacement, '2.0')
        first.execute('core.module_update', {'module':'sample','source':str(replacement)})
        assert second.query('sample.status') == {'version':'2.0'}
        # A lifecycle change issued by a different context must also reach the first.
        second.execute('core.module_disable', {'module':'sample'})
        assert 'sample.status' not in first.query('describe')['operations']['query']
        with pytest.raises(ValueError, match='Unknown operation'):
            first.query('sample.status')
    finally:
        first.close()
        second.close()


def test_changed_provider_prepare_requires_explicit_enable(tmp_path):
    from contextopus.core.filtering import registry_for_layout
    from contextopus.core.storage import StorageLayout
    release(tmp_path / 'modules/sample')
    directory = tmp_path / 'modules/sample/package/filter_algorithms/third_party'
    directory.mkdir(parents=True)
    description = {'id':'third_party', 'version':'1', 'purpose':'test', 'parameters_schema':{'type':'object'}, 'defaults':{}, 'when_to_use':'test', 'how_to_adjust':'none'}
    (directory / 'description.json').write_text(json.dumps(description))
    provider = directory / 'algorithm.py'
    provider.write_text("def select(rows, parameters):\n    return rows, {}\n")
    app = manager(tmp_path)
    app.prepare('sample')
    app.enable('sample')
    app.prepare('sample')
    assert app.state['sample']['enabled'] is True
    assert registry_for_layout(StorageLayout(tmp_path)).catalog('third_party')
    marker = tmp_path / 'executed'
    provider.write_text("from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('executed')\ndef select(rows, parameters):\n    return rows, {}\n")
    app.prepare('sample')
    assert app.state['sample']['enabled'] is False
    assert not app.app.registry.describe()['operations']['query']
    assert not registry_for_layout(StorageLayout(tmp_path)).catalog('third_party')
    assert not marker.exists()
    assert manager(tmp_path).discover()[0]['state'] == 'prepared'
    app.enable('sample')
    assert registry_for_layout(StorageLayout(tmp_path)).catalog('third_party')
    assert marker.read_text() == 'executed'


def test_bundled_command_uses_absolute_executable_for_windows_cwd(tmp_path, monkeypatch):
    from types import SimpleNamespace
    path = tmp_path / 'modules/sample'
    release(path, operations=[{'name':'sample.command','kind':'query','command':['bin/adapter.exe','--status']}])
    app = manager(tmp_path)
    app.prepare('sample')
    app.enable('sample')
    observed = []
    def run(argv, **kwargs):
        observed.append((argv, kwargs['cwd']))
        return SimpleNamespace(stdout='{"ok":true}')
    monkeypatch.setattr('contextopus.core.module_management.subprocess.run', run)
    assert app.app.registry.dispatch('query','sample.command') == {'ok':True}
    assert observed == [([str(path / 'package/bin/adapter.exe'),'--status'], path / 'package')]

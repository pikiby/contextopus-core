"""Trusted built artifacts enter the ordinary lifecycle after safe publication."""
import json
from pathlib import Path
import stat
import zipfile

import pytest

from contextopus.core.module_management import source
from contextopus.startup import Application
from test_module_install import release


def artifact(path):
    manifest = release(path)
    manifest['core_requires'] = '>=1,<2'
    (path / 'module.json').write_text(json.dumps(manifest))
    (path / 'install.sh').write_text('#!/bin/sh\n# wrapper shipped with the built module\n')
    return path


def archive(folder, target, prefix=''):
    with zipfile.ZipFile(target, 'w') as stream:
        for item in sorted(folder.rglob('*')):
            stream.write(item, prefix + item.relative_to(folder).as_posix() + ('/' if item.is_dir() else ''))
    return target


@pytest.mark.parametrize('kind', ['folder', 'zip', 'prefixed_zip'])
def test_real_install_roundtrip_storage_restart_and_existing_data(tmp_path, kind):
    folder = artifact(tmp_path / 'built module with spaces')
    payload = folder if kind == 'folder' else archive(folder, tmp_path / 'module.zip', 'sample/' if kind == 'prefixed_zip' else '')
    root = tmp_path / 'new root'
    with Application(root, discover=False) as app:
        preview = app.query('core.module_source_plan', {'module': 'sample', 'source': str(payload)})
        assert preview['files'] >= 4 and preview['bytes'] > 0
        assert not (root / 'modules/sample').exists()
        result = app.execute('core.module_install', {'module': 'sample', 'source': str(payload), 'source_revision': preview['revision']})
        assert result['state'] == 'enabled'
        assert (root / 'modules/sample/install.sh').is_file()
        app.execute('sample.save', {'id': 'kept', 'title': 'Persistent finding'})
        with pytest.raises(ValueError, match='already exists'):
            app.query('core.module_source_plan', {'module': 'sample', 'source': str(payload)})
        assert app.query('sample.read')['rows'][0]['id'] == 'kept'
    with Application(root, discover=False) as app:
        assert app.query('sample.read')['rows'][0]['title'] == 'Persistent finding'


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'C:/drive', 'package/../../escape', 'package\\escape', 'CON.txt', 'package/file.'])
def test_archive_rejects_unsafe_paths_before_staging(tmp_path, name):
    payload = tmp_path / 'bad.zip'
    with zipfile.ZipFile(payload, 'w') as stream:
        stream.writestr(name, 'unsafe')
    with pytest.raises(ValueError):
        source.inspect_source(payload, 'sample')
    assert not (tmp_path / 'escape').exists()


@pytest.mark.parametrize('kind', ['symlink', 'duplicate', 'case', 'directory_case', 'identity', 'empty_git', 'live_data'])
def test_malformed_payload_cannot_install(tmp_path, kind):
    folder = artifact(tmp_path / 'artifact')
    if kind == 'symlink':
        (folder / 'package/link').symlink_to(folder / 'package/adapter.py')
        payload = folder
    elif kind in {'empty_git', 'live_data'}:
        (folder / ('.git' if kind == 'empty_git' else 'data')).mkdir()
        payload = folder
    elif kind == 'identity':
        value = json.loads((folder / 'module.json').read_text()); value['id'] = 'different'
        (folder / 'module.json').write_text(json.dumps(value)); payload = folder
    else:
        payload = archive(folder, tmp_path / 'bad.zip')
        with zipfile.ZipFile(payload, 'a') as stream:
            if kind == 'duplicate':
                with pytest.warns(UserWarning):
                    stream.writestr('module.json', '{}')
            elif kind == 'case':
                stream.writestr('PACKAGE/extra.txt', 'bad')
            else:
                stream.writestr('PACKAGE/', '')
    with pytest.raises(ValueError):
        source.inspect_source(payload, 'sample')


def test_zip_symlink_and_non_object_manifest_rejected(tmp_path):
    for case in ['symlink', 'manifest']:
        payload = tmp_path / (case + '.zip')
        with zipfile.ZipFile(payload, 'w') as stream:
            stream.writestr('module.json', '[]' if case == 'manifest' else '{}')
            info = zipfile.ZipInfo('package/link'); info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            stream.writestr(info if case == 'symlink' else 'package/file', 'target')
        with pytest.raises(ValueError):
            source.inspect_source(payload, 'sample')


def test_source_revision_mismatch_and_copy_race_keep_target_absent(tmp_path, monkeypatch):
    folder = artifact(tmp_path / 'artifact')
    root = tmp_path / 'root'
    with Application(root, discover=False) as app:
        preview = app.query('core.module_source_plan', {'module': 'sample', 'source': str(folder)})
        (folder / 'install.sh').write_text('changed after preview')
        with pytest.raises(ValueError, match='stale'):
            app.execute('core.module_install', {'module': 'sample', 'source': str(folder), 'source_revision': preview['revision']})
        assert not (root / 'modules/sample').exists()
    plan = source.inspect_source(folder, 'sample')
    original = source._regular
    def changed(path):
        if Path(path).name == 'install.sh':
            Path(path).write_text('changed during copy')
        return original(path)
    monkeypatch.setattr(source, '_regular', changed)
    with pytest.raises(ValueError, match='changed during staging'):
        with source.staged_source(plan, tmp_path / 'stages'):
            pytest.fail('published changed bytes')


def test_concurrent_target_creation_is_never_overwritten(tmp_path, monkeypatch):
    folder = artifact(tmp_path / 'artifact')
    root = tmp_path / 'root'
    original = source.publish_new
    def raced(stage, target):
        target.mkdir()
        (target / 'keep').write_text('another owner')
        return original(stage, target)
    monkeypatch.setattr(source, 'publish_new', raced)
    with Application(root, discover=False) as app:
        preview = app.query('core.module_source_plan', {'module': 'sample', 'source': str(folder)})
        with pytest.raises(FileExistsError):
            app.execute('core.module_install', {'module': 'sample', 'source': str(folder), 'source_revision': preview['revision']})
    assert (root / 'modules/sample/keep').read_text() == 'another owner'
    assert not (root / 'modules/sample/module.json').exists()


def test_incompatible_or_failed_install_retains_truthful_state(tmp_path, monkeypatch):
    folder = artifact(tmp_path / 'artifact')
    root = tmp_path / 'root'
    with Application(root, discover=False) as app:
        value = json.loads((folder / 'module.json').read_text()); value['core_requires'] = '>999'
        (folder / 'module.json').write_text(json.dumps(value))
        with pytest.raises(RuntimeError, match='incompatible'):
            app.query('core.module_source_plan', {'module': 'sample', 'source': str(folder)})
        assert not (root / 'modules/sample').exists()
        value['core_requires'] = '>=1'; (folder / 'module.json').write_text(json.dumps(value))
        preview = app.query('core.module_source_plan', {'module': 'sample', 'source': str(folder)})
        def failed(module):
            raise RuntimeError('fixture dependency failure')
        monkeypatch.setattr(app.module_manager, 'prepare', failed)
        with pytest.raises(RuntimeError, match='dependency failure'):
            app.execute('core.module_install', {'module': 'sample', 'source': str(folder), 'source_revision': preview['revision']})
        assert (root / 'modules/sample/module.json').exists()
        assert not app.module_manager.state['sample']['enabled']
        assert 'sample.read' not in app.registry._operations


def test_cli_source_plan_and_failed_business_result(tmp_path, monkeypatch, capsys):
    from contextopus.interfaces.cli import main as cli
    calls = []
    class Remote:
        def __init__(self, *a, **kw): pass
        def query(self, name, args):
            calls.append(name); return {'revision': 'reviewed'}
        def execute(self, name, args):
            calls.append(name)
            assert args['source_revision'] == 'reviewed'
            return {'id': 'sample', 'state': 'error'}
        def close(self): pass
    from contextopus.integrations import remote
    monkeypatch.setattr(remote, 'RemoteApplication', Remote)
    assert cli.main(['--root', str(tmp_path), 'modules', 'install', 'sample', '--source', str(tmp_path), '--plan']) == 0
    assert calls == ['core.module_source_plan']
    calls.clear()
    assert cli.main(['--root', str(tmp_path), 'modules', 'install', 'sample', '--source', str(tmp_path)]) == 2
    assert calls == ['core.module_source_plan', 'core.module_install']
    assert 'did not return enabled' in capsys.readouterr().err


def test_real_remote_source_install_on_isolated_owner(tmp_path):
    import socket
    import subprocess
    import sys
    import tempfile
    import time
    import urllib.request
    from contextopus.integrations.remote import RemoteApplication
    folder = artifact(tmp_path / 'built')
    root = tmp_path / 'isolated root'
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    with tempfile.TemporaryFile() as log:
        child = subprocess.Popen([sys.executable, '-c',
            'from contextopus.interfaces.mcp.server import run; import sys; run(sys.argv[1],port=int(sys.argv[2]))',
            str(root), str(port)], stdout=log, stderr=log)
        remote = RemoteApplication(root, endpoint=f'http://127.0.0.1:{port}/mcp')
        try:
            deadline = time.monotonic() + 20
            while True:
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=0.5) as response:
                        assert json.load(response)['root'] == str(root)
                    break
                except OSError:
                    if child.poll() is not None or time.monotonic() > deadline:
                        log.seek(0)
                        pytest.fail(log.read().decode(errors='replace'))
                    time.sleep(0.05)
            preview = remote.query('core.module_source_plan', {'module': 'sample', 'source': str(folder)})
            assert remote.execute('core.module_install', {'module': 'sample', 'source': str(folder),
                                  'source_revision': preview['revision']})['state'] == 'enabled'
            remote.execute('sample.save', {'id': 'remote', 'title': 'Verified HTTP operation'})
            assert remote.query('sample.read')['rows'][0]['id'] == 'remote'
        finally:
            remote.close()
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=10)

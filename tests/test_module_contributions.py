"""Optional trusted modules share generic lifecycle without importing domain code."""
import json
import sys

import pytest

from contextopus.startup import Application


FACTORY = '''from .helper import title
from contextopus.core.settings import DEFAULTS, Settings

class ModuleSettings(Settings):
    defaults = {**DEFAULTS, 'feature': True}

def register(host):
    host._operation('sample.status', 'query', lambda: {'title': title})
    host.alias('sample_status', 'sample.status')
    host.procedure('sample-help', lambda: {'content': title})
    host.settings_provider(ModuleSettings)
    host.index.register_source('sample', object())
    host.hook('setup', lambda: {'title': title})
    def close():
        target = host.layout.root / 'closed.log'
        with target.open('a') as stream:
            stream.write(title + '\\n')
    host.hook('close', close)
'''


def release(path, title='one', factory=FACTORY):
    package = path / 'package/sample'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text(factory)
    (package / 'helper.py').write_text('title = ' + repr(title) + '\n')
    manifest = {'id': 'sample', 'version': '1.0',
                'contribution': {'factory': 'sample/__init__.py:register'}}
    (path / 'module.json').write_text(json.dumps(manifest))
    return manifest


def test_core_alone_does_not_import_or_register_domain_modules(tmp_path, monkeypatch):
    class NoDomainImports:
        def find_spec(self, fullname, *args):
            if 'workspace' in fullname:
                raise AssertionError('Core attempted a Workspace import: ' + fullname)
    monkeypatch.setattr(sys, 'meta_path', [NoDomainImports(), *sys.meta_path])
    with Application(tmp_path, discover=False) as app:
        assert not app.registry.modules
        assert not any(name.startswith('workspace.') for name in app.registry._operations)
        assert app.query('core.modules') == []
        assert 'knowledge_approval_required' not in app.query('core.settings')['values']
        assert app.query('core.doctor')['model_loaded'] is False
        assert app.query('procedure', {'name': 'default'})['name'] == 'modules'
        app.execute('core.init')
        assert not (tmp_path / 'modules/workspace').exists()


def test_contribution_discovery_is_inert_and_disable_removes_every_owner(tmp_path):
    release(tmp_path / 'modules/sample')
    with Application(tmp_path, discover=False) as app:
        assert app.query('core.modules')[0]['state'] == 'discovered'
        assert not (tmp_path / 'closed.log').exists()
        assert app.execute('core.module_install', {'module': 'sample'})['state'] == 'enabled'
        assert app.query('sample_status')['title'] == 'one'
        assert app.query('procedure', {'name': 'sample-help'})['content'] == 'one'
        assert app.query('core.settings', {'module': 'sample'})['values']['feature'] is True
        assert app.module_manager.run_hooks('setup') == {'sample': [{'title': 'one'}]}
        assert 'sample' in app.index.source_adapters
        # Imported bytecode is never part of the release content fingerprint.
        assert app.query('sample.status')['title'] == 'one'
        app.execute('core.module_disable', {'module': 'sample'})
        assert 'sample' not in app.index.source_adapters
        assert not app.module_manager.aliases
        assert not app.module_manager.procedures
        assert not app.services._settings.providers
        assert not app.module_manager.contributions
        assert app.query('core.settings', {'module': 'sample'})['values'].get('feature') is None
        with pytest.raises(ValueError, match='Unknown operation'):
            app.query('sample_status')
    assert (tmp_path / 'closed.log').read_text().splitlines() == ['one']
    with Application(tmp_path, discover=False) as restored:
        assert 'sample' not in restored.registry.modules
        restored.execute('core.module_enable', {'module': 'sample'})
        assert restored.query('sample_status')['title'] == 'one'


def test_other_application_observes_enable_disable_update_and_restart(tmp_path):
    release(tmp_path / 'modules/sample')
    with Application(tmp_path, discover=False) as first, Application(tmp_path, discover=False) as second:
        first.execute('core.module_install', {'module': 'sample'})
        assert second.query('sample_status')['title'] == 'one'
        replacement = tmp_path / 'replacement'
        release(replacement, 'two')
        first.execute('core.module_update', {'module': 'sample', 'source': str(replacement)})
        assert second.query('sample_status')['title'] == 'two'
        second.execute('core.module_disable', {'module': 'sample'})
        with pytest.raises(ValueError, match='Unknown operation'):
            first.query('sample_status')
        second.execute('core.module_enable', {'module': 'sample'})
    with Application(tmp_path, discover=False) as third:
        assert third.query('sample_status')['title'] == 'two'


def test_discovery_reports_actual_native_operations_across_lifecycle(tmp_path):
    release(tmp_path / 'modules/sample')
    with Application(tmp_path, discover=False) as first, Application(tmp_path, discover=False) as second:
        assert first.query('core.modules')[0]['operations'] == []
        first.execute('core.module_install', {'module': 'sample'})
        assert first.query('core.modules')[0]['operations'] == ['sample.status']
        assert second.query('core.modules')[0]['operations'] == ['sample.status']
        replacement = tmp_path / 'replacement'
        release(replacement, 'two', FACTORY.replace('sample.status', 'sample.inspect'))
        first.execute('core.module_update', {'module': 'sample', 'source': str(replacement)})
        assert second.query('core.modules')[0]['operations'] == ['sample.inspect']
        first.execute('core.module_disable', {'module': 'sample'})
        assert second.query('core.modules')[0]['operations'] == []
        first.execute('core.module_enable', {'module': 'sample'})
    with Application(tmp_path, discover=False) as restarted:
        assert restarted.query('core.modules')[0]['operations'] == ['sample.inspect']


def test_failed_contribution_update_restores_previous_complete_contribution(tmp_path):
    release(tmp_path / 'modules/sample')
    with Application(tmp_path, discover=False) as app:
        app.execute('core.module_install', {'module': 'sample'})
        replacement = tmp_path / 'replacement'
        release(replacement, 'broken', FACTORY + '\nraise RuntimeError("rejected release")\n')
        with pytest.raises(RuntimeError, match='rejected release'):
            app.execute('core.module_update', {'module': 'sample', 'source': str(replacement)})
        assert app.query('sample_status')['title'] == 'one'
        assert app.query('procedure', {'name': 'sample-help'})['content'] == 'one'
        assert 'sample' in app.index.source_adapters


def test_native_dependencies_are_checked_in_core_interpreter_without_venv(tmp_path):
    module = tmp_path / 'modules/sample'
    manifest = release(module)
    manifest['contribution']['requires'] = ['contextopus-core>=99999']
    (module / 'module.json').write_text(json.dumps(manifest))
    with Application(tmp_path, discover=False) as app:
        assert 'Core interpreter' in app.query('core.modules')[0]['error']
        with pytest.raises(ValueError, match='Core interpreter'):
            app.execute('core.module_install', {'module': 'sample'})
    assert not (module / '.venv').exists()


INSTALL_FACTORY = FACTORY + '''
_original_register = register

def register(host):
    _original_register(host)
    marker = host.layout.root / 'installed.txt'
    host.hook('install_prepare', lambda: {'revision': 'v1'})
    def apply(revision):
        assert revision == 'v1'
        marker.write_text(revision)
    host.hook('install_apply', apply)
    def ready():
        if not marker.is_file():
            raise ValueError('Explicit installation required')
    host.hook('ready', ready)
'''


def test_install_hooks_precede_registration_and_restart_never_migrates(tmp_path):
    release(tmp_path / 'modules/sample', factory=INSTALL_FACTORY)
    marker = tmp_path / 'installed.txt'
    with Application(tmp_path, discover=False) as app:
        app.execute('core.module_prepare', {'module': 'sample'})
        assert not marker.exists()
        with pytest.raises(ValueError, match='Explicit installation'):
            app.execute('core.module_enable', {'module': 'sample'})
        assert 'sample' not in app.index.source_adapters
        assert app.execute('core.module_install', {'module': 'sample'})['state'] == 'enabled'
        assert marker.read_text() == 'v1'
        assert app.query('sample_status')['title'] == 'one'
    marker.unlink()
    with Application(tmp_path, discover=False) as app:
        assert not marker.exists()
        assert 'sample' not in app.index.source_adapters
        assert app.query('core.modules')[0]['state'] == 'error'
        with pytest.raises(ValueError, match='Unknown operation'):
            app.query('sample_status')


def test_process_resources_close_owned_contributions(tmp_path):
    from contextopus.core.resources import ProcessResources
    release(tmp_path / 'modules/sample')
    resources = ProcessResources()
    app = Application(tmp_path, resources=resources, discover=False)
    app.execute('core.module_install', {'module': 'sample'})
    resources.close()
    assert (tmp_path / 'closed.log').read_text().splitlines() == ['one']
    assert not app.module_manager.aliases


def test_failed_close_keeps_disable_durable_and_removes_all_registrations(tmp_path):
    factory = FACTORY.replace("stream.write(title + '\\n')", "stream.write(title + '\\n')\n        raise RuntimeError('close failed')")
    release(tmp_path / 'modules/sample', factory=factory)
    app = Application(tmp_path, discover=False)
    app.execute('core.module_install', {'module': 'sample'})
    with pytest.raises(ExceptionGroup, match='cleanup failed'):
        app.execute('core.module_disable', {'module': 'sample'})
    assert not app.module_manager.aliases
    assert not app.module_manager.procedures
    assert not app.index.source_adapters
    assert not app.services._settings.providers
    assert 'sample.status' not in app.registry._operations
    assert json.loads((tmp_path / 'core/configuration/modules.json').read_text())['sample']['enabled'] is False
    app.close()


def test_failed_install_apply_never_reuses_new_candidate_for_old_release(tmp_path):
    release(tmp_path / 'modules/sample')
    with Application(tmp_path, discover=False) as app:
        app.execute('core.module_install', {'module': 'sample'})
        replacement = tmp_path / 'replacement'
        factory = FACTORY + '''
_original_register = register

def register(host):
    _original_register(host)
    host.hook('install_prepare', lambda: {'revision': 'next'})
    def fail(revision):
        raise RuntimeError('reject migration')
    host.hook('install_apply', fail)
'''
        release(replacement, 'two', factory)
        with pytest.raises(RuntimeError, match='reject migration'):
            app.execute('core.module_update', {'module': 'sample', 'source': str(replacement)})
        assert app.query('sample.status')['title'] == 'one'
        assert app.query('procedure', {'name': 'sample-help'})['content'] == 'one'
        assert app.module_manager.contributions['sample'].fingerprint == app.module_manager._digest('sample')


def test_application_close_failure_still_releases_owned_process_resources(tmp_path):
    factory = FACTORY.replace("stream.write(title + '\\n')", "stream.write(title + '\\n')\n        raise RuntimeError('close failed')")
    release(tmp_path / 'modules/sample', factory=factory)
    app = Application(tmp_path, discover=False)
    app.execute('core.module_install', {'module': 'sample'})
    with pytest.raises(ExceptionGroup, match='Application failed to close'):
        app.close()
    assert app.resources._closed is True
    assert not app.module_manager.contributions


def test_disable_drains_native_calls_across_applications_and_allows_nested_core_call(tmp_path):
    import threading
    factory = FACTORY + '''
_original_register = register

def register(host):
    import threading
    _original_register(host)
    host.started = threading.Event()
    host.release = threading.Event()
    def wait():
        host.started.set()
        if not host.release.wait(5):
            raise TimeoutError('test did not release request')
        # A lifecycle action is already draining. This Core call must keep the
        # admitted request snapshot instead of waiting on the lifecycle lock.
        return {'exists': host.query('core.doctor')['exists']}
    host._operation('sample.wait', 'query', wait)
'''
    release(tmp_path / 'modules/sample', factory=factory)
    with Application(tmp_path, discover=False) as first, Application(tmp_path, discover=False) as second:
        first.execute('core.module_install', {'module': 'sample'})
        second.query('sample.status')
        other = second.module_manager.contributions['sample']
        results, failures = [], []
        def request():
            try:
                results.append(second.query('sample.wait'))
            except Exception as exc:
                failures.append(exc)
        def disable():
            try:
                first.execute('core.module_disable', {'module': 'sample'})
            except Exception as exc:
                failures.append(exc)
        reader = threading.Thread(target=request)
        reader.start()
        assert other.started.wait(2)
        writer = threading.Thread(target=disable)
        writer.start()
        writer.join(.1)
        assert writer.is_alive()
        assert not (tmp_path / 'closed.log').exists()
        other.release.set()
        reader.join(3)
        writer.join(3)
        assert not reader.is_alive() and not writer.is_alive()
        assert not failures
        assert results == [{'exists': True}]
        with pytest.raises(ValueError, match='Unknown operation'):
            second.query('sample.wait')


def test_native_quiescence_blocks_new_calls_until_relocation_boundary_finishes(tmp_path):
    import threading
    release(tmp_path / 'modules/sample')
    with Application(tmp_path, discover=False) as app:
        app.execute('core.module_install', {'module': 'sample'})
        # Bypass registry refresh just as a request that resolved its operation
        # before the relocation lifecycle lock was taken.
        spec = app.registry._operations['sample.status']
        began = threading.Event()
        completed = threading.Event()
        result = []
        def call():
            began.set()
            result.append(spec.handler(app.context))
            completed.set()
        with app.module_manager.quiesce_contributions():
            worker = threading.Thread(target=call)
            worker.start()
            assert began.wait(1)
            assert not completed.wait(.1)
            # The lifecycle thread can run native shutdown hooks within its
            # quiescent boundary without admitting unrelated outer requests.
            assert app.module_manager.run_hooks('setup') == {'sample': [{'title': 'one'}]}
        worker.join(2)
        assert completed.is_set()
        assert result == [{'title': 'one'}]

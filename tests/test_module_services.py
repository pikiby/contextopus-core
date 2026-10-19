"""Real isolated persistent children; no live roots, model or network."""
import json
import os
from pathlib import Path
import threading
import time

import pytest

from contextopus.core.resources import ProcessResources
from contextopus.startup import Application

ADAPTER = '''import json, os, threading, time
from pathlib import Path
class Service:
    def __init__(self, core):
        self.core = core
        self.data = Path(os.environ['CONTEXTOPUS_MODULE_DATA'])
        self.stop = threading.Event()
        self.thread = None
    def start(self):
        if (self.data / 'fail').exists():
            raise RuntimeError('failed readiness')
        def work():
            pending = self.data / 'pending'
            while not self.stop.wait(.02):
                if pending.exists() and not self.stop.wait(.3):
                    (self.data / 'done').write_text(pending.read_text())
                    pending.unlink()
        self.thread = threading.Thread(target=work)
        self.thread.start()
    def dispatch(self, operation, arguments, context):
        name = operation.split('.')[1]
        if name == 'status':
            return {'pid': os.getpid(), 'context': context, 'version': VERSION}
        if name == 'enqueue':
            (self.data / 'pending').write_text(arguments['value'])
            return {'queued': True}
        if name == 'forbidden':
            return self.core.storage.execute('INSERT INTO "{{module}}::items" VALUES (1)')
        if name == 'forbidden_rag':
            return self.core.rag.delete_document(key={'collection': 'items', 'id': 'one'})
        if name == 'transaction':
            transaction = self.core.storage.begin(.8)['transaction_id']
            self.core.storage.execute('INSERT INTO "{{module}}::items" VALUES (42)', transaction_id=transaction)
            if arguments.get('crash'):
                os._exit(7)
            return {'opened': True}
        if name == 'background_transaction':
            def work():
                transaction = self.core.storage.begin(.4)['transaction_id']
                self.core.storage.execute('INSERT INTO "{{module}}::items" VALUES (43)', transaction_id=transaction)
                (self.data / 'transaction').write_text('opened')
            threading.Thread(target=work).start()
            return {}
        if name == 'sleep':
            (self.data / 'sleeping').write_text('yes')
            time.sleep(.4)
            return {}
        if name == 'read':
            return self.core.storage.query('SELECT * FROM "{{module}}::items"')
        raise ValueError(name)
    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join()
def create_service(core):
    return Service(core)
'''


def release(path, version=1, *, code=None, ready_timeout=3, stop_timeout=.3):
    package = path / 'package'
    package.mkdir(parents=True)
    (package / 'adapter.py').write_text('VERSION=' + repr(version) + '\n' + (code or ADAPTER))
    (package / 'migrations').mkdir()
    (package / 'migrations/001-schema.sql').write_text('CREATE TABLE "{{module}}::items" (value INTEGER);')
    manifest = {'id': 'sample', 'version': str(version), 'rag': True,
        'service': {'factory': 'adapter.py:create_service', 'ready_timeout': ready_timeout, 'stop_timeout': stop_timeout},
        'storage': {'engine': 'sqlite', 'schema_version': 1, 'migrations': 'migrations', 'compatible_versions': {'min': 1, 'max': 1}},
        'operations': [{'name': 'sample.' + name, 'kind': kind, 'service': True}
            for name, kind in [('status','query'), ('enqueue','execute'), ('forbidden','query'), ('forbidden_rag','query'),
                              ('transaction','execute'), ('background_transaction','execute'), ('sleep','query'), ('read','query')]]}
    (path / 'module.json').write_text(json.dumps(manifest))
    return manifest


def wait_for(check, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(.02)
    assert check()


@pytest.fixture
def running(tmp_path):
    release(tmp_path / 'modules/sample')
    app = Application(tmp_path, context='first', discover=False)
    app.resources.start_services()
    app.execute('core.module_install', {'module': 'sample'})
    try:
        yield app
    finally:
        app.close()


def test_discovery_defers_children_and_started_owner_reuses_across_contexts(tmp_path, monkeypatch):
    release(tmp_path / 'modules/sample')
    resources = ProcessResources()
    first = Application(tmp_path, 'first', resources=resources, discover=False)
    first.execute('core.module_install', {'module': 'sample'})
    second = Application(tmp_path, 'second', resources=resources, discover=False)
    try:
        assert first.query('core.modules')[0]['service'] == {'state': 'stopped', 'pid': None}
        resources.start_services()
        initial = first.query('sample.status')
        assert initial['context'] == 'first'
        assert second.query('sample.status') == {**initial, 'context': 'second'}
        resources.start_services()
        assert first.query('sample.status')['pid'] == initial['pid']
        monkeypatch.setattr('contextopus.core.module_management.services.subprocess.Popen', lambda *a, **kw: pytest.fail('inspection spawned a child'))
        assert first.query('core.modules')[0]['service']['state'] == 'running'
        assert second.query('describe', {'operation': 'sample.status'})['kind'] == 'query'
    finally:
        resources.close()


def test_work_continues_after_request_and_restart_resumes_queue(running):
    app = running
    data = app.layout.root / 'modules/sample/data'
    assert app.execute('sample.enqueue', {'value': 'continued'}) == {'queued': True}
    wait_for(lambda: (data / 'done').exists())
    assert (data / 'done').read_text() == 'continued'
    app.execute('sample.enqueue', {'value': 'resumed'})
    app.close()
    assert (data / 'pending').exists()
    with Application(app.layout.root, discover=False) as restarted:
        assert restarted.query('core.modules')[0]['service']['state'] == 'stopped'
        restarted.resources.start_services()
        wait_for(lambda: (data / 'done').read_text() == 'resumed')
        assert restarted.query('sample.status')['version'] == 1


def test_query_permissions_and_request_transactions(running):
    for operation in ('sample.forbidden', 'sample.forbidden_rag'):
        with pytest.raises(RuntimeError, match='Query operations cannot write'):
            running.query(operation)
    assert running.execute('sample.transaction') == {'opened': True}
    assert running.query('sample.read')['rows'] == []
    running.execute('sample.background_transaction')
    data = running.layout.root / 'modules/sample/data'
    wait_for(lambda: (data / 'transaction').exists())
    # The child stays silent after opening a transaction. Parent idle expiry
    # releases its write gate and rolls back without another child RPC.
    time.sleep(.6)
    running.module_storage.execute('sample', 'INSERT INTO "{{module}}::items" VALUES (99)')
    assert running.query('sample.read')['rows'] == [{'value': 99}]


def test_disable_stops_child_preserves_config_and_enable_restarts(running):
    root = running.layout.root / 'modules/sample'
    pid = running.query('sample.status')['pid']
    (root / 'config/options').write_text('keep')
    running.execute('core.module_disable', {'module': 'sample'})
    assert running.query('core.modules')[0]['service']['state'] == 'stopped'
    assert (root / 'config/options').read_text() == 'keep'
    running.execute('core.module_enable', {'module': 'sample'})
    assert running.query('sample.status')['pid'] != pid


def test_update_ready_failure_rolls_back_and_restarts_previous_service(running, tmp_path):
    source = tmp_path / 'replacement'
    release(source, 2)
    running.execute('core.module_update', {'module': 'sample', 'source': str(source)})
    assert running.query('sample.status')['version'] == 2
    bad = tmp_path / 'broken'
    release(bad, 3, code=ADAPTER.replace('self.stop = threading.Event()', "raise RuntimeError('broken factory')"))
    with pytest.raises(RuntimeError, match='broken factory'):
        running.execute('core.module_update', {'module': 'sample', 'source': str(bad)})
    assert running.query('sample.status')['version'] == 2
    assert running.query('core.modules')[0]['service']['state'] == 'running'


def test_crash_rolls_back_and_requires_explicit_enable(running):
    service = running.module_manager.runtime.services['sample']
    with pytest.raises(RuntimeError, match='exited'):
        running.execute('sample.transaction', {'crash': True})
    wait_for(lambda: service._finished.is_set())
    assert running.module_storage.query('sample', 'SELECT * FROM "{{module}}::items"')['rows'] == []
    assert running.query('core.modules')[0]['state'] == 'error'
    running.resources.start_services()
    assert running.module_manager.runtime.services['sample'] is service
    running.execute('core.module_enable', {'module': 'sample'})
    assert running.query('sample.status')['pid'] != service.process.pid


def test_service_dispatch_does_not_hold_root_guard(running):
    root = running.layout.root
    failures = []
    def dispatch():
        try:
            running.query('sample.sleep')
        except Exception as exc:
            failures.append(exc)
    worker = threading.Thread(target=dispatch)
    worker.start()
    wait_for(lambda: (root / 'modules/sample/data/sleeping').exists())
    started = time.monotonic()
    with running.layout.guard():
        assert time.monotonic() - started < .2
    running.query('core.status')
    assert time.monotonic() - started < .3
    worker.join(2)
    assert not worker.is_alive() and not failures


def test_changed_source_stops_running_code_without_another_request(running):
    service = running.module_manager.runtime.services['sample']
    source = running.layout.root / 'modules/sample/package/adapter.py'
    source.write_text(source.read_text() + '\n# changed fingerprint\n')
    wait_for(lambda: service._finished.is_set())
    assert service.status()['state'] == 'error'
    assert 'changed' in service.error
    assert running.query('core.modules')[0]['state'] == 'error'


def test_new_root_discovered_after_owner_start_activates(tmp_path):
    from contextopus.interfaces.mcp.server import ServerOwner
    root, later = tmp_path / 'initial', tmp_path / 'later'
    release(later / 'modules/sample')
    with Application(later, discover=False) as offline:
        offline.execute('core.module_install', {'module': 'sample'})
    owner = ServerOwner(root)
    try:
        owner.application()
        owner.resources.start_services()
        app = owner.application(later)
        assert app.query('sample.status')['version'] == 1
    finally:
        owner.close()


def test_failed_ready_enable_disables_and_does_not_retry(tmp_path):
    release(tmp_path / 'modules/sample', code=ADAPTER.replace("self.stop = threading.Event()", "raise RuntimeError('not ready')"))
    with Application(tmp_path, discover=False) as app:
        app.execute('core.module_install', {'module': 'sample'})
        # Owner activation records the failure and does not start crash loops.
        app.resources.start_services()
        service = app.module_manager.runtime.services['sample']
        assert app.query('core.modules')[0]['state'] == 'error'
        app.resources.start_services()
        assert app.module_manager.runtime.services['sample'] is service
        with pytest.raises(RuntimeError, match='not ready'):
            app.execute('core.module_enable', {'module': 'sample'})
        assert not app.module_manager.state['sample']['enabled']
        assert 'sample.status' not in app.query('describe')['operations']['query']


def test_line_json_service_command_and_stale_request_ids(tmp_path):
    import sys
    package = tmp_path / 'modules/sample/package'
    package.mkdir(parents=True)
    (package / 'command.py').write_text('''import json, sys
request = json.loads(sys.stdin.readline())
assert request['protocol'] == 'contextopus-service-v1'
print(json.dumps({'type':'ready'}), flush=True)
while True:
    request = json.loads(sys.stdin.readline())
    if request['type'] == 'stop':
        break
    print(json.dumps({'type':'call','id':'rpc','method':'storage.query','arguments':{'sql':'SELECT 1'},'request_id':'stale'}), flush=True)
    response = json.loads(sys.stdin.readline())
    print(json.dumps({'type':'response','id':request['id'],'result':{'denied':response['error']['type']}}), flush=True)
''')
    manifest = {'id': 'sample', 'version': '1',
        'service': {'command': [sys.executable, 'command.py'], 'protocol': 'contextopus-service-v1'},
        'operations': [{'name': 'sample.status', 'kind': 'query', 'service': True}]}
    (package.parent / 'module.json').write_text(json.dumps(manifest))
    with Application(tmp_path, discover=False) as app:
        app.resources.start_services()
        app.execute('core.module_install', {'module': 'sample'})
        assert app.query('sample.status') == {'denied': 'PermissionError'}


@pytest.mark.skipif(os.name == 'nt', reason='POSIX /proc descendant state probe')
def test_disable_kills_descendants_even_if_service_leader_exits(tmp_path):
    code = ADAPTER.replace('self.thread.start()', '''self.thread.start()
        import subprocess, sys
        child = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(90)'])
        (self.data / 'descendant').write_text(str(child.pid))''')
    release(tmp_path / 'modules/sample', code=code)
    with Application(tmp_path, discover=False) as app:
        app.resources.start_services()
        app.execute('core.module_install', {'module': 'sample'})
        data = tmp_path / 'modules/sample/data'
        descendant = int((data / 'descendant').read_text())
        app.execute('core.module_disable', {'module': 'sample'})
        def gone():
            status = Path('/proc') / str(descendant) / 'stat'
            return not status.exists() or status.read_text().split()[2] == 'Z'
        wait_for(gone)


def test_model_lease_is_shared_across_requests_and_shutdown_does_not_wait_for_inference(tmp_path):
    from contextopus.core.embeddings import default_config
    created, started, finish = [], threading.Event(), threading.Event()
    class Provider:
        closed = False
        block = False
        def embed(self, texts, purpose='document'):
            if self.block:
                started.set()
                assert finish.wait(5)
            return [[1., .5] for _ in texts]
        def close(self):
            self.closed = True
    def factory(config):
        provider = Provider()
        created.append(provider)
        return provider
    code = ADAPTER.replace("if name == 'status':", """if name == 'embed':
            profile = self.core.embeddings.profile()
            return {'vector': self.core.embeddings.embed_query(text='hello', profile=profile)}
        if name == 'status':""")
    manifest = release(tmp_path / 'modules/sample', code=code)
    manifest['operations'].append({'name': 'sample.embed', 'kind': 'query', 'service': True})
    (tmp_path / 'modules/sample/module.json').write_text(json.dumps(manifest))
    resources = ProcessResources(provider_factory=factory)
    app = Application(tmp_path, resources=resources, discover=False)
    config = default_config()
    config['profile']['dimensions'] = 2
    app.index.embeddings = config
    with app.layout.guard():
        app.index._generic_table(create=True)
    app.execute('core.module_install', {'module': 'sample'})
    assert created == []
    resources.start_services()
    assert created == []
    errors = []
    worker = None
    try:
        assert app.query('sample.embed') == {'vector': [1., .5]}
        assert app.query('sample.embed') == {'vector': [1., .5]}
        assert len(created) == 1 and not created[0].closed
        created[0].block = True
        def embed():
            try:
                app.query('sample.embed')
            except Exception as exc:
                errors.append(exc)
        worker = threading.Thread(target=embed)
        worker.start()
        assert started.wait(2)
        before = time.monotonic()
        with app.layout.guard():
            assert time.monotonic() - before < .2
        app.execute('core.module_disable', {'module': 'sample'})
        assert time.monotonic() - before < 1.5
        assert not created[0].closed
        finish.set()
        wait_for(lambda: created[0].closed)
        worker.join(2)
        assert not worker.is_alive() and errors
    finally:
        finish.set()
        resources.close()
        if worker:
            worker.join(2)


def test_background_prints_are_logs_and_start_timeout_leaves_module_disabled(tmp_path):
    code = ADAPTER.replace("while not self.stop.wait(.02):", "while not self.stop.wait(.02):\n                print('background log', flush=True)")
    release(tmp_path / 'modules/sample', code=code)
    with Application(tmp_path, discover=False) as app:
        app.resources.start_services()
        app.execute('core.module_install', {'module': 'sample'})
        time.sleep(.08)
        assert app.query('sample.status')['version'] == 1
    stalled = tmp_path / 'stalled'
    code = ADAPTER.replace("if (self.data / 'fail').exists():", "time.sleep(30)\n        if (self.data / 'fail').exists():")
    release(stalled / 'modules/sample', code=code, ready_timeout=.15, stop_timeout=.1)
    with Application(stalled, discover=False) as app:
        app.resources.start_services()
        before = time.monotonic()
        with pytest.raises(TimeoutError, match='readiness'):
            app.execute('core.module_install', {'module': 'sample'})
        assert time.monotonic() - before < 2
        assert app.module_manager.state['sample']['enabled'] is False
        assert app.query('core.modules')[0]['state'] == 'error'


def test_oversized_rpc_result_returns_error_without_killing_service(tmp_path, monkeypatch):
    from contextopus.core.module_management.core_access import ModuleCoreAccess
    from contextopus.core.module_management.protocol import MAX_MESSAGE
    original = ModuleCoreAccess.call
    def call(self, method, arguments, deadline=None):
        if method == 'test.large':
            return 'x' * MAX_MESSAGE
        return original(self, method, arguments, deadline)
    monkeypatch.setattr(ModuleCoreAccess, 'call', call)
    code = ADAPTER.replace("if name == 'status':", """if name == 'large':
            return self.core.call('test.large')
        if name == 'status':""")
    manifest = release(tmp_path / 'modules/sample', code=code)
    manifest['operations'].append({'name': 'sample.large', 'kind': 'query', 'service': True})
    (tmp_path / 'modules/sample/module.json').write_text(json.dumps(manifest))
    with Application(tmp_path, discover=False) as app:
        app.resources.start_services()
        app.execute('core.module_install', {'module': 'sample'})
        pid = app.query('sample.status')['pid']
        with pytest.raises(RuntimeError, match='exceeds 1 MiB'):
            app.query('sample.large')
        assert app.query('sample.status')['pid'] == pid


def test_frozen_prepare_and_update_have_no_module_or_child_side_effects(running, tmp_path, monkeypatch):
    root = running.layout.root
    source = tmp_path / 'replacement'
    release(source, 2)
    service = running.module_manager.runtime.services['sample']
    manifest = root / 'modules/sample/module.json'
    state = running.module_manager.state_path
    original = (manifest.read_bytes(), state.read_bytes(), service.process.pid)
    freeze = root / '.contextopus-freeze.json'
    freeze.write_text(json.dumps({'revision': 'test'}))
    monkeypatch.setattr('contextopus.core.module_management.subprocess.run', lambda *a, **kw: pytest.fail('frozen dependency preparation'))
    try:
        with pytest.raises(RuntimeError, match='frozen'):
            running.module_manager.prepare('sample')
        with pytest.raises(RuntimeError, match='frozen'):
            running.module_manager.update('sample', str(source))
        assert (manifest.read_bytes(), state.read_bytes(), service.process.pid) == original
        assert service.process.poll() is None
        assert not (root / 'modules/sample/.releases').exists()
        assert not list((root / 'modules').glob('.module-stage-*'))
    finally:
        freeze.unlink()


def test_relocation_waits_for_module_lifecycle_without_taking_root_guard(tmp_path):
    from contextopus.core.module_management.lifecycle import module_lifecycle
    from contextopus.core import relocation
    root, target = tmp_path / 'root', tmp_path / 'target'
    (root / 'data').mkdir(parents=True)
    (root / 'data/item').write_text('preserved')
    app = Application(root, discover=False)
    plan = relocation.plan(root, target)
    started, finished, failures = threading.Event(), threading.Event(), []
    def relocate():
        started.set()
        try:
            relocation.apply(plan)
        except Exception as exc:
            failures.append(exc)
        finally:
            finished.set()
    try:
        with module_lifecycle(root):
            after_lock = relocation.plan(root, target)
            assert after_lock['revision'] == plan['revision']
            assert 'runtime/module-lifecycle.lock' not in {item['path'] for item in after_lock['files']}
            # Nested acquisition must reuse the same file lock.
            with module_lifecycle(root):
                thread = threading.Thread(target=relocate)
                thread.start()
                assert started.wait(1)
                assert not finished.wait(.1)
                assert not (root / '.contextopus-freeze.json').exists()
                with app.layout.guard():
                    assert not finished.is_set()
        thread.join(3)
        assert not thread.is_alive() and not failures
        assert (target / 'data/item').read_text() == 'preserved'
        assert not (target / 'runtime/module-lifecycle.lock').exists()
    finally:
        app.close()


def test_lifecycle_gate_serializes_an_independent_process(tmp_path):
    import subprocess
    import sys
    from contextopus.core.module_management.lifecycle import module_lifecycle
    marker = tmp_path / 'acquired'
    code = "from pathlib import Path\nfrom contextopus.core.module_management.lifecycle import module_lifecycle\nprint('ready', flush=True)\nwith module_lifecycle(" + repr(str(tmp_path)) + "):\n Path(" + repr(str(marker)) + ").write_text('yes')\n"
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    process = None
    try:
        with module_lifecycle(tmp_path):
            process = subprocess.Popen([sys.executable, '-c', code], stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, env=environment)
            assert process.stdout.readline().strip() == 'ready'
            time.sleep(.1)
            assert not marker.exists()
        output, error = process.communicate(timeout=4)
        assert process.returncode == 0, error
        assert marker.read_text() == 'yes'
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=2)

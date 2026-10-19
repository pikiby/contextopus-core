"""Verify an extracted starter bundle against its installed Core wheel.

Only temporary data roots, projects and loopback ports are used. No installer,
OS service, user configuration, transcript history or real model is invoked.
Pass --test-embeddings for an explicitly labelled deterministic model fixture.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
from importlib import metadata
import inspect
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
import zipfile

sys.dont_write_bytecode = True


SERVER = r'''
import json
import math
from pathlib import Path
import sys
from contextopus.interfaces.mcp import server
if sys.argv[3] == 'fixture':
    from contextopus.core import model_setup
    from contextopus.core.resources import ProcessResources
    state = {'providers': 0, 'embed_calls': 0}
    evidence = Path(sys.argv[4])
    def publish():
        temporary = evidence.with_suffix('.tmp')
        temporary.write_text(json.dumps(state))
        temporary.replace(evidence)
    class Tokenizer:
        model_max_length = 32768
        def __call__(self, text, add_special_tokens=False, **kwargs):
            if isinstance(text, list):
                return {'input_ids': [list(range(len(value))) for value in text]}
            return {'input_ids': list(range(len(text))) + ([999] if add_special_tokens else []),
                    'offset_mapping': [(i, i + 1) for i in range(len(text))]}
    class Provider:
        def __init__(self, config):
            self.config = config
        def tokenizer(self):
            return Tokenizer()
        def embed(self, texts, purpose='document'):
            state['embed_calls'] += 1
            publish()
            vectors = []
            for text in texts:
                angle = sum(ord(char) for char in text) % 360 * math.pi / 180
                vectors.append([math.cos(angle), math.sin(angle)] +
                               [0.0] * (self.config['profile']['dimensions'] - 2))
            return vectors
        def close(self):
            pass
    def factory(config):
        state['providers'] += 1
        publish()
        return Provider(config)
    hardware = {'cpu': {'available': True}, 'cuda': {'available': False, 'count': 0, 'devices': []},
                'mps': {'available': False}, 'torch_available': False, 'diagnostics': []}
    model_setup.detect_hardware = lambda probe=None: hardware
    server.ProcessResources = lambda: ProcessResources(factory)
    publish()
server.run(sys.argv[1], host='127.0.0.1', port=int(sys.argv[2]))
'''


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def load_bundle(root):
    spec = importlib.util.spec_from_file_location('starter_bundle_under_test', root / 'bundle.py')
    require(spec is not None and spec.loader is not None, 'Bundle validator is unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_bundle(root)


def installer_support(root):
    spec = importlib.util.spec_from_file_location('starter_install_support_under_test',
                                                 root / 'install_support.py')
    require(spec is not None and spec.loader is not None, 'Installer helpers are unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def installed_runtime(bundle, manifest):
    """Version alone cannot distinguish a released and unreleased 1.4.0 wheel."""
    from contextopus.startup import Application

    distribution = metadata.distribution('contextopus-core')
    require(distribution.version == manifest['core']['version'], 'Installed Core version differs')
    location = Path(inspect.getfile(Application)).resolve()
    require(location.is_relative_to(Path(sys.prefix).resolve()),
            'Use an installed-wheel environment; Core resolved outside its prefix')
    checked = 0
    with zipfile.ZipFile(bundle / manifest['core']['path']) as wheel:
        for member in wheel.infolist():
            if member.is_dir() or not member.filename.startswith('contextopus/'):
                continue
            path = Path(distribution.locate_file(member.filename))
            require(path.is_file() and hashlib.sha256(path.read_bytes()).digest() ==
                    hashlib.sha256(wheel.read(member)).digest(),
                    'Installed Core bytes differ from bundle wheel: ' + member.filename)
            checked += 1
    require(checked > 0, 'The Core wheel contains no runtime files')
    return {'version': distribution.version, 'source': str(location), 'wheel_files_verified': checked}


def isolated_environment(scratch):
    allowed = ('PATH', 'SystemRoot', 'WINDIR', 'COMSPEC', 'PATHEXT', 'LANG', 'LC_ALL',
               'LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH')
    env = {name: os.environ[name] for name in allowed if name in os.environ}
    for name, directory in {
        'HOME': 'home', 'USERPROFILE': 'home', 'APPDATA': 'appdata',
        'LOCALAPPDATA': 'local', 'XDG_CONFIG_HOME': 'config', 'XDG_DATA_HOME': 'data',
        'XDG_CACHE_HOME': 'cache', 'CODEX_HOME': 'unused-codex', 'HF_HOME': 'models',
        'TMPDIR': 'tmp', 'TEMP': 'tmp', 'TMP': 'tmp',
    }.items():
        target = scratch / directory
        target.mkdir(exist_ok=True)
        env[name] = str(target)
    env.update(PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
               CONTEXTOPUS_LEGACY_TOOLS='0', NO_PROXY='127.0.0.1,localhost')
    return env


def verify(bundle, test_embeddings=False):
    from contextopus.integrations.native import plan
    from contextopus.integrations.remote import RemoteApplication

    class BoundedRemote(RemoteApplication):
        def _sync(self, tool, operation, arguments):
            return self._executor.submit(lambda: asyncio.run(asyncio.wait_for(
                self._call(tool, operation, arguments), timeout=45))).result(timeout=50)

    manifest = load_bundle(bundle)
    support = installer_support(bundle)
    runtime = installed_runtime(bundle, manifest)
    module_ids = {entry['id'] for entry in manifest['modules']}
    require(module_ids == {'workspace', 'session_search'}, 'Expected the two starter modules')
    evidence = {'status': 'passed', 'bundle_version': manifest['bundle_version'],
                'core': runtime, 'tested': [], 'not_tested': [
                    'Installer execution and dependency downloads', 'Real model inference or quality',
                    'User transcripts and live service/client configuration',
                    'Native operating systems other than ' + sys.platform],
                'embedding_fixture': 'deterministic-test-only' if test_embeddings else None}
    with tempfile.TemporaryDirectory(prefix='contextopus-starter-runtime-') as temporary:
        scratch = Path(temporary)
        root = scratch / 'root'
        project = scratch / 'project'
        project.mkdir()
        env = isolated_environment(scratch)
        for entry in manifest['modules']:
            shutil.copytree(bundle / entry['path'], root / 'modules' / entry['id'])
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        require(port != 8765, 'Refusing the live service port')
        endpoint = f'http://127.0.0.1:{port}/mcp'
        evidence['endpoint'] = endpoint
        probe = scratch / 'embedding-fixture.json'
        remote = BoundedRemote(root, endpoint=endpoint)
        process = None
        installed = []
        with tempfile.TemporaryFile() as log:
            try:
                process = subprocess.Popen([sys.executable, '-I', '-B', '-c', SERVER,
                    str(root), str(port), 'fixture' if test_embeddings else 'none', str(probe)],
                    cwd=scratch, env=env, stdout=log, stderr=log)
                deadline = time.monotonic() + 25
                while True:
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=.2):
                            break
                    except Exception:
                        if process.poll() is not None or time.monotonic() > deadline:
                            log.seek(0)
                            raise AssertionError('Isolated owner failed: ' +
                                                 log.read().decode(errors='replace')[-3000:])
                        time.sleep(.05)
                require(remote.execute('core.init')['status'] == 'initialized', 'Core init failed')
                for entry in manifest['modules']:
                    module = entry['id']
                    result = remote.execute('core.module_install', {'module': module})
                    require(result['state'] == 'enabled', 'Module activation failed: ' + module)
                    installed.append(module)
                modules = {item['id']: item for item in remote.query('core.modules')}
                support.require_modules(list(modules.values()), manifest['modules'], bundle)
                evidence['module_install_order'] = list(installed)
                require(modules['session_search']['service']['state'] == 'running',
                        'The real Session Search child service is not running')
                registry = remote.query('describe')['operations']
                require('workspace.settings_read' in registry['query'] and
                        'session_search.status' in registry['query'], 'Module operations are absent')
                # A fresh root has no project context yet. Read the registered
                # Workspace settings contribution through Core's module scope.
                settings = remote.query('core.settings', {
                    'module': 'workspace', 'fields': ['reread_instructions']})
                require(settings['values']['reread_instructions'] is False,
                        'Workspace default settings query failed')
                status = remote.query('session_search.status')
                require(status['integration'] == 'core' and status['worker_alive'] and
                        status['config'] is None and status['indexing'] is False and
                        status['stats']['sessions'] == 0 and status['stats']['vectors'] == 0,
                        'Fresh Session Search is not empty, unconfigured and paused')
                require(not (root / 'core/rag/active.json').exists(),
                        'Module installation unexpectedly initialized embeddings')
                if test_embeddings:
                    require(json.loads(probe.read_text())['providers'] == 0,
                            'Installing modules unexpectedly constructed a provider')
                evidence['tested'].extend(['Exact installed Core wheel bytes',
                    'Bundle payload hashes and module metadata', 'Real isolated MCP HTTP owner',
                    'Fresh Core init and both module installations without a model',
                    'Real Session Search child service and empty paused status',
                    'Workspace operation registry and effective settings'])
                preview = plan('codex', project, root=root, endpoint=endpoint)
                require(all(Path(item['path']).is_relative_to(project) for item in preview['writes']),
                        'Client preview escaped the temporary project')
                skills = {Path(item['path']).parent.name for item in preview['writes']
                          if Path(item['path']).name == 'SKILL.md'}
                require(skills == {'m', 'w', 'w-search', 'w-context', 'w-create', 'w-settings', 'w-analyze'},
                        'Client preview does not contain Core and Workspace skills')
                require(any(endpoint in item.get('content', '') for item in preview['writes']),
                        'Client preview does not use the isolated endpoint')
                require(not (project / '.codex').exists() and not (project / '.agents').exists(),
                        'Client preview wrote configuration or skills')
                evidence['tested'].append('Native Codex integration preview in a temporary project')
                if test_embeddings:
                    from contextopus.core.embeddings import default_config
                    config = default_config()
                    config['profile']['dimensions'] = 2
                    config['provider']['local_files_only'] = True
                    model = remote.query('core.model_plan', {'device': 'cpu', 'config': config})
                    result = remote.execute('core.model_apply', {'plan': model})
                    support.require_setup(result)
                    require(result['status'] == 'ok' and
                            result['setup']['workspace'][0]['status'] == 'ready',
                            'Fixture model setup did not deliver Workspace documentation')
                    require(remote.query('core.base_plan')['status'] == 'current',
                            'Base documentation plan is not current')
                    base = remote.query('core.base_status')
                    search = remote.query('core.search', {
                        'query': 'Contextopus installation verification', 'limit': 1})
                    require(isinstance(search.get('results'), list),
                            'The installer Core search read did not complete')
                    evidence['fixture_setup'] = {
                        'setup': result['setup'], 'base_context': base['context'],
                        'base_present': base['present'], 'base_plan_status': 'current',
                        'installer_require_setup': 'passed',
                        'core_search_result_count': len(search['results'])}
                    scoped = BoundedRemote(root, context=base['context'], endpoint=endpoint)
                    try:
                        scoped_settings = scoped.query('workspace.settings_read', {
                            'fields': ['reread_instructions']})
                        require(scoped_settings['values']['reread_instructions'] is False,
                                'The created base context settings query failed')
                    finally:
                        scoped.close()
                    require(json.loads(probe.read_text())['embed_calls'] > 0,
                            'The explicit embedding fixture was not exercised')
                    require(remote.query('session_search.status')['config'] is None and
                            remote.query('session_search.status')['indexing'] is False,
                            'Model setup silently configured or started transcript indexing')
                    evidence['tested'].extend([
                        'Explicit deterministic embedding setup and base/catalog delivery',
                        'Installer require_setup helper accepted the real nested setup response',
                        'Installer Core search request over real HTTP and LanceDB with the test fixture',
                        'Scoped Workspace settings query in the created base context'])
                    evidence['not_tested'].append('Session transcript search: no source was configured')
                else:
                    evidence['not_tested'].append('Embedding setup and managed base-context delivery')
            finally:
                cleanup_errors = []
                disabled = []
                for module in reversed(installed):
                    try:
                        result = remote.execute('core.module_disable', {'module': module})
                        # Disabled modules retain their prepared release. That
                        # is the lifecycle API's returned state after disable.
                        require(result['state'] == 'prepared', 'Disable was not confirmed: ' + module)
                        disabled.append(module)
                    except Exception as exc:
                        cleanup_errors.append(module + ': ' + str(exc))
                child_stopped = False
                if installed and not cleanup_errors:
                    try:
                        remaining = {item['id']: item for item in remote.query('core.modules')}
                        child_stopped = remaining['session_search']['service']['state'] == 'stopped'
                        if not child_stopped:
                            cleanup_errors.append('The Session Search child did not stop')
                    except Exception as exc:
                        cleanup_errors.append('Child status: ' + str(exc))
                try:
                    remote.close()
                finally:
                    if process is not None:
                        process.terminate()
                        try:
                            process.wait(timeout=12)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=5)
                evidence['cleanup'] = {'disabled_modules': disabled,
                    'session_search_child_stopped': child_stopped,
                    'owner_terminated': process is not None and process.poll() is not None,
                    'owner_exit_code': process.returncode if process is not None else None,
                    'errors': cleanup_errors}
                require(not cleanup_errors, 'Module cleanup failed: ' + '; '.join(cleanup_errors))
        evidence['tested'].append('Module disable/drain and isolated owner termination')
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle-dir', type=Path, required=True)
    parser.add_argument('--python', type=Path, help='Interpreter containing the installed candidate wheel')
    parser.add_argument('--test-embeddings', action='store_true',
                        help='Explicit deterministic test fixture; never real model inference')
    args = parser.parse_args()
    bundle = args.bundle_dir.expanduser().resolve()
    if args.python is not None:
        command = [str(args.python.expanduser().absolute()), '-I', '-B', str(Path(__file__).resolve()),
                   '--bundle-dir', str(bundle)]
        if args.test_embeddings:
            command.append('--test-embeddings')
        return subprocess.call(command)
    try:
        print(json.dumps(verify(bundle, args.test_embeddings), indent=2))
        return 0
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__, 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

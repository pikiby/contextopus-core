"""Explicit installation, activation and recoverable updates of folder modules."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from ..operations import OperationSpec
from .manifest import ModuleManifestReader


class ModuleManager(ModuleManifestReader):
    def __init__(self, app):
        self.app = app
        from ..module_storage import ModuleStorage
        if not hasattr(app, 'module_storage'):
            app.module_storage = ModuleStorage(app.layout)
        super().__init__(app.layout, app.registry.modules)
        self.loaded = {}
        self._active_fingerprints = {}
        self.errors = {}
        for item in self.discover():
            if self.state.get(item['id'], {}).get('enabled') and item['state'] != 'incompatible':
                try:
                    self._activate(item['id'])
                except Exception as exc:
                    self.errors[item['id']] = str(exc)

        self.app.registry.refresh_modules = self.refresh

    def refresh(self):
        """Reconcile this application with shared root state before every API call."""
        from contextlib import nullcontext
        guard = self.app.layout.guard() if hasattr(self.app.layout, 'guard') and self.root.exists() and not (self.root / '.contextopus-freeze.json').exists() else nullcontext()
        with guard:
            self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
            desired = {ident for ident, record in self.state.items() if record.get('enabled')}
            for ident in set(self.loaded) - desired:
                self.app.registry.replace_owned(ident, [])
                self.app.registry.modules.pop(ident, None)
                self.loaded.pop(ident, None)
                self._active_fingerprints.pop(ident, None)
            for ident in desired:
                if ident in self.reserved:
                    self.errors[ident] = 'Built-in module lifecycle is managed by Core'
                    continue
                try:
                    fingerprint = self._digest(ident)
                    if fingerprint != self.state[ident].get('prepared'):
                        raise ValueError('Module changed; prepare and explicitly enable it again')
                    self._require_storage(ident, self._manifest(ident))
                    if self._active_fingerprints.get(ident) != fingerprint:
                        self._activate(ident)
                except Exception as exc:
                    self.app.registry.replace_owned(ident, [])
                    self.app.registry.modules.pop(ident, None)
                    self.loaded.pop(ident, None)
                    self._active_fingerprints.pop(ident, None)
                    self.errors[ident] = str(exc)

    def discover(self):
        result = []
        if not self.base.exists():
            return result
        for directory in sorted(self.base.iterdir()):
            if not (directory / 'module.json').is_file():
                continue
            ident = directory.name
            item = {'id': ident}
            try:
                manifest = self._manifest(ident)
                record = self.state.get(ident, {})
                item.update(operations=[op['name'] for op in manifest.get('operations', [])], skills=manifest.get('skills', 'skills'), procedures=manifest.get('procedures', 'procedures'), filter_algorithms=manifest.get('filter_algorithms', 'filter_algorithms'), open_tui=manifest.get('tui'), version=manifest['version'], state='enabled' if ident in self.loaded else 'prepared' if record.get('prepared') == self._digest(ident) else 'discovered')
                storage = self._storage(ident, manifest)
                if storage is not None:
                    item['storage'] = storage
                    if storage['needs_migration'] and not storage['errors']:
                        item.update(state='storage_pending')
                    elif storage['errors'] or not storage['compatible']:
                        item.update(state='storage_error' if storage['status'] == 'error' else 'storage_incompatible')
                if ident in self.errors:
                    item.update(state='error', error=self.errors[ident])
            except Exception as exc:
                item.update(state='incompatible' if str(exc).startswith('incompatible:') else 'error', error=str(exc))
            result.append(item)
        return result

    def _save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix('.tmp')
        with temporary.open('w') as stream:
            json.dump(self.state, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.state_path)

    def prepare(self, module):
        manifest = self._manifest(module)
        directory = self._code(self._directory(module))
        fingerprint = self._digest(module)
        storage = self._storage(module, manifest)
        if storage is not None and storage['errors']:
            raise ValueError('Module storage preflight failed; preserve data and select a compatible release: ' + '; '.join(storage['errors']))
        dependencies = manifest.get('dependencies', {}).get('python', [])
        if dependencies:
            environment = directory / '.venv'
            if not environment.is_dir():
                subprocess.run(['uv', 'venv', str(environment)], check=True, capture_output=True, text=True)
            subprocess.run(['uv', 'pip', 'install', '--python', str(environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')), *dependencies], check=True, capture_output=True, text=True)
        record = self.state.setdefault(module, {})
        if record.get('prepared') != fingerprint:
            record['enabled'] = False
            self.app.registry.replace_owned(module, [])
            self.app.registry.modules.pop(module, None)
            self.loaded.pop(module, None)
            self._active_fingerprints.pop(module, None)
        record['prepared'] = fingerprint
        self.errors.pop(module, None)
        self._save()
        result = {'id': module, 'state': 'prepared'}
        storage = self._storage(module, manifest)
        if storage is not None:
            result['storage'] = storage
        return result

    def _migrate(self, module):
        manifest = self._manifest(module)
        if 'storage' not in manifest:
            return None
        package = self._code(self._directory(module)) / 'package'
        service = self.app.module_storage
        plan = service.prepare(module, manifest['storage'], package)
        return service.apply(module, manifest['storage'], package, plan['revision'])

    def install(self, module):
        """Install the selected module's dependencies and declared schema, then enable it."""
        self._manifest(module)
        try:
            self.prepare(module)
            self._migrate(module)
            result = self.enable(module)
        except Exception as exc:
            self.disable(module)
            self.errors[module] = str(exc)
            raise
        storage = self._storage(module, self._manifest(module))
        if storage is not None:
            result['storage'] = storage
        return result

    def _activate(self, module):
        manifest = self._manifest(module)
        if self.state.get(module, {}).get('prepared') != self._digest(module):
            raise ValueError('Module changed; prepare and explicitly enable it again')
        self._require_storage(module, manifest)
        directory = self._directory(module)
        specs = []
        for operation in manifest.get('operations', []):
            handler = self._handler(directory, operation, storage_declared='storage' in manifest)
            specs.append(OperationSpec(operation['name'], operation['kind'], operation.get('arguments_schema', {'type': 'object'}), handler, operation.get('description', '')))
        self.app.registry.replace_owned(module, specs)
        self.loaded[module] = manifest
        self._active_fingerprints[module] = self.state[module]["prepared"]
        self.app.registry.register_module(module, available=True, state='enabled', open_tui=manifest.get('tui'))
        self.errors.pop(module, None)

    def _handler(self, directory, operation, *, storage_declared=False):
        code = self._code(directory)
        # Both adapters use a child process, preserving Core's interpreter and imports.
        if 'handler' in operation:
            file, function = operation['handler'].split(':')
            if operation.get('protocol') == 'contextopus-core-v1':
                runner = "import runpy,sys; runpy.run_path(sys.argv[1])['main'](sys.argv[2],sys.argv[3])"
                runner_arguments = [str(Path(__file__).with_name('child.py')), str(code / 'package' / file), function]
            else:
                runner = "import json,runpy,sys; ns=runpy.run_path(sys.argv[1]); print(json.dumps(ns[sys.argv[2]](json.load(sys.stdin))))"
                runner_arguments = [str(code / 'package' / file), function]
            python = code / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            command = [str(python) if python.exists() else sys.executable, '-c', runner, *runner_arguments]
        else:
            command = list(operation['command'])
            executable = command[0]
            if not Path(executable).is_absolute() and ('/' in executable or '\\' in executable):
                command[0] = str(self._inside(code / 'package', executable))
        def invoke(context, **arguments):
            environment = dict(os.environ, CONTEXTOPUS_MODULE_DATA=str(directory / 'data'), CONTEXTOPUS_MODULE_CONFIG=str(directory / 'config'), CONTEXTOPUS_ROOT=str(self.root), PYTHONDONTWRITEBYTECODE='1')
            for path in (directory / 'data', directory / 'config'):
                path.mkdir(exist_ok=True)
            if operation.get('protocol') == 'contextopus-core-v1':
                from .bridge import invoke as bridge_invoke
                return bridge_invoke(command, arguments=arguments, module=directory.name,
                    kind=operation['kind'], storage=self.app.module_storage,
                    declared_storage=storage_declared, cwd=code / 'package',
                    env=environment, timeout=operation.get('timeout', 60))
            output = subprocess.run(command, input=json.dumps(arguments), cwd=code / 'package', env=environment, text=True, capture_output=True, check=True, timeout=operation.get('timeout', 60))
            return json.loads(output.stdout)
        return invoke

    def enable(self, module):
        self._activate(module)
        self.state.setdefault(module, {})['enabled'] = True
        self._save()
        return {'id': module, 'state': 'enabled'}

    def disable(self, module):
        if module in self.reserved:
            raise ValueError('Built-in module lifecycle is managed by Core')
        self._directory(module)
        self.app.registry.replace_owned(module, [])
        self.loaded.pop(module, None)
        self._active_fingerprints.pop(module, None)
        self.app.registry.modules.pop(module, None)
        self.state.setdefault(module, {})['enabled'] = False
        self._save()
        return {'id': module, 'state': 'prepared'}

    def sources(self, module, kind):
        if kind not in ('procedures', 'skills', 'filter_algorithms'):
            raise ValueError('Invalid source kind')
        manifest = self.loaded[module]
        return self._inside(self._code(self._directory(module)) / 'package', manifest.get(kind, kind))

    def update(self, module, source):
        """Stage a release and retain a recoverable backup of the previous code."""
        directory = self._directory(module)
        source = Path(source).resolve()
        self._manifest(module, source)
        staging = Path(tempfile.mkdtemp(prefix='.module-stage-', dir=self.base))
        try:
            shutil.copyfile(source / 'module.json', staging / 'module.json')
            shutil.copytree(source / 'package', staging / 'package', symlinks=False)
            self._manifest(module, staging)
            # Atomically replace a release pointer: data/config stay at module root.
            releases = directory / '.releases'
            releases.mkdir(exist_ok=True)
            release = releases / staging.name
            os.replace(staging, release)
            previous_record = dict(self.state.get(module, {}))
            was_enabled = previous_record.get('enabled', False)
            self.disable(module)
            pointer = directory / '.current.json'
            previous = pointer.read_text() if pointer.exists() else None
            temporary = directory / '.next.json'
            temporary.write_text(json.dumps({'release': str(release.relative_to(directory))}))
            os.replace(temporary, pointer)
            try:
                self.prepare(module)
                self._migrate(module)
                if was_enabled:
                    self.enable(module)
            except Exception as update_error:
                if previous is None:
                    pointer.unlink()
                else:
                    temporary.write_text(previous)
                    os.replace(temporary, pointer)
                self.state[module] = previous_record
                self._save()
                if was_enabled:
                    try:
                        self._activate(module)
                    except Exception as rollback_error:
                        self.disable(module)
                        self.errors[module] = str(rollback_error)
                        raise RuntimeError('Module update failed: ' + str(update_error) +
                            '; previous code cannot reactivate against current storage: ' +
                            str(rollback_error) + '; data/schema preserved; retry core.module_update') from update_error
                raise
            return {'id': module, 'state': 'enabled' if was_enabled else 'prepared', 'previous': previous or 'original package'}
        finally:
            if staging.exists(): shutil.rmtree(staging)

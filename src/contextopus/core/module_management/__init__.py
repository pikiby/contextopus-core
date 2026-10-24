"""Explicit installation, activation and recoverable updates of folder modules."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from contextlib import nullcontext
from functools import wraps

from ..operations import OperationSpec
from .manifest import ModuleManifestReader
from .lifecycle import module_lifecycle
from .adapters import AdapterReplacement


def lifecycle(method=None, *, check_frozen=True):
    """Serialize publication and relocation without retaining the root guard."""
    if method is None:
        return lambda fn: lifecycle(fn, check_frozen=check_frozen)
    @wraps(method)
    def invoke(self, *args, **kwargs):
        if check_frozen and (self.root / '.contextopus-freeze.json').exists():
            raise RuntimeError('Root is frozen for relocation')
        with module_lifecycle(self.root), self.runtime.lock:
            if check_frozen:
                if (self.root / '.contextopus-freeze.json').exists():
                    raise RuntimeError('Root is frozen for relocation')
                if hasattr(self.app.layout, 'guard'):
                    with self.app.layout.guard():
                        pass
            self.state = self._read_state()
            return method(self, *args, **kwargs)
    return invoke


class ModuleManager(AdapterReplacement, ModuleManifestReader):
    def __init__(self, app):
        self.app = app
        from ..module_storage import ModuleStorage
        if not hasattr(app, 'module_storage'):
            app.module_storage = ModuleStorage(app.layout)
        self.adapters = set(app.registry.compatibility_adapters)
        super().__init__(app.layout, set(app.registry.modules) - set(self.adapters))
        self.adapters.difference_update(self.reserved)
        self.adapters.update(module for module, record in self.state.items()
                             if 'adapter_selection' in record and module not in self.reserved)
        from .services import ModuleServiceRegistry
        from ..resources import ProcessResources
        if not hasattr(app, 'resources'):
            app.resources = ProcessResources()
        self.runtime = app.resources.service(('folder_modules', str(self.root)), lambda: ModuleServiceRegistry(self.root))
        self.runtime.manager = self
        self.loaded = {}
        self.contributions = {}
        self._pending_contributions = {}
        self.aliases = {}
        self.procedures = {}
        self._active_fingerprints = {}
        self.errors = {}
        self.app.resources.service(('module_contributions', str(self.root), id(app)), lambda: self)
        self.app.registry.refresh_modules = self.refresh
        self.refresh()

    def refresh(self):
        """Reconcile this application with shared root state before every API call."""
        from .contributions import in_native_call
        if in_native_call():
            # An admitted native request may call Core while lifecycle waits for
            # it to drain. Keep its request snapshot; reconcile at the next call.
            return
        with self.runtime.lock:
            self.state = self._read_state()
            desired = {ident for ident, record in self.state.items() if record.get('enabled')}
            for ident in (set(self.loaded) | set(self.runtime.services)) - desired:
                self.runtime.stop(ident)
                self._unpublish(ident)
            self._reconcile_adapters()
            for ident in desired:
                if self._adapter_pending(ident):
                    continue
                if ident in self.reserved:
                    self.errors[ident] = 'Built-in module lifecycle is managed by Core'
                    continue
                try:
                    fingerprint = self._digest(ident)
                    if fingerprint != self.state[ident].get('prepared'):
                        raise ValueError('Module changed; prepare and explicitly enable it again')
                    self._require_storage(ident, self._manifest(ident))
                    service = self.runtime.services.get(ident)
                    if service is not None and service.fingerprint != fingerprint:
                        self.runtime.stop(ident)
                    if self._active_fingerprints.get(ident) != fingerprint:
                        self._activate(ident)
                except Exception as exc:
                    self.runtime.stop(ident)
                    self._unpublish(ident)
                    self.errors[ident] = str(exc)
            self._sync_index_lifecycle()

    def _sync_index_lifecycle(self):
        index = getattr(self.app, 'index', None)
        if index is None:
            return
        statuses = {}
        for module, record in self.state.items():
            status = 'disabled'
            if record.get('enabled'):
                status = 'unavailable'
                if module in self.loaded and module not in self.errors:
                    manifest = self.loaded[module]
                    service = self.runtime.services.get(module)
                    if 'service' not in manifest or service is not None and service.status()['state'] == 'running':
                        status = 'enabled'
                elif (module in self.app.registry.compatibility_adapters
                      and not self._folder_selected(module)
                      and self.app.registry.modules.get(module, {}).get('available')):
                    status = 'enabled'
            statuses[module] = status
        index.module_states = statuses

    def _unpublish(self, module):
        self.app.registry.replace_owned(module, [])
        self.app.registry.modules.pop(module, None)
        self.loaded.pop(module, None)
        self._active_fingerprints.pop(module, None)
        try:
            self._remove_contribution(module)
        finally:
            self._restore_adapter(module)

    @lifecycle(check_frozen=False)
    def start_services(self):
        if (self.root / '.contextopus-freeze.json').exists() or (self.root / '.contextopus-redirect.json').exists():
            return
        self.refresh()
        for module in list(self.state):
            if self._adapter_pending(module):
                try:
                    self.enable(module)
                except Exception:
                    # Failure is recorded durably by the replacement attempt;
                    # ordinary refresh/listing must never retry readiness.
                    pass
        for module, manifest in list(self.loaded.items()):
            if 'service' in manifest and module not in self.runtime.services:
                try:
                    self._start_service(module, manifest)
                except Exception as exc:
                    self.errors[module] = str(exc)

    def _start_service(self, module, manifest, *, pending_activation=False):
        from .services import ModuleService
        code = self._code(self._directory(module))
        command = self._command(code, manifest['service'], service=True)
        service = ModuleService(self.app, module, manifest, self._digest(module), command,
                                code / 'package', self._environment(self._directory(module)),
                                pending_activation=pending_activation)
        self.runtime.services[module] = service
        service.start()


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
                operations = [op['name'] for op in manifest.get('operations', [])]
                if ident in self.contributions:
                    # Native factories publish their contracts at activation;
                    # discovery must stay inert when the contribution is absent.
                    operations = sorted(self.app.registry._owned.get(ident, ()))
                item.update(operations=operations, skills=manifest.get('skills', 'skills'), procedures=manifest.get('procedures', 'procedures'), filter_algorithms=manifest.get('filter_algorithms', 'filter_algorithms'), open_tui=manifest.get('tui'), version=manifest['version'], state='enabled' if ident in self.loaded else 'prepared' if record.get('prepared') == self._digest(ident) else 'discovered')
                if 'service' in manifest:
                    service = self.runtime.services.get(ident)
                    item['service'] = service.status() if service else {'state': 'stopped', 'pid': None}
                    if service is not None and service.error:
                        item.update(state='error', error=service.error)
                storage = self._storage(ident, manifest)
                if storage is not None:
                    item['storage'] = storage
                    if storage['needs_migration'] and not storage['errors']:
                        item.update(state='storage_pending')
                    elif storage['errors'] or not storage['compatible']:
                        item.update(state='storage_error' if storage['status'] == 'error' else 'storage_incompatible')
                if ident in self.errors:
                    item.update(state='error', error=self.errors[ident])
                elif self._adapter_pending(ident):
                    item['state'] = 'activation_pending'
            except Exception as exc:
                item.update(state='incompatible' if str(exc).startswith('incompatible:') else 'error', error=str(exc))
            result.append(item)
        return result

    def _save(self):
        guard = self.app.layout.guard() if hasattr(self.app.layout, 'guard') else nullcontext()
        with guard:
            self._save_locked()

    def _save_locked(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix('.tmp')
        with temporary.open('w') as stream:
            json.dump(self.state, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.state_path)

    @lifecycle
    def prepare(self, module):
        manifest = self._manifest(module)
        directory = self._code(self._directory(module))
        fingerprint = self._digest(module)
        storage = self._storage(module, manifest)
        if storage is not None and storage['errors']:
            raise ValueError('Module storage preflight failed; preserve data and select a compatible release: ' + '; '.join(storage['errors']))
        if self.state.get(module, {}).get('prepared') != fingerprint:
            # Retire the previous interpreter before touching its dependencies.
            self.runtime.stop(module)
        dependencies = manifest.get('dependencies', {}).get('python', [])
        if dependencies:
            environment = directory / '.venv'
            if not environment.is_dir():
                subprocess.run(['uv', 'venv', str(environment)], check=True, capture_output=True, text=True)
            subprocess.run(['uv', 'pip', 'install', '--python', str(environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')), *dependencies], check=True, capture_output=True, text=True)
        record = self.state.setdefault(module, {})
        if module in self.adapters:
            record['adapter_selection'] = 'folder' if self._folder_selected(module) else 'pending'
        if record.get('prepared') != fingerprint:
            self.runtime.stop(module)
            record['enabled'] = False
            self._unpublish(module)
        record['prepared'] = fingerprint
        self.errors.pop(module, None)
        self._save()
        result = {'id': module, 'state': 'prepared'}
        storage = self._storage(module, manifest)
        if storage is not None:
            result['storage'] = storage
        return result

    def _contribution_candidate(self, module, manifest):
        fingerprint = self._digest(module)
        active = self.contributions.get(module)
        if active is not None and active.fingerprint == fingerprint:
            return active
        candidate = self._pending_contributions.get(module)
        if candidate is not None and candidate.fingerprint != fingerprint:
            self._pending_contributions.pop(module, None)
            candidate.close()
            candidate = None
        if candidate is None:
            from .contributions import load_contribution
            candidate = load_contribution(self.app, module, self._code(self._directory(module)),
                                          fingerprint, manifest['contribution'])
            self._pending_contributions[module] = candidate
        return candidate

    def _migrate(self, module):
        manifest = self._manifest(module)
        result = None
        if 'storage' in manifest:
            package = self._code(self._directory(module)) / 'package'
            service = self.app.module_storage
            plan = service.prepare(module, manifest['storage'], package)
            result = service.apply(module, manifest['storage'], package, plan['revision'])
        if 'contribution' in manifest:
            candidate = self._contribution_candidate(module, manifest)
            prepare = candidate.hooks.get('install_prepare', [])
            apply = candidate.hooks.get('install_apply', [])
            if len(prepare) != len(apply):
                raise ValueError('Contribution installation requires paired prepare/apply hooks')
            plans = [callback() for callback in prepare]
            if any(not isinstance(plan, dict) or not isinstance(plan.get('revision'), str) for plan in plans):
                raise ValueError('Contribution install preparation must return a revision')
            for callback, plan in zip(apply, plans):
                callback(plan['revision'])
        return result

    @lifecycle
    def install(self, module, source=None, source_revision=None):
        """Install the selected module's dependencies and declared schema, then enable it."""
        if source is not None:
            from .source import inspect_source, staged_source, publish_new
            preview = self.source_plan(module, source)
            if source_revision is None or source_revision != preview['revision']:
                raise ValueError('Module source preview is missing or stale; inspect it again')
            plan = inspect_source(source, module)
            if plan['fingerprint'] != preview['revision']:
                raise ValueError('Module source changed after preview; inspect it again')
            with staged_source(plan, self.root / 'core/tmp') as stage:
                self._manifest(module, stage)
                # Lifecycle serialization protects Core requests; mkdir below also
                # refuses an unrelated process that creates the target meanwhile.
                self._new_source_target(module)
                self.base.mkdir(parents=True, exist_ok=True)
                publish_new(stage, self._directory(module))
        self._manifest(module)
        try:
            self.prepare(module)
            self._migrate(module)
            result = self.enable(module)
        except Exception as exc:
            if module in self.adapters:
                self._adapter_failed(module, exc)
            else:
                self.disable(module)
            self.errors[module] = str(exc)
            raise
        storage = self._storage(module, self._manifest(module))
        if storage is not None:
            result['storage'] = storage
        return result

    def _new_source_target(self, module):
        target = self._directory(module)
        if self.base.is_symlink():
            raise ValueError('Module base must not be a symlink')
        if target.exists() or target.is_symlink() or module in self._read_state():
            raise ValueError('Module already exists; use the explicit update flow, or retry install without --source')
        if module in self.reserved:
            raise ValueError('Built-in module lifecycle is managed by Core')
        return target

    def source_plan(self, module, source):
        """Validate and fingerprint an artifact without executing its code."""
        from .source import inspect_source
        self._new_source_target(module)
        plan = inspect_source(source, module)
        self.validate_value(module, plan['manifest'])
        return {'module': module, 'source': plan['source'], 'version': plan['version'],
                'core_requires': plan['core_requires'], 'files': len(plan['files']),
                'bytes': plan['bytes'], 'revision': plan['fingerprint'],
                'effects': ['Copy a new built module', 'Prepare declared dependencies and storage',
                            'Run installation hooks and enable the module']}

    def _activation(self, module):
        manifest = self._manifest(module)
        if self.state.get(module, {}).get('prepared') != self._digest(module):
            raise ValueError('Module changed; prepare and explicitly enable it again')
        self._require_storage(module, manifest)
        directory = self._directory(module)
        specs = []
        if 'contribution' in manifest:
            candidate = self._contribution_candidate(module, manifest)
            try:
                for callback in candidate.hooks.get('ready', []):
                    callback()
            except BaseException:
                self._pending_contributions.pop(module, None)
                candidate.close()
                raise
            specs = list(candidate.registry._operations.values())
        for operation in manifest.get('operations', []):
            handler = self._handler(directory, operation, storage_declared='storage' in manifest, rag_declared=manifest.get('rag', False))
            specs.append(OperationSpec(operation['name'], operation['kind'], operation.get('arguments_schema', {'type': 'object'}), handler, operation.get('description', ''), guard_root=False))
        return manifest, specs

    def _activate(self, module):
        if self._active_fingerprints.get(module) == self._digest(module):
            return
        self._publish_activation(module, *self._activation(module))

    def _publish_activation(self, module, manifest, specs):
        candidate = self._pending_contributions.pop(module, None)
        try:
            for spec in specs:
                if spec.name in self.aliases and self.aliases[spec.name][0] != module:
                    raise ValueError('Operation conflicts with module alias: ' + spec.name)
            if candidate is not None:
                self._validate_contribution(module, candidate)
            self.app.registry.replace_owned(module, specs)
        except BaseException:
            if candidate is not None:
                candidate.close()
            raise
        try:
            self._remove_contribution(module)
        except BaseException:
            self.app.registry.replace_owned(module, [])
            if candidate is not None:
                candidate.close()
            raise
        if candidate is not None:
            self.contributions[module] = candidate
            self.aliases.update({name: (module, target) for name, target in candidate.aliases.items()})
            self.procedures.update({name: (module, provider) for name, provider in candidate.procedures.items()})
            for name, adapter in candidate.index.sources.items():
                self.app.index.register_source(name, adapter)
            if candidate.settings_factory is not None:
                self.app.services._settings.providers[module] = candidate.settings_factory
            self.app.journal.search_operations.update(candidate.search_operations)
        self.loaded[module] = manifest
        self._active_fingerprints[module] = self.state[module]["prepared"]
        self.app.registry.register_module(module, available=True, state='enabled', open_tui=manifest.get('tui'))
        self.errors.pop(module, None)

    def _validate_contribution(self, module, candidate):
        operations = self.app.registry._operations
        own = getattr(self.app.registry, '_owned', {}).get(module, set())
        for alias, target in candidate.aliases.items():
            if (alias in operations and alias not in own) or (alias in self.aliases and self.aliases[alias][0] != module):
                raise ValueError('Conflicting operation alias: ' + alias)
            if target not in candidate.registry._operations:
                raise ValueError('Alias target is not contributed: ' + target)
        for name in candidate.procedures:
            if name in self.procedures and self.procedures[name][0] != module:
                raise ValueError('Conflicting module procedure: ' + name)
        for operation in candidate.search_operations:
            if operation not in candidate.registry._operations:
                raise ValueError('Search evidence operation is not contributed: ' + operation)
        for source in candidate.index.sources:
            if source in self.app.index.source_adapters and source != module:
                raise ValueError('Conflicting RAG source: ' + source)

    def _remove_contribution(self, module):
        contribution = self.contributions.pop(module, None)
        pending = self._pending_contributions.pop(module, None)
        self.aliases = {key: value for key, value in self.aliases.items() if value[0] != module}
        self.procedures = {key: value for key, value in self.procedures.items() if value[0] != module}
        failures = []
        for candidate in (pending, contribution):
            if candidate is None:
                continue
            for name, adapter in candidate.index.sources.items():
                if self.app.index.source_adapters.get(name) is adapter:
                    self.app.index.source_adapters.pop(name, None)
            if candidate.settings_factory is not None:
                self.app.services._settings.providers.pop(module, None)
                self.app.services._settings._providers.pop(module, None)
            for operation in candidate.search_operations:
                self.app.journal.search_operations.pop(operation, None)
            try:
                candidate.close()
            except Exception as exc:
                failures.append(exc)
        if failures:
            raise ExceptionGroup('Module contribution cleanup failed', failures)

    def run_hooks(self, event, *args):
        return {module: [contribution.invoke(callback, *args) for callback in contribution.hooks.get(event, [])]
                for module, contribution in list(self.contributions.items())
                if contribution.hooks.get(event)}

    def quiesce_contributions(self):
        from .contributions import quiesce_contributions
        return quiesce_contributions(list(self.contributions.values()))

    def close_contributions(self):
        failures = []
        for module in set(self.contributions) | set(self._pending_contributions):
            try:
                self._remove_contribution(module)
            except Exception as exc:
                failures.append(exc)
        if failures:
            raise ExceptionGroup('Module contributions failed to close', failures)

    def close(self):
        self.close_contributions()

    def _command(self, code, declaration, *, service=False):
        target = declaration.get('factory' if service else 'handler')
        if target is not None:
            file, function = target.split(':')
            if service or declaration.get('protocol') == 'contextopus-core-v1':
                runner = "import runpy,sys; runpy.run_path(sys.argv[1])['main'](sys.argv[2],sys.argv[3])"
                adapter = 'service_child.py' if service else 'child.py'
                runner_arguments = [str(Path(__file__).with_name(adapter)), str(code / 'package' / file), function]
            else:
                runner = "import json,runpy,sys; ns=runpy.run_path(sys.argv[1]); print(json.dumps(ns[sys.argv[2]](json.load(sys.stdin))))"
                runner_arguments = [str(code / 'package' / file), function]
            python = code / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            return [str(python) if python.exists() else sys.executable, '-c', runner, *runner_arguments]
        command = list(declaration['command'])
        executable = command[0]
        if not Path(executable).is_absolute() and ('/' in executable or '\\' in executable):
            command[0] = str(self._inside(code / 'package', executable))
        return command

    def _environment(self, directory):
        for path in (directory / 'data', directory / 'config'):
            path.mkdir(exist_ok=True)
        return dict(os.environ, CONTEXTOPUS_MODULE_DATA=str(directory / 'data'),
            CONTEXTOPUS_MODULE_CONFIG=str(directory / 'config'), CONTEXTOPUS_ROOT=str(self.root),
            PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')

    def _handler(self, directory, operation, *, storage_declared=False, rag_declared=False):
        code = self._code(directory)
        command = None if operation.get('service') else self._command(code, operation)
        def invoke(context, /, **arguments):
            if operation.get('service'):
                with self.runtime.lock:
                    service = self.runtime.services.get(directory.name)
                if service is None:
                    raise RuntimeError('Module service is not running; start the service owner')
                return service.request(operation['name'], operation['kind'], arguments, context, operation.get('timeout', 60))
            environment = self._environment(directory)
            if operation.get('protocol') == 'contextopus-core-v1':
                from .bridge import invoke as bridge_invoke
                from .core_access import ModuleCoreAccess
                access = ModuleCoreAccess(self.app, directory.name, kind=operation['kind'],
                    storage_declared=storage_declared, rag_declared=rag_declared)
                try:
                    return bridge_invoke(command, arguments=arguments, module=directory.name,
                        kind=operation['kind'], storage=self.app.module_storage, access=access,
                        declared_storage=storage_declared, cwd=code / 'package',
                        env=environment, timeout=operation.get('timeout', 60))
                finally:
                    access.close()
            output = subprocess.run(command, input=json.dumps(arguments), cwd=code / 'package', env=environment,
                encoding='utf-8', capture_output=True, check=True, timeout=operation.get('timeout', 60))
            return json.loads(output.stdout)
        return invoke

    @lifecycle
    def enable(self, module):
        if module in self.adapters and not self._folder_selected(module):
            return self._enable_replacement(module)
        self._activate(module)
        self.state.setdefault(module, {})['enabled'] = True
        self._save()
        if 'service' in self.loaded[module] and self.app.resources.services_started:
            self.runtime.stop(module)
            try:
                self._start_service(module, self.loaded[module])
            except Exception as exc:
                self.state[module]['enabled'] = False
                self._save()
                self._unpublish(module)
                self.errors[module] = str(exc)
                raise
        self._sync_index_lifecycle()
        return {'id': module, 'state': 'enabled'}

    @lifecycle
    def disable(self, module):
        if module in self.reserved:
            raise ValueError('Built-in module lifecycle is managed by Core')
        if module in self.adapters:
            return self._disable_replacement(module)
        self._directory(module)
        self.runtime.stop(module)
        self.state.setdefault(module, {})['enabled'] = False
        self._save()
        self.errors.pop(module, None)
        self._unpublish(module)
        self._sync_index_lifecycle()
        return {'id': module, 'state': 'prepared'}

    def sources(self, module, kind):
        if kind not in ('procedures', 'skills', 'filter_algorithms'):
            raise ValueError('Invalid source kind')
        manifest = self.loaded[module]
        return self._inside(self._code(self._directory(module)) / 'package', manifest.get(kind, kind))

    @lifecycle
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
            replacing_adapter = module in self.adapters and not self._folder_selected(module)
            was_enabled = previous_record.get('enabled', False) or replacing_adapter
            if replacing_adapter:
                # Staging an update is not the user's explicit logical disable,
                # and cannot select a folder before its first readiness check.
                self.runtime.stop(module)
            else:
                self.disable(module)
            pointer = directory / '.current.json'
            previous = pointer.read_text() if pointer.exists() else None
            temporary = directory / '.next.json'
            with self.app.layout.guard() if hasattr(self.app.layout, 'guard') else nullcontext():
                temporary.write_text(json.dumps({'release': str(release.relative_to(directory))}))
                os.replace(temporary, pointer)
            try:
                self.prepare(module)
                self._migrate(module)
                if was_enabled:
                    activation = self.enable(module)
                else:
                    candidate = self._pending_contributions.pop(module, None)
                    if candidate is not None:
                        candidate.close()
            except Exception as update_error:
                saved = self._read_state()
                if replacing_adapter and self._folder_selected(module, saved):
                    self.state = saved
                    self.errors[module] = str(update_error)
                    raise
                with self.app.layout.guard() if hasattr(self.app.layout, 'guard') else nullcontext():
                    if previous is None:
                        pointer.unlink()
                    else:
                        temporary.write_text(previous)
                        os.replace(temporary, pointer)
                self.state[module] = previous_record
                if replacing_adapter:
                    self.state[module]['activation_error'] = str(update_error)
                self._save()
                if replacing_adapter:
                    self._unpublish(module)
                    self.errors[module] = str(update_error)
                elif was_enabled:
                    try:
                        self._activate(module)
                        if 'service' in self.loaded[module] and self.app.resources.services_started:
                            self.runtime.stop(module)
                            self._start_service(module, self.loaded[module])
                    except Exception as rollback_error:
                        self.disable(module)
                        self.errors[module] = str(rollback_error)
                        raise RuntimeError('Module update failed: ' + str(update_error) +
                            '; previous code cannot reactivate against current storage: ' +
                            str(rollback_error) + '; data/schema preserved; retry core.module_update') from update_error
                raise
            return {'id': module, 'state': activation['state'] if was_enabled else 'prepared', 'previous': previous or 'original package'}
        finally:
            if staging.exists(): shutil.rmtree(staging)

"""Opt-in root-local modules. Discovery only reads manifests; activation is explicit."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from ..operations import OperationSpec


class ModuleManifestReader:
    """Read module contracts and fingerprints without activation or dependency work."""
    def __init__(self, layout, reserved=()):
        self.root = layout.root
        self.base = self.root / 'modules'
        self.state_path = self.root / 'core/configuration/modules.json'
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        self.reserved = set(reserved) | {'workspace', 'core'}

    def inspect_sources(self, kind):
        if kind not in ('procedures', 'skills', 'filter_algorithms'):
            raise ValueError('Invalid source kind')
        directories, signature, errors = [], [], []
        for ident, record in sorted(self.state.items()):
            if not record.get('enabled'):
                continue
            try:
                manifest = self._manifest(ident)
                fingerprint = self._digest(ident)
                if fingerprint != record.get('prepared'):
                    raise ValueError('Module changed; prepare and explicitly enable it again')
                directories.append(self._inside(self._code(self._directory(ident)) / 'package', manifest.get(kind, kind)))
                signature.append((ident, fingerprint))
            except Exception as exc:
                errors.append({'module': ident, 'error': str(exc)})
        return directories, signature, errors

    def _directory(self, ident):
        if not isinstance(ident, str) or not re.fullmatch(r'[a-z][a-z0-9_-]*', ident):
            raise ValueError('Invalid module ID')
        directory = self.base / ident
        if directory.is_symlink():
            raise ValueError('Module directory must not be a symlink')
        return directory

    @staticmethod
    def _inside(base, relative):
        target = (base / relative).resolve()
        if not target.is_relative_to(base.resolve()):
            raise ValueError('Module path escapes package')
        return target

    def _code(self, directory):
        pointer = directory / '.current.json'
        if pointer.is_file():
            relative = json.loads(pointer.read_text())['release']
            resolved = (directory / relative).resolve()
            if not resolved.is_relative_to((directory / '.releases').resolve()):
                raise ValueError('Release pointer escapes module')
            return resolved
        return directory

    def _manifest(self, ident, directory=None):
        if ident in self.reserved:
            raise ValueError('Built-in module lifecycle is managed by Core')
        directory = self._code(directory or self._directory(ident))
        if (directory / 'package').is_symlink():
            raise ValueError('Package must not be a symlink')
        value = json.loads((directory / 'module.json').read_text())
        from jsonschema import Draft202012Validator
        validator = Draft202012Validator({
            'type': 'object', 'required': ['id', 'version'],
            'properties': {
                'id': {'type': 'string'}, 'version': {'type': 'string'},
                'core_requires': {'type': 'string'},
                'dependencies': {'type': 'object', 'additionalProperties': False, 'properties': {'python': {'type': 'array', 'items': {'type': 'string', 'minLength': 1}}}},
                **{kind: {'type': 'string'} for kind in ('skills', 'procedures', 'filter_algorithms', 'tui')},
                'operations': {'type': 'array', 'items': {
                    'type': 'object', 'required': ['name', 'kind'],
                    'oneOf': [{'required': ['handler'], 'not': {'required': ['command']}}, {'required': ['command'], 'not': {'required': ['handler']}}],
                    'properties': {
                        'name': {'type': 'string'}, 'kind': {'enum': ['query', 'execute']},
                        'handler': {'type': 'string'},
                        'command': {'type': 'array', 'minItems': 1, 'items': {'type': 'string', 'minLength': 1}},
                        'arguments_schema': {'type': 'object'}, 'description': {'type': 'string'},
                        'timeout': {'type': 'number', 'exclusiveMinimum': 0},
                    }
                }},
            }
        })
        try:
            validator.validate(value)
        except Exception as exc:
            raise ValueError('Invalid module manifest: ' + str(exc)) from exc
        if value.get('id') != ident or not isinstance(value.get('version'), str):
            raise ValueError('Manifest ID/version missing or mismatched')
        from packaging.specifiers import SpecifierSet
        from packaging.version import Version
        Version(value['version'])
        core = importlib.metadata.version('contextopus-core')
        if Version(core) not in SpecifierSet(value.get('core_requires', '')):
            raise RuntimeError('incompatible: Core ' + core)
        for kind in ('procedures', 'skills', 'filter_algorithms'):
            self._inside(directory / 'package', value.get(kind, kind))
        names = set()
        for operation in value.get('operations', []):
            name = operation['name']
            if not name.startswith(ident + '.') or name in names:
                raise ValueError('Operations must use unique module ID prefix')
            names.add(name)
            if operation['kind'] not in ('query', 'execute'):
                raise ValueError('Invalid operation kind')
            if 'handler' in operation:
                file, function = operation['handler'].split(':')
                if not function.isidentifier() or not self._inside(directory / 'package', file).is_file():
                    raise ValueError('Invalid Python handler')
                handler_path = self._inside(directory / 'package', file)
                try:
                    compile(handler_path.read_text(encoding='utf-8'), str(handler_path), 'exec')
                except SyntaxError as exc:
                    raise ValueError('Invalid Python handler syntax: ' + str(exc)) from exc
            elif not isinstance(operation.get('command'), list) or not operation['command']:
                raise ValueError('Operation requires handler or command argv')
        return value

    def _digest(self, ident):
        directory = self._code(self._directory(ident))
        digest = hashlib.sha256((directory / 'module.json').read_bytes())
        for path in sorted((directory / 'package').rglob('*')):
            if path.is_symlink():
                raise ValueError('Package symlinks are not supported')
            if path.is_file():
                digest.update(str(path.relative_to(directory)).encode())
                digest.update(path.read_bytes())
        return digest.hexdigest()


class ModuleManager(ModuleManifestReader):
    def __init__(self, app):
        self.app = app
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
        return {'id': module, 'state': 'prepared'}

    def _activate(self, module):
        manifest = self._manifest(module)
        if self.state.get(module, {}).get('prepared') != self._digest(module):
            raise ValueError('Module changed; prepare and explicitly enable it again')
        directory = self._directory(module)
        specs = []
        for operation in manifest.get('operations', []):
            handler = self._handler(directory, operation)
            specs.append(OperationSpec(operation['name'], operation['kind'], operation.get('arguments_schema', {'type': 'object'}), handler, operation.get('description', '')))
        self.app.registry.replace_owned(module, specs)
        self.loaded[module] = manifest
        self._active_fingerprints[module] = self.state[module]["prepared"]
        self.app.registry.register_module(module, available=True, state='enabled', open_tui=manifest.get('tui'))
        self.errors.pop(module, None)

    def _handler(self, directory, operation):
        code = self._code(directory)
        # Both adapters use a child process, preserving Core's interpreter and imports.
        if 'handler' in operation:
            file, function = operation['handler'].split(':')
            runner = "import json,runpy,sys; ns=runpy.run_path(sys.argv[1]); print(json.dumps(ns[sys.argv[2]](json.load(sys.stdin))))"
            python = code / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            command = [str(python) if python.exists() else sys.executable, '-c', runner, str(code / 'package' / file), function]
        else:
            command = list(operation['command'])
            executable = command[0]
            if not Path(executable).is_absolute() and ('/' in executable or '\\' in executable):
                command[0] = str(self._inside(code / 'package', executable))
        def invoke(context, **arguments):
            environment = dict(os.environ, CONTEXTOPUS_MODULE_DATA=str(directory / 'data'), CONTEXTOPUS_MODULE_CONFIG=str(directory / 'config'), CONTEXTOPUS_ROOT=str(self.root))
            for path in (directory / 'data', directory / 'config'):
                path.mkdir(exist_ok=True)
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
                if was_enabled:
                    self.enable(module)
            except Exception:
                if previous is None:
                    pointer.unlink()
                else:
                    temporary.write_text(previous)
                    os.replace(temporary, pointer)
                self.state[module] = previous_record
                self._save()
                if was_enabled:
                    self._activate(module)
                raise
            return {'id': module, 'state': 'enabled' if was_enabled else 'prepared', 'previous': previous or 'original package'}
        finally:
            if staging.exists(): shutil.rmtree(staging)

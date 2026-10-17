"""Read-only discovery and validation of root-local module contracts."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re


class ModuleManifestReader:
    """Read module contracts and fingerprints without activation or dependency work."""
    def __init__(self, layout, reserved=()):
        self.layout = layout
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
                self._require_storage(ident, manifest)
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
                'storage': {'type': 'object'},
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
                        'protocol': {'enum': ['contextopus-core-v1']},
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
        if 'storage' in value:
            from ..module_storage import validate_contract
            validate_contract(value['storage'])
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

    def _storage(self, ident, manifest):
        if 'storage' not in manifest:
            return None
        from ..module_storage import ModuleStorage
        service = getattr(getattr(self, 'app', None), 'module_storage', None)
        if service is None:
            service = ModuleStorage(self.layout)
        return service.inspect(ident, manifest['storage'], self._code(self._directory(ident)) / 'package')

    def _require_storage(self, ident, manifest):
        report = self._storage(ident, manifest)
        if report is not None and (report['errors'] or not report['compatible'] or report['needs_migration']):
            raise ValueError('Module storage is not ready; use core.module_install: ' + json.dumps(report))
        return report

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


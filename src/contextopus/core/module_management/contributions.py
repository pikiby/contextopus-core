"""Trusted, optional in-process contributions using the ordinary module lifecycle.

This mode has the same trust as installing Python code into the Core process.
Factories are loaded only for explicitly enabled, fingerprint-current releases.
"""
from importlib import util
from importlib.abc import MetaPathFinder
from importlib.machinery import SourceFileLoader
from pathlib import Path
from contextlib import contextmanager
from dataclasses import replace
from pydantic import ConfigDict, create_model
import hashlib
import sys
import threading

from ..operations import OperationRegistry, OperationSpec

_LOAD_LOCK = threading.RLock()
_PACKAGES = {}
_SOURCE_ROOTS = {}
_ACTIVITY = {}
_LOCAL = threading.local()


def in_native_call():
    return bool(getattr(_LOCAL, 'depth', 0))


class _Activity:
    def __init__(self):
        self.condition = threading.Condition(threading.RLock())
        self.active = 0
        self.draining = False
        self.deferred = []


@contextmanager
def _admitted(host):
    activity = host._activity
    owned = getattr(_LOCAL, 'owned', {})
    with activity.condition:
        while activity.draining and not in_native_call():
            activity.condition.wait()
        if host._closed:
            raise RuntimeError('Module contribution has closed; retry the request')
        activity.active += 1
        namespace = host._namespace
        _LOCAL.owned = {**owned, namespace: owned.get(namespace, 0) + 1}
        _LOCAL.depth = getattr(_LOCAL, 'depth', 0) + 1
    try:
        yield
    finally:
        pending = []
        with activity.condition:
            activity.active -= 1
            _LOCAL.depth -= 1
            _LOCAL.owned[namespace] -= 1
            if activity.active == 0:
                pending, activity.deferred = activity.deferred, []
                activity.condition.notify_all()
        for candidate in pending:
            candidate._finish_close()



@contextmanager
def quiesce_contributions(hosts):
    """Drain a root's native calls before relocation closes their runtime state."""
    if in_native_call():
        raise RuntimeError('Relocation must run outside a native module request')
    activities = sorted({host._activity for host in hosts}, key=id)
    acquired = []
    try:
        # Nested requests remain admitted until their outer request completes.
        # Blocking only new outer admission avoids cross-module drain cycles.
        for activity in activities:
            with activity.condition:
                while activity.draining:
                    activity.condition.wait()
                activity.draining = True
                acquired.append(activity)
        for activity in acquired:
            with activity.condition:
                while activity.active:
                    activity.condition.wait()
        _LOCAL.depth = 1
        try:
            yield
        finally:
            _LOCAL.depth = 0
    finally:
        for activity in reversed(acquired):
            with activity.condition:
                activity.draining = False
                activity.condition.notify_all()


class _SourceOnlyLoader(SourceFileLoader):
    def get_code(self, fullname):
        # Cached bytecode is not a release source and must never bypass its
        # fingerprint through forged timestamps or stale same-size files.
        return self.source_to_code(self.get_data(self.path), self.path)


class _ContributionFinder(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        namespace, separator, relative = fullname.partition('.')
        base = _SOURCE_ROOTS.get(namespace)
        if base is None or not separator:
            return None
        location = base.joinpath(*relative.split('.'))
        package = location / '__init__.py'
        source = location.with_suffix('.py')
        if package.is_file():
            return util.spec_from_file_location(fullname, package,
                loader=_SourceOnlyLoader(fullname, str(package)),
                submodule_search_locations=[str(location)])
        if source.is_file():
            return util.spec_from_file_location(fullname, source,
                loader=_SourceOnlyLoader(fullname, str(source)))
        return None


_FINDER = _ContributionFinder()
sys.meta_path.insert(0, _FINDER)


class ContributionIndex:
    def __init__(self, index):
        self._index = index
        self.sources = {}

    def register_source(self, module, adapter):
        if module in self.sources:
            raise ValueError('Duplicate contributed RAG source: ' + module)
        self.sources[module] = adapter

    def __getattr__(self, name):
        return getattr(self._index, name)


class _OwnedObject:
    """Keep contributed service callbacks admitted for their full invocation."""
    def __init__(self, host, value):
        object.__setattr__(self, '_host', host)
        object.__setattr__(self, '_value', value)

    def __getattr__(self, name):
        value = getattr(self._value, name)
        if callable(value):
            return lambda *args, **kwargs: self._host.invoke(value, *args, **kwargs)
        return value

    def __setattr__(self, name, value):
        setattr(self._value, name, value)


class ContributionHost:
    """App-like Core services with staged, module-owned registrations.

    New attributes belong to this host. Registrations become visible only after
    the factory has completed and all operation/alias/provider conflicts pass.
    """
    def __init__(self, app, module, package):
        self._app, self.module, self.package = app, module, Path(package)
        self.registry = OperationRegistry()
        self.index = ContributionIndex(app.index)
        self.aliases, self.procedures, self.hooks = {}, {}, {}
        self.settings_factory = None
        self.search_operations = {}
        self._closed = False
        self._namespace = None
        self._activity = None

    @property
    def layout(self):
        return self._app.layout

    @property
    def resources(self):
        return self._app.resources

    @property
    def services(self):
        return self._app.services

    @property
    def module_storage(self):
        return self._app.module_storage

    @property
    def context(self):
        return self._app.context

    def active_profile(self):
        return self._app.active_profile()

    def write_active_profile(self, value):
        return self._app.write_active_profile(value)

    def query(self, operation, arguments=None):
        return self._app.query(operation, arguments)

    def execute(self, operation, arguments=None):
        return self._app.execute(operation, arguments)

    def search_operation(self, operation, instruction_revision=None):
        self.search_operations[operation] = instruction_revision

    def _operation(self, name, kind, fn, fields=None):
        model = create_model(name.replace('.', '_') + '_arguments',
                             __config__=ConfigDict(extra='forbid', strict=True), **(fields or {}))
        self.registry.register(OperationSpec(name, kind, model,
            lambda context, **arguments: fn(**arguments), fn.__doc__ or name, guard_root=False))

    def alias(self, name, operation):
        if name in self.aliases:
            raise ValueError('Duplicate operation alias: ' + name)
        self.aliases[name] = operation

    def procedure(self, name, provider):
        if name in self.procedures or not callable(provider):
            raise ValueError('Invalid or duplicate procedure: ' + name)
        self.procedures[name] = lambda: self.invoke(provider)

    def hook(self, event, callback):
        if event not in {'setup', 'apply_profile', 'initialize', 'before_relocation', 'after_relocation', 'close', 'install_prepare', 'install_apply', 'ready'}:
            raise ValueError('Unknown contribution hook: ' + event)
        if not callable(callback):
            raise ValueError('Contribution hook must be callable')
        self.hooks.setdefault(event, []).append(callback)

    def settings_provider(self, factory):
        if self.settings_factory is not None or not callable(factory):
            raise ValueError('Settings provider must be one callable')
        def create(layout, registry=None):
            return _OwnedObject(self, self.invoke(factory, layout, registry=registry))
        self.settings_factory = create

    def invoke(self, callback, *args, **kwargs):
        with _admitted(self):
            return callback(*args, **kwargs)

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._activity is not None and getattr(_LOCAL, 'owned', {}).get(self._namespace, 0):
            with self._activity.condition:
                self._activity.deferred.append(self)
            return
        self._finish_close()

    def _finish_close(self):
        activity = self._activity
        if activity is not None:
            with activity.condition:
                while activity.draining:
                    activity.condition.wait()
                activity.draining = True
                while activity.active:
                    activity.condition.wait()
        failures = []
        try:
            for callback in reversed(self.hooks.get('close', [])):
                try:
                    callback()
                except Exception as exc:
                    failures.append(exc)
            if self._namespace:
                release_package(self._namespace)
                self._namespace = None
        finally:
            if activity is not None:
                with activity.condition:
                    activity.draining = False
                    activity.condition.notify_all()
        if failures:
            raise ExceptionGroup('Module contribution failed to close', failures)


def load_contribution(app, module, code, fingerprint, declaration):
    package = code / 'package'
    file, function = declaration['factory'].split(':')
    path = (package / file).resolve()
    # A distinct namespace separates roots/releases, while Applications sharing
    # a root and release share package globals and their runtime caches.
    identity = hashlib.sha256((str(app.layout.root) + ':' + module + ':' + fingerprint).encode()).hexdigest()
    namespace = '_contextopus_module_' + identity
    host = ContributionHost(app, module, package)
    host.fingerprint = fingerprint
    with _LOAD_LOCK:
        if namespace not in _PACKAGES:
            _SOURCE_ROOTS[namespace] = path.parent
            spec = util.spec_from_file_location(namespace, path,
                loader=_SourceOnlyLoader(namespace, str(path)),
                submodule_search_locations=[str(path.parent)])
            if spec is None or spec.loader is None:
                raise ValueError('Unable to load module contribution')
            imported = util.module_from_spec(spec)
            sys.modules[namespace] = imported
            try:
                spec.loader.exec_module(imported)
            except BaseException:
                _SOURCE_ROOTS.pop(namespace, None)
                for name in list(sys.modules):
                    if name == namespace or name.startswith(namespace + '.'):
                        sys.modules.pop(name, None)
                raise
            _PACKAGES[namespace] = [imported, 0]
            _ACTIVITY[namespace] = _Activity()
        imported, count = _PACKAGES[namespace]
        _PACKAGES[namespace][1] = count + 1
        host._namespace = namespace
        host._activity = _ACTIVITY[namespace]
    try:
        getattr(imported, function)(host)
        for operation in host.registry._operations:
            if not operation.startswith(module + '.'):
                raise ValueError('Contribution operations must use the module ID prefix')
        for source in host.index.sources:
            if source != module:
                raise ValueError('A contribution can register only its own RAG source')
        host.index.sources = {name: _OwnedObject(host, adapter)
                              for name, adapter in host.index.sources.items()}
        for name, spec in list(host.registry._operations.items()):
            def handler(context, _callback=spec.handler, **arguments):
                return host.invoke(_callback, context, **arguments)
            host.registry._operations[name] = replace(spec, handler=handler)
        return host
    except BaseException:
        host.close()
        raise


def release_package(namespace):
    with _LOAD_LOCK:
        entry = _PACKAGES.get(namespace)
        if entry is None:
            return
        entry[1] -= 1
        if entry[1]:
            return
        _PACKAGES.pop(namespace)
        _SOURCE_ROOTS.pop(namespace, None)
        _ACTIVITY.pop(namespace, None)
        for name in list(sys.modules):
            if name == namespace or name.startswith(namespace + '.'):
                sys.modules.pop(name, None)

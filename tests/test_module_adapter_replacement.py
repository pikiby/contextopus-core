"""Replace an available compatibility adapter through real folder services."""

import json
import os
from pathlib import Path
import socket
import threading

import pytest

import shutil
import sys
from contextopus.core.operations import OperationRegistry, OperationSpec
from contextopus.core.resources import ProcessResources
from contextopus.startup import Application


MODULE = "sample_adapter"


def legacy_executable():
    return shutil.which('sample-adapter')


class LegacyAdapter:
    """Synthetic adapter for Core takeover coverage; no optional module code."""
    def available(self):
        return legacy_executable() is not None

    def request(self, payload):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3)
            client.connect(os.environ['CONTEXTOPUS_TEST_LEGACY_SOCKET'])
            client.sendall(json.dumps(payload).encode() + b'\n')
            with client.makefile('rb') as stream:
                return json.loads(stream.readline())

    def register(self, registry):
        empty = {'type': 'object', 'properties': {}, 'additionalProperties': False}
        registry.register(OperationSpec(MODULE + '.status', 'query', empty,
                                       lambda ctx: self.request({'op': 'status'})))
        registry.register(OperationSpec(MODULE + '.search', 'query',
            {'type': 'object', 'properties': {'query': {'type': 'string'}},
             'required': ['query'], 'additionalProperties': False},
            lambda ctx, query: self.request({'op': 'search', 'query': query})))
        registry.register(OperationSpec(MODULE + '.open_tui', 'execute', empty,
            lambda ctx: {'argv': [legacy_executable(), 'tui']}))
SERVICE = '''
import os
from pathlib import Path
class Service:
    def start(self):
        if (Path(os.environ["CONTEXTOPUS_MODULE_DATA"]) / "fail").exists():
            raise RuntimeError("candidate readiness failed")
    def dispatch(self, operation, arguments, context):
        return {"implementation": "folder", "pid": os.getpid(), "context": context}
    def close(self):
        pass
def create_service(core):
    return Service()
'''


@pytest.fixture(autouse=True)
def declared_external_adapter(monkeypatch):
    """Supply a synthetic external adapter explicitly; Core has no fallback."""
    from contextopus.core.module_management import ModuleManager
    original = ModuleManager.__init__
    def initialize(manager, app):
        if MODULE not in app.registry.modules:
            adapter = LegacyAdapter()
            if adapter.available():
                app.registry.register_compatibility_adapter(
                    MODULE, adapter.register, available=True, state='available',
                    open_tui='sample_adapter.open_tui')
        original(manager, app)
    monkeypatch.setattr(ModuleManager, '__init__', initialize)


@pytest.fixture
def legacy(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("The legacy daemon bridge uses a Unix launcher/socket")
    binary = tmp_path / "bin/sample-adapter"
    binary.parent.mkdir()
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(binary.parent) + os.pathsep + os.environ.get("PATH", ""))
    endpoint = tmp_path / "legacy.sock"
    monkeypatch.setenv("CONTEXTOPUS_TEST_LEGACY_SOCKET", str(endpoint))
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(endpoint))
    server.listen()
    server.settimeout(.1)
    stop = threading.Event()

    def serve():
        while not stop.is_set():
            try:
                connection, _ = server.accept()
            except socket.timeout:
                continue
            with connection, connection.makefile("rb") as stream:
                request = json.loads(stream.readline())
                connection.sendall(json.dumps({"ok": True, "implementation": "legacy", "query": request.get("query")}).encode() + b"\n")

    worker = threading.Thread(target=serve)
    worker.start()
    assert LegacyAdapter().available()
    try:
        yield binary
    finally:
        stop.set()
        worker.join(timeout=2)
        server.close()
        assert not worker.is_alive()


def candidate(root):
    directory = root / "modules" / MODULE
    package = directory / "package"
    package.mkdir(parents=True)
    (package / "worker.py").write_text(SERVICE)
    manifest = {"id": MODULE, "version": "1.0",
                "service": {"factory": "worker.py:create_service", "ready_timeout": 2, "stop_timeout": .2},
                "operations": [{"name": MODULE + "." + name, "kind": "query", "service": True}
                               for name in ("status", "new_only")]}
    (directory / "module.json").write_text(json.dumps(manifest))
    (directory / "data").mkdir()
    (directory / "data/preserved").write_text("existing user data")
    return directory


def assert_legacy(app):
    assert app.query("sample_adapter.search", {"query": "existing index"}) == {
        "ok": True, "implementation": "legacy", "query": "existing index"}


def test_running_owner_replaces_available_legacy_adapter_with_folder_service(tmp_path, legacy):
    root = tmp_path / "root"
    directory = candidate(root)
    with Application(root, discover=False) as app:
        assert_legacy(app)
        app.resources.start_services()
        assert app.execute("core.module_install", {"module": MODULE})["state"] == "enabled"
        assert app.query("sample_adapter.status")["implementation"] == "folder"
        assert app.query("sample_adapter.new_only")["implementation"] == "folder"
        with pytest.raises(ValueError, match="Unknown operation"):
            app.query("sample_adapter.search", {"query": "legacy must not remain"})
        assert "sample_adapter.open_tui" not in app.registry._operations
        assert (directory / "data/preserved").read_text() == "existing user data"
        assert legacy.is_file()


def saved(root):
    return json.loads((root / "core/configuration/modules.json").read_text())[MODULE]


def assert_no_legacy(app):
    app.registry.describe()
    assert "sample_adapter.search" not in app.registry._operations
    assert "sample_adapter.open_tui" not in app.registry._operations


def test_pending_without_owner_preserves_legacy_then_cross_app_owner_commits(tmp_path, legacy, monkeypatch):
    root = tmp_path / "root"
    candidate(root)
    resources = ProcessResources()
    first = Application(root, "first", resources=resources, discover=False)
    second = Application(root, "second", resources=resources, discover=False)
    try:
        assert first.execute("core.module_install", {"module": MODULE})["state"] == "activation_pending"
        assert saved(root)["adapter_selection"] == "pending"
        with monkeypatch.context() as patch:
            patch.setattr("contextopus.core.module_management.services.subprocess.Popen", lambda *args, **kw: pytest.fail("listing started service"))
            assert second.query("core.modules")[0]["state"] == "activation_pending"
            assert second.registry.describe("sample_adapter.status")["kind"] == "query"
            assert_legacy(first)
            assert_legacy(second)
        resources.start_services()
        assert saved(root)["adapter_selection"] == "folder"
        assert first.query("sample_adapter.status")["context"] == "first"
        assert second.query("sample_adapter.status")["context"] == "second"
        assert_no_legacy(first)
        assert_no_legacy(second)
        first.execute("core.module_disable", {"module": MODULE})
        assert saved(root)["adapter_selection"] == "folder"
        assert_no_legacy(second)
        with pytest.raises(ValueError, match="Unknown operation"):
            second.query("sample_adapter.status")
    finally:
        resources.close()
    with Application(root, discover=False) as restarted:
        restarted.resources.start_services()
        assert_no_legacy(restarted)
        with pytest.raises(ValueError, match="Unknown operation"):
            restarted.query("sample_adapter.search", {"query": "disabled"})
        restarted.execute("core.module_enable", {"module": MODULE})
        assert restarted.query("sample_adapter.status")["implementation"] == "folder"


@pytest.mark.parametrize("failure", ["manifest", "dependency", "schema", "readiness"])
def test_failed_first_install_keeps_working_legacy_and_visible_candidate_error(tmp_path, legacy, monkeypatch, failure):
    root = tmp_path / "root"
    directory = candidate(root)
    manifest_path = directory / "module.json"
    manifest = json.loads(manifest_path.read_text())
    if failure == "manifest":
        manifest["operations"][0]["name"] = "foreign.status"
    elif failure == "dependency":
        manifest["dependencies"] = {"python": ["invalid-test-package"]}
        def fail(*args, **kwargs):
            raise RuntimeError("candidate dependency failed")
        monkeypatch.setattr("contextopus.core.module_management.subprocess.run", fail)
    elif failure == "schema":
        (directory / "package/migrations").mkdir()
        (directory / "package/migrations/001-schema.sql").write_text("INVALID CANDIDATE SQL;")
        manifest["storage"] = {"engine": "sqlite", "schema_version": 1, "migrations": "migrations", "compatible_versions": {"min": 1, "max": 1}}
    else:
        (directory / "data/fail").touch()
    manifest_path.write_text(json.dumps(manifest))
    with Application(root, discover=False) as app:
        app.resources.start_services()
        with pytest.raises(Exception):
            app.execute("core.module_install", {"module": MODULE})
        assert_legacy(app)
        assert app.query("core.modules")[0]["state"] == "error"
        assert "sample_adapter.new_only" not in app.registry._operations
        assert (directory / "data/preserved").read_text() == "existing user data"
        if failure != "manifest":
            assert not saved(root)["enabled"]
            assert saved(root).get("adapter_selection") != "folder"
    with Application(root, discover=False) as restarted:
        restarted.resources.start_services()
        assert_legacy(restarted)


def test_pending_failed_readiness_is_not_retried_by_inspection_or_owner_hook(tmp_path, legacy, monkeypatch):
    root = tmp_path / "root"
    directory = candidate(root)
    (directory / "data/fail").touch()
    with Application(root, discover=False) as app:
        assert app.execute("core.module_install", {"module": MODULE})["state"] == "activation_pending"
        app.resources.start_services()
        assert saved(root)["enabled"] is False
        assert saved(root)["adapter_selection"] == "pending"
        with monkeypatch.context() as patch:
            patch.setattr("contextopus.core.module_management.services.subprocess.Popen", lambda *a, **kw: pytest.fail("failed readiness was implicitly retried"))
            for _ in range(2):
                assert_legacy(app)
                assert "candidate readiness failed" in app.query("core.modules")[0]["error"]
                app.resources.start_services()
        (directory / "data/fail").unlink()
        app.execute("core.module_enable", {"module": MODULE})
        assert app.query("sample_adapter.status")["implementation"] == "folder"


@pytest.mark.parametrize("boundary", ["before_save", "after_save", "after_publication"])
def test_first_activation_failure_uses_durable_ownership_boundary(tmp_path, legacy, monkeypatch, boundary):
    root = tmp_path / "root"
    candidate(root)
    with Application(root, discover=False) as app:
        app.resources.start_services()
        manager = app.module_manager
        save, publish = manager._save, manager._publish_activation
        failed = False

        def saving():
            nonlocal failed
            if not failed and manager.state.get(MODULE, {}).get("adapter_selection") == "folder":
                failed = True
                if boundary == "after_save":
                    save()
                raise OSError("activation save boundary")
            return save()

        def publishing(*args, **kwargs):
            publish(*args, **kwargs)
            raise OSError("activation publication boundary")

        with monkeypatch.context() as patch:
            if boundary == "after_publication":
                patch.setattr(manager, "_publish_activation", publishing)
            else:
                patch.setattr(manager, "_save", saving)
            with pytest.raises(OSError, match="boundary"):
                app.execute("core.module_install", {"module": MODULE})
        if boundary == "before_save":
            assert_legacy(app)
        else:
            assert saved(root)["adapter_selection"] == "folder"
            assert_no_legacy(app)
            with pytest.raises(ValueError, match="Unknown operation"):
                app.query("sample_adapter.search", {"query": "no fallback"})
    with Application(root, discover=False) as restarted:
        if boundary == "before_save":
            assert_legacy(restarted)
        else:
            assert_no_legacy(restarted)


def test_restart_success_and_later_service_failure_never_revives_adapter(tmp_path, legacy):
    root = tmp_path / "root"
    directory = candidate(root)
    with Application(root, discover=False) as app:
        app.resources.start_services()
        app.execute("core.module_install", {"module": MODULE})
        original = app.query("sample_adapter.status")["pid"]
    with Application(root, discover=False) as restarted:
        restarted.resources.start_services()
        assert restarted.query("sample_adapter.status")["pid"] != original
        assert_no_legacy(restarted)
    (directory / "data/fail").touch()
    with Application(root, discover=False) as failed:
        failed.resources.start_services()
        assert_no_legacy(failed)
        assert failed.query("core.modules")[0]["state"] == "error"
        with pytest.raises(RuntimeError):
            failed.query("sample_adapter.status")


@pytest.mark.parametrize('enabled', [True, False], ids=['enabled', 'disabled'])
def test_historical_folder_without_selection_still_owns_id(tmp_path, legacy, enabled):
    root = tmp_path / "root"
    candidate(root)
    with Application(root, discover=False) as old:
        old.execute("core.module_prepare", {"module": MODULE})
    path = root / "core/configuration/modules.json"
    state = json.loads(path.read_text())
    state[MODULE]['enabled'] = enabled
    state[MODULE].pop('adapter_selection')
    assert 'adapter_selection' not in state[MODULE]
    path.write_text(json.dumps(state))
    assert LegacyAdapter().available()
    with Application(root, discover=False) as restarted:
        restarted.resources.start_services()
        assert_no_legacy(restarted)
        if enabled:
            assert restarted.query("sample_adapter.status")["implementation"] == "folder"
        else:
            with pytest.raises(ValueError, match='Unknown operation'):
                restarted.query('sample_adapter.status')


def test_true_builtins_and_unrelated_native_entrypoint_remain_protected(tmp_path, legacy, monkeypatch):
    from types import SimpleNamespace
    root = tmp_path / "root"
    candidate(root)
    def register(app):
        app.registry.register_module(MODULE, state="native")
        app.registry.register(OperationSpec("sample_adapter.native", "query", {}, lambda context: {"native": True}))
    entry = SimpleNamespace(name=MODULE, load=lambda: register)
    monkeypatch.setattr("contextopus.startup.metadata.entry_points", lambda **kw: [entry])
    with Application(root) as app:
        path = root / 'core/configuration/modules.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({MODULE: {'adapter_selection': 'pending', 'enabled': True, 'prepared': 'foreign'}}))
        for ident in ("core", MODULE):
            with pytest.raises(ValueError, match="Built-in"):
                app.execute("core.module_install", {"module": ident})
        assert app.query("sample_adapter.native") == {"native": True}
        assert MODULE not in app.registry.compatibility_adapters
        assert MODULE not in app.module_manager.adapters


def test_registry_replacement_conflict_leaves_entire_legacy_group_intact():
    registry = OperationRegistry()
    def adapter(target):
        for name in ("adapter.one", "adapter.two"):
            target.register(OperationSpec(name, "query", {}, lambda context: {"legacy": True}))
    registry.register_compatibility_adapter("adapter", adapter, state="available")
    registry.register(OperationSpec("adapter.foreign", "query", {}, lambda context: {}))
    previous = dict(registry._operations)
    with pytest.raises(ValueError, match="conflicting"):
        registry.replace_owned("adapter", [OperationSpec(name, "query", {}, lambda context: {})
                                           for name in ("adapter.one", "adapter.foreign")])
    assert registry._operations == previous


@pytest.mark.parametrize("fails", [False, True])
def test_first_transition_through_update_preserves_legacy_on_readiness_failure(tmp_path, legacy, fails):
    root = tmp_path / "root"
    directory = candidate(root)
    replacement = tmp_path / "release"
    candidate(replacement)
    release = replacement / "modules" / MODULE
    if fails:
        (directory / "data/fail").touch()
    with Application(root, discover=False) as app:
        app.resources.start_services()
        assert_legacy(app)
        if fails:
            with pytest.raises(RuntimeError, match="candidate readiness failed"):
                app.execute("core.module_update", {"module": MODULE, "source": str(release)})
            assert_legacy(app)
            assert not (directory / ".current.json").exists()
        else:
            assert app.execute("core.module_update", {"module": MODULE, "source": str(release)})["state"] == "enabled"
            assert app.query("sample_adapter.status")["implementation"] == "folder"
            assert_no_legacy(app)
        assert (directory / "package/worker.py").is_file()
        assert (directory / "data/preserved").read_text() == "existing user data"
    if fails:
        with Application(root, discover=False) as restarted:
            assert_legacy(restarted)
            assert 'candidate readiness failed' in restarted.query('core.modules')[0]['error']


def test_dispatch_releases_legacy_guard_when_shared_operation_is_replaced(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from contextlib import contextmanager
    from types import SimpleNamespace
    from contextopus.core.storage import StorageLayout, _root_lock
    registry = OperationRegistry()
    registry.register_compatibility_adapter("adapter", lambda target: target.register(
        OperationSpec("adapter.status", "query", {}, lambda context: {"legacy": True})))
    waiting, release = threading.Event(), threading.Event()
    guard = StorageLayout.guard

    @contextmanager
    def paused_guard(layout, *args, **kwargs):
        waiting.set()
        assert release.wait(3)
        with guard(layout, *args, **kwargs):
            yield

    def folder(context):
        assert getattr(_root_lock(tmp_path)[1], 'depth', 0) == 0
        return {"folder": True}

    monkeypatch.setattr(StorageLayout, 'guard', paused_guard)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(registry.dispatch, "query", "adapter.status", {}, SimpleNamespace(root=tmp_path))
        try:
            assert waiting.wait(2)
            registry.replace_owned("adapter", [OperationSpec("adapter.status", "query", {}, folder, guard_root=False)])
        finally:
            release.set()
        assert future.result(timeout=3) == {"folder": True}


def test_pending_replacement_finishes_when_legacy_is_unavailable_then_stays_folder(tmp_path, legacy, monkeypatch):
    root = tmp_path / "root"
    candidate(root)
    with Application(root, discover=False) as app:
        assert app.execute("core.module_install", {"module": MODULE})["state"] == "activation_pending"
    # Hide every external launcher/package through discovery boundaries, rather
    # than disabling LegacyAdapter.available itself. The persisted transition
    # still belongs to the pending folder installation.
    with monkeypatch.context() as patch:
        patch.setattr(sys.modules[__name__], 'legacy_executable', lambda: None)
        with Application(root, discover=False) as owner:
            assert MODULE not in owner.registry.compatibility_adapters
            assert owner.query('core.modules')[0]['state'] == 'activation_pending'
            owner.resources.start_services()
            assert owner.query('sample_adapter.status')['implementation'] == 'folder'
            assert saved(root)['adapter_selection'] == 'folder'
    assert LegacyAdapter().available()
    with Application(root, discover=False) as restarted:
        restarted.resources.start_services()
        assert restarted.query('sample_adapter.status')['implementation'] == 'folder'
        assert_no_legacy(restarted)


def test_existing_app_without_legacy_tracks_pending_selection_from_other_app(tmp_path, legacy, monkeypatch):
    root = tmp_path / 'root'
    candidate(root)
    with monkeypatch.context() as patch:
        patch.setattr(sys.modules[__name__], 'legacy_executable', lambda: None)
        owner = Application(root, discover=False)
    try:
        assert MODULE not in owner.module_manager.adapters
        with Application(root, discover=False) as installing:
            assert_legacy(installing)
            assert installing.execute('core.module_install', {'module': MODULE})['state'] == 'activation_pending'
            assert owner.query('core.modules')[0]['state'] == 'activation_pending'
            assert 'sample_adapter.status' not in owner.registry._operations
            owner.resources.start_services()
            assert saved(root)['adapter_selection'] == 'folder'
            assert owner.query('sample_adapter.status')['implementation'] == 'folder'
            assert_no_legacy(installing)
    finally:
        owner.close()


def test_explicit_disable_before_takeover_does_not_reenable_legacy(tmp_path, legacy):
    root = tmp_path / 'root'
    candidate(root)
    with Application(root, discover=False) as app:
        app.execute('core.module_prepare', {'module': MODULE})
        assert saved(root)['adapter_selection'] == 'pending'
        assert_legacy(app)
        app.execute('core.module_disable', {'module': MODULE})
        assert saved(root)['adapter_selection'] == 'folder'
        assert_no_legacy(app)
    with Application(root, discover=False) as restarted:
        assert_no_legacy(restarted)


def test_first_update_failure_after_durable_selection_cannot_restore_legacy(tmp_path, legacy, monkeypatch):
    root = tmp_path / 'root'
    directory = candidate(root)
    release = candidate(tmp_path / 'new-root')
    with Application(root, discover=False) as app:
        app.resources.start_services()
        publish = app.module_manager._publish_activation
        def published_then_failed(*args):
            publish(*args)
            raise OSError('after durable update publication')
        with monkeypatch.context() as patch:
            patch.setattr(app.module_manager, '_publish_activation', published_then_failed)
            with pytest.raises(OSError, match='after durable'):
                app.execute('core.module_update', {'module': MODULE, 'source': str(release)})
        assert saved(root)['adapter_selection'] == 'folder'
        assert (directory / '.current.json').is_file()
        assert_no_legacy(app)
    with Application(root, discover=False) as restarted:
        assert_no_legacy(restarted)

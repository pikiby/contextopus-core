"""Fresh starter orchestration with disposable files and mocked external systems."""

import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "distribution"


@pytest.fixture
def installer_module(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("starter_install_under_test", SCRIPTS / "install.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def support(installer_module):
    return sys.modules["install_support"]


def payload(tmp_path):
    bundle = tmp_path / "bundle with spaces"
    modules = []
    for ident in ("alpha", "beta"):
        folder = bundle / "modules" / ident
        (folder / "package").mkdir(parents=True)
        manifest = {"id": ident, "version": "1.0"}
        if ident == "beta":
            manifest["service"] = {"factory": "worker.py:create"}
        (folder / "module.json").write_text(json.dumps(manifest))
        (folder / "package/worker.py").write_text("# verified fixture payload\n")
        modules.append({"id": ident, "version": "1.0", "path": "modules/" + ident, "core_requires": ">=1.4,<2"})
    wheel = bundle / "packages/contextopus_core-1.4.0-py3-none-any.whl"
    wheel.parent.mkdir()
    wheel.write_bytes(b"wheel contents checked by the separate bundle validator")
    manifest = {"schema_version": 1, "bundle_version": "review.1", "python": "3.12",
                "core": {"path": "packages/" + wheel.name, "version": "1.4.0"}, "modules": modules}
    (bundle / "bundle.json").write_text(json.dumps(manifest))
    return bundle, manifest


class FakeSystem:
    def __init__(self, support, root, tmp_path, *, platform=None):
        self.support, self.root = support, root
        self.paths = {"uv": "/existing/uv", **support.tool_paths(tmp_path / "tool storage", tmp_path / "tool bin", platform=platform)}
        self.paths.update(binding_path=tmp_path / "default-root.json", binding_fingerprint=None)
        self.calls = []
        self.failure = None
        self.setup_status = "ready"
        self.model_status = "ok"
        self.module_state = "enabled"
        self.service_state = "running"
        self.client_errors = []

    def check(self, root, run, probe, **kwargs):
        self.support.fresh_root(root)
        return self.paths

    def probe(self):
        return {"root": str(self.root), "pid": 1234}

    def run(self, argv, **kwargs):
        argv = list(map(str, argv))
        self.calls.append(argv)
        if argv[:3] == [self.paths["uv"], "tool", "install"]:
            for name in ("python", "executable"):
                path = self.paths[name]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("disposable executable fixture")
            return ""
        if argv[0] == str(self.paths["python"]):
            return json.dumps({"version": "1.4.0", "source": str(self.paths["prefix"] / "lib/contextopus/startup.py")})
        assert argv[0] == str(self.paths["executable"])
        if argv[1:] == ["--version"]:
            return "Contextopus 1.4.0\n"
        assert argv[1:3] == ["--root", str(self.root)]
        args = argv[3:]
        if self.failure and args[:len(self.failure)] == self.failure:
            raise self.support.InstallError("synthetic external failure")
        if args == ["init"]:
            return json.dumps({"status": "initialized", "root": str(self.root)})
        if args[:2] == ["modules", "install"]:
            return json.dumps({"id": args[2], "state": self.module_state})
        if args[0] == "setupmodel":
            preview = {"applied": False, "selected_device": "cpu", "effects": {"may_download_weights": True}}
            if "--apply" not in args:
                return json.dumps(preview)
            result = {"status": self.model_status,
                      "setup": {"alpha": [{"status": self.setup_status,
                                           "base_context": {"status": "installed"}}]}}
            return json.dumps(preview) + "\n" + json.dumps(result)
        if args[:2] == ["query", "core.modules"]:
            return json.dumps([{"id": "alpha", "version": "1.0", "state": "enabled"},
                               {"id": "beta", "version": "1.0", "state": "enabled",
                                "service": {"state": self.service_state, "pid": 77}}])
        if args[:2] == ["query", "procedure"]:
            return json.dumps({"name": "modules", "content": "Core module guide"})
        if args[:2] == ["query", "core.status"]:
            return json.dumps({"scope": str(self.root), "state": "idle"})
        if args[:2] == ["query", "core.search"]:
            return json.dumps({"results": []})
        if args[0] == "integrate":
            preview = {"client": args[1], "module_errors": self.client_errors,
                       "files": [{"path": "temporary client configuration", "changed": True}]}
            if "--apply" not in args:
                return json.dumps(preview)
            return json.dumps(preview) + "\n" + json.dumps({"client": args[1], "written": ["temporary client configuration"], "removed": []})
        if args[:2] == ["root", "--set"]:
            return json.dumps({"root": str(self.root), "binding": "temporary binding"})
        raise AssertionError(argv)


def make_installer(installer_module, support, tmp_path, **settings):
    bundle, manifest = payload(tmp_path)
    root = tmp_path / "new memory root"
    system = FakeSystem(support, root, tmp_path, platform=settings.pop("platform", None))
    options = {"root": str(root), "clients": ["codex"], "skip_model": False, "device": "cpu", **settings}
    installer = installer_module.Installer(bundle, manifest, options, run=system.run,
                                          probe=system.probe, check=system.check, output=lambda *a, **kw: None)
    return installer, system


def test_plan_runs_no_commands_network_mutation_or_input(installer_module, tmp_path, monkeypatch, capsys):
    bundle, manifest = payload(tmp_path)
    monkeypatch.setattr(installer_module, "load_bundle", lambda root: manifest)
    monkeypatch.setattr(installer_module, "Installer", lambda *a, **kw: pytest.fail("plan constructed an installer"))
    before = {str(path.relative_to(tmp_path)): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert installer_module.main(["--plan", "--root", str(tmp_path / "memory"), "--client", "hermes"],
                                 bundle_root=bundle, input_fn=lambda text: pytest.fail("plan requested input")) == 0
    after = {str(path.relative_to(tmp_path)): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert before == after
    plan = json.loads(capsys.readouterr().out)
    assert plan["options"]["clients"] == ["hermes"]
    assert plan["commands"][0][-1].endswith(".whl[local]")
    assert not (tmp_path / "memory").exists()
    assert not (bundle / "__pycache__").exists()


def test_generic_install_order_private_executable_and_final_binding(installer_module, support, tmp_path):
    installer, system = make_installer(installer_module, support, tmp_path)
    receipt = installer.apply()
    assert receipt["status"] == "installed" and receipt["search_ready"]
    assert receipt["clients_require_reload"] == ["codex"]
    assert (installer.root / "modules/alpha/package/worker.py").is_file()
    steps = receipt["completed_steps"]
    assert steps.index("install_module:beta") < steps.index("setup_cpu_model_and_search") < steps.index("integrate_client:codex")
    assert steps[-1] == "bind_default_root"
    assert system.calls[0] == [system.paths["uv"], "tool", "install", "--python", "3.12", "--torch-backend", "cpu",
                               str(installer.bundle_root / installer.manifest["core"]["path"]) + "[local]"]
    assert "--force" not in repr(system.calls)
    assert all(call[0] != "contextopus" for call in system.calls)
    assert json.loads(installer.receipt_path.read_text())["bundle_fingerprint"]


def test_skip_model_still_installs_local_runtime_and_is_not_search_ready(installer_module, support, tmp_path):
    installer, system = make_installer(installer_module, support, tmp_path, skip_model=True, clients=[])
    result = installer.apply()
    assert result["status"] == "installed" and result["search_ready"] is False
    assert system.calls[0][-1].endswith("[local]")
    assert not any("setupmodel" in call or "core.search" in call for call in system.calls)
    assert "verify_core_and_module_catalog" in result["completed_steps"]


@pytest.mark.parametrize("failure", ["business", "setup", "module", "service", "client", "exception"])
def test_failures_retain_partial_state_and_never_bind_or_claim_success(installer_module, support, tmp_path, failure):
    installer, system = make_installer(installer_module, support, tmp_path)
    if failure == "business":
        system.model_status = "failed"
    elif failure == "setup":
        system.setup_status = "pending"
    elif failure == "module":
        system.module_state = "activation_pending"
    elif failure == "service":
        system.service_state = "stopped"
    elif failure == "client":
        system.client_errors = [{"module": "alpha", "error": "stale package"}]
    else:
        system.failure = ["integrate", "codex", "--user", "--apply"]
    with pytest.raises(support.InstallError):
        installer.apply()
    receipt = json.loads(installer.receipt_path.read_text())
    assert receipt["status"] == "failed" and receipt["search_ready"] is False
    assert receipt["failed_step"]
    assert not any(call[-3:-1] == ["root", "--set"] for call in system.calls)
    assert installer.root.is_dir() and (installer.root / "modules/alpha/module.json").is_file()
    assert "rollback" not in repr(system.calls) and "uninstall" not in repr(system.calls)


def test_wrong_root_after_initialization_stops_before_modules(installer_module, support, tmp_path):
    installer, system = make_installer(installer_module, support, tmp_path)
    installer.probe = lambda: {"root": str(tmp_path / "another root"), "pid": 12}
    with pytest.raises(support.InstallError, match="does not match"):
        installer.apply()
    assert not any("install_module:" in item for item in installer.receipt["completed_steps"])
    assert installer.receipt["failed_step"] == "initialize_core_and_user_service"


def test_windows_private_paths_do_not_use_shell_or_path_lookup(installer_module, support, tmp_path):
    installer, system = make_installer(installer_module, support, tmp_path, platform="win32", clients=[])
    installer.apply()
    assert system.paths["python"].parts[-2:] == ("Scripts", "python.exe")
    assert system.paths["executable"].parts[-2:] == ("Scripts", "contextopus.exe")
    assert " " in str(system.paths["prefix"])


@pytest.fixture
def preflight_system(support, tmp_path, monkeypatch):
    monkeypatch.delenv("CONTEXTOPUS_ROOT", raising=False)
    binding = tmp_path / "config/root.json"
    monkeypatch.setattr(support, "binding_path", lambda: binding)
    monkeypatch.setattr(support, "native_preflight", lambda run: None)
    monkeypatch.setattr(support.shutil, "which", lambda name: {"uv": "/tools/uv", "git": "/tools/git"}.get(name))
    calls = []
    def run(argv, **kw):
        calls.append(argv)
        if argv[0] == "/tools/git":
            return "git version 2.47.1\n"
        if argv[1:] == ["--version"]:
            return "uv 0.13.1\n"
        return str(tmp_path / ("bin" if "--bin" in argv else "tools"))
    return binding, calls, run


@pytest.mark.parametrize("conflict", ["root", "tool", "entrypoint", "path", "owner", "binding", "override", "old_uv", "missing_git", "broken_git"])
def test_preflight_refuses_conflicts_without_root_mutation(support, tmp_path, monkeypatch, preflight_system, conflict):
    binding, calls, run = preflight_system
    root = tmp_path / "fresh root"
    probe = lambda: None
    if conflict == "root":
        root.mkdir()
        (root / "keep").write_text("user file")
    elif conflict == "tool":
        (tmp_path / "tools/contextopus-core").mkdir(parents=True)
    elif conflict == "entrypoint":
        path = support.tool_paths(tmp_path / "tools", tmp_path / "bin")["entrypoint"]
        path.parent.mkdir()
        path.write_text("existing")
    elif conflict == "path":
        monkeypatch.setattr(support.shutil, "which", lambda name: {"uv": "/tools/uv", "git": "/tools/git", "contextopus": "/other/contextopus"}.get(name))
    elif conflict == "owner":
        probe = lambda: {"root": str(tmp_path / "unrelated root"), "pid": 5}
    elif conflict == "binding":
        other = tmp_path / "existing memory"
        other.mkdir()
        binding.parent.mkdir()
        binding.write_text(json.dumps({"root": str(other)}))
    elif conflict == "override":
        monkeypatch.setenv("CONTEXTOPUS_ROOT", str(tmp_path / "elsewhere"))
    elif conflict == "old_uv":
        run = lambda argv, **kw: "git version 2.47.1" if argv[0] == "/tools/git" else "uv 0.12.0"
    elif conflict == "missing_git":
        monkeypatch.setattr(support.shutil, "which", lambda name: "/tools/uv" if name == "uv" else None)
    elif conflict == "broken_git":
        run = lambda *a, **kw: "not a working Git executable"
    with pytest.raises(support.InstallError):
        support.preflight(root, run, probe)
    assert not root.exists() or conflict == "root"
    assert not any("install" in call or "--set" in call for call in calls)


def test_occupied_non_mcp_port_is_not_treated_as_free(support, monkeypatch):
    class Connection:
        def close(self):
            pass
    class Opener:
        def open(self, *a, **kw):
            raise OSError("unrelated HTTP listener")
    monkeypatch.setattr(support.socket, "create_connection", lambda *a, **kw: Connection())
    monkeypatch.setattr(support.urllib.request, "build_opener", lambda *a: Opener())
    with pytest.raises(support.InstallError, match="occupied"):
        support.health()


def test_json_streams_preserve_false_null_and_lists_and_reject_noise(support):
    assert support.json_documents(' {"applied": false}\n {"status":"failed"}\n [] null false') == [
        {"applied": False}, {"status": "failed"}, [], None, False]
    for value in ("", "warning\n{}", "{}\ntrailing noise"):
        with pytest.raises(support.InstallError):
            support.json_documents(value)


def test_client_selection_and_platform_defaults(installer_module, support, tmp_path):
    assert installer_module.selected_clients(["codex", "hermes", "codex"]) == ["codex", "hermes"]
    with pytest.raises(support.InstallError):
        installer_module.selected_clients(["none", "codex"])
    assert support.default_root(platform="darwin", home=tmp_path, environment={}) == tmp_path / "Library/Application Support/Contextopus"
    assert support.default_root(platform="win32", home=tmp_path, environment={}) == tmp_path / "AppData/Local/Contextopus"
    assert support.default_root(platform="linux", home=tmp_path, environment={"XDG_DATA_HOME": str(tmp_path / "xdg")}) == tmp_path / "xdg/Contextopus"


def test_cancelled_interactive_confirmation_is_read_only(installer_module, tmp_path, monkeypatch):
    bundle, manifest = payload(tmp_path)
    monkeypatch.setattr(installer_module, "load_bundle", lambda root: manifest)
    monkeypatch.setattr(installer_module, "Installer", lambda *a, **kw: pytest.fail("declined installation ran"))
    root = tmp_path / "memory"
    assert installer_module.main(["--root", str(root), "--client", "none"], bundle_root=bundle, input_fn=lambda text: "n") == 0
    assert not root.exists()


def test_main_reports_partial_failure_with_receipt(installer_module, support, tmp_path, monkeypatch, capsys):
    installer, system = make_installer(installer_module, support, tmp_path)
    system.model_status = "failed"
    monkeypatch.setattr(installer_module, "load_bundle", lambda root: installer.manifest)
    monkeypatch.setattr(installer_module, "Installer", lambda *a, **kw: installer)
    assert installer_module.main(["--yes", "--root", str(installer.root)], bundle_root=installer.bundle_root) == 2
    captured = capsys.readouterr()
    assert "Partial installation retained" in captured.err
    assert "Automatic resume and rollback are not implemented" in captured.err
    assert "Installed: " not in captured.out


def test_data_root_inside_bundle_is_refused_before_mutation(installer_module, support, tmp_path):
    installer, system = make_installer(installer_module, support, tmp_path)
    installer.root = installer.bundle_root / "modules/alpha/package/nested data"
    with pytest.raises(support.InstallError, match="outside the extracted bundle"):
        installer.apply()
    assert not installer.root.exists() and not system.calls


def test_python_loader_environment_is_not_inherited(support, monkeypatch):
    import io
    monkeypatch.setenv("PYTHONPATH", "/wrong/source")
    monkeypatch.setenv("PYTHONHOME", "/wrong/python")
    monkeypatch.setenv("HOME", "/keep/user/home")
    seen = []
    class Process:
        returncode = 0
        def __init__(self, argv, **kwargs):
            seen.append(kwargs)
            self.stdout, self.stderr = io.BytesIO(b"result"), io.BytesIO(b"")
        def wait(self, **kwargs):
            return 0
    monkeypatch.setattr(support.subprocess, "Popen", Process)
    assert support.command(["/tool path/contextopus", "--version"]) == "result"
    assert "PYTHONPATH" not in seen[0]["env"] and "PYTHONHOME" not in seen[0]["env"]
    assert seen[0]["env"]["HOME"] == "/keep/user/home"


def test_changed_default_binding_is_preserved_at_final_step(installer_module, support, tmp_path):
    installer, system = make_installer(installer_module, support, tmp_path)
    integrate = installer.client
    def changed_binding(client):
        integrate(client)
        system.paths["binding_path"].write_text('{"root":"/another/root"}')
    installer.client = changed_binding
    with pytest.raises(support.InstallError, match="binding changed"):
        installer.apply()
    assert system.paths["binding_path"].read_text() == '{"root":"/another/root"}'
    assert installer.receipt["failed_step"] == "bind_default_root"


def test_command_streams_stderr_before_exit_and_keeps_json_stdout(support, monkeypatch):
    import io
    import threading
    progress = threading.Event()
    class Sink(io.StringIO):
        def write(self, value):
            result = super().write(value)
            if "download progress" in self.getvalue():
                progress.set()
            return result
    sink = Sink()
    monkeypatch.setattr(support.sys, "stderr", sink)
    returned = []
    script = "import sys,time;sys.stderr.write('download progress\\r');sys.stderr.flush();time.sleep(.3);print('{\"status\":\"ok\"}')"
    worker = threading.Thread(target=lambda: returned.append(support.command([sys.executable, "-c", script], timeout=5)))
    worker.start()
    assert progress.wait(3), "Progress was buffered until command completion"
    assert worker.is_alive()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert json.loads(returned[0]) == {"status": "ok"}
    assert "download progress" not in returned[0]


def test_command_preserves_stderr_diagnostic_on_failure(support, capsys):
    with pytest.raises(support.InstallError, match="deliberate download failure"):
        support.command([sys.executable, "-c", "import sys;sys.stderr.write('deliberate download failure');sys.exit(3)"], timeout=5)
    assert "deliberate download failure" in capsys.readouterr().err


@pytest.mark.parametrize('selection, expected', [(['none'], []), (['alpha'], ['alpha']), (['alpha', 'beta'], ['alpha', 'beta'])])
def test_module_subset_plan_and_apply(installer_module, support, tmp_path, selection, expected):
    installer, system = make_installer(installer_module, support, tmp_path, modules=selection, skip_model=True)
    plan = installer_module.make_plan(installer.bundle_root, installer.manifest, installer.options)
    assert [item['id'] for item in plan['modules']] == expected
    receipt = installer.apply()
    assert receipt['status'] == 'installed'
    assert sorted(path.name for path in (installer.root / 'modules').iterdir()) == expected
    assert [call[-1] for call in system.calls if call[3:5] == ['modules', 'install']] == expected


@pytest.mark.parametrize('selection', [['missing'], ['none', 'alpha']])
def test_invalid_module_selection_is_read_only(installer_module, tmp_path, monkeypatch, selection):
    bundle, manifest = payload(tmp_path)
    monkeypatch.setattr(installer_module, 'load_bundle', lambda root: manifest)
    root = tmp_path / 'untouched'
    argv = ['--yes', '--root', str(root)]
    for name in selection:
        argv.extend(['--module', name])
    assert installer_module.main(argv, bundle_root=bundle) == 2
    assert not root.exists()


def test_core_only_preflight_needs_no_git(support, tmp_path, monkeypatch, preflight_system):
    binding, calls, run = preflight_system
    monkeypatch.setattr(support.shutil, 'which', lambda name: '/tools/uv' if name == 'uv' else None)
    support.preflight(tmp_path / 'core only', run, lambda: None, require_git=False)
    assert not any(call[0].endswith('/git') for call in calls)

import json
from pathlib import Path
import pytest
from contextopus.integrations import IntegrationConflict, integrate, plan


@pytest.mark.parametrize(
    "client,config,section",
    [
        ("codex", ".codex/config.toml", "mcp_servers"),
        ("claude-code", ".mcp.json", "mcpServers"),
        ("opencode", "opencode.json", "mcp"),
        ("crush", "crush.json", "mcp"),
    ],
)
def test_merge_idempotence_preserves_existing(tmp_path, client, config, section):
    path = tmp_path / config
    path.parent.mkdir(parents=True, exist_ok=True)
    if client == "codex":
        path.write_text(
            '# keep comment\nmodel = "other"\n[mcp_servers.other]\ncommand = "untouched"\n'
        )
    else:
        path.write_text(
            json.dumps(
                {"unrelated": "keep", section: {"other": {"url": "http://other"}}}
            )
        )
    integrate(plan(client, tmp_path))
    text = path.read_text()
    assert "other" in text and "keep" in text
    assert "127.0.0.1:8765/mcp" in text
    assert not integrate(plan(client, tmp_path))["written"]




def test_stale_preview_does_not_partially_write(tmp_path):
    preview = plan("claude-code", tmp_path)
    (tmp_path / ".mcp.json").write_text('{"changed": true}')
    with pytest.raises(IntegrationConflict, match="changed"):
        integrate(preview)
    assert not (tmp_path / ".claude/skills").exists()


def test_jsonc_preserved(tmp_path):
    (tmp_path / "opencode.jsonc").write_text("// keep\n{}")
    with pytest.raises(IntegrationConflict, match="JSONC"):
        plan("opencode", tmp_path)
    assert not (tmp_path / "opencode.json").exists()








@pytest.mark.parametrize("command", ["status", "doctor"])
def test_offline_observation_does_not_start_or_create(
    tmp_path, monkeypatch, capsys, command
):
    from contextopus.interfaces.cli.main import main
    from contextopus.integrations import service

    root = tmp_path / "absent"
    monkeypatch.setattr(service, "status", lambda root: {"state": "stopped"})
    monkeypatch.setattr(
        service, "start", lambda root: pytest.fail("observation started a service")
    )
    assert main(["--root", str(root), command]) == 0
    assert json.loads(capsys.readouterr().out)["root_exists"] is False
    assert not root.exists()


def test_user_scope_and_existing_plain_jsonc_are_merged(tmp_path, monkeypatch):
    config_base = tmp_path / "native-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_base))
    monkeypatch.setenv("LOCALAPPDATA", str(config_base))
    config = config_base / "opencode/opencode.jsonc"
    config.parent.mkdir(parents=True)
    config.write_text('{"unrelated":"keep"}')
    integrate(plan("opencode", tmp_path, scope="user", install_skills=False))
    saved = json.loads(config.read_text())
    assert saved["unrelated"] == "keep"
    assert saved["mcp"]["contextopus"]["type"] == "remote"
    assert not (config_base / "opencode/skills").exists()




def test_codex_native_cutover_preserves_old_cache_and_avoids_duplicate_mcp(tmp_path):
    from importlib.metadata import version

    release = version("contextopus-core")
    new = (
        tmp_path
        / f".codex/plugins/cache/contextopus/contextopus/{release}/.codex-plugin/plugin.json"
    )
    new.parent.mkdir(parents=True)
    new.write_text(json.dumps({"name": "contextopus", "version": release}))
    old = (
        tmp_path
        / ".codex/plugins/cache/persistent-context-workspace/persistent-context-workspace/0.14.0/keep"
    )
    old.parent.mkdir(parents=True)
    old.write_text("active old session cache")
    config = tmp_path / ".codex/config.toml"
    config.write_text(
        '[plugins."persistent-context-workspace@persistent-context-workspace"]\nenabled=true\n[marketplaces.persistent-context-workspace]\nsource="old-path"\n[mcp_servers.contextopus]\nurl="http://127.0.0.1:8765/mcp"\n'
    )
    integrate(plan("codex", tmp_path, scope="user", native_plugin=True))
    import tomllib

    value = tomllib.loads(config.read_text())
    assert value["plugins"]["contextopus@contextopus"]["enabled"] is True
    assert (
        value["plugins"]["persistent-context-workspace@persistent-context-workspace"][
            "enabled"
        ]
        is False
    )
    assert "contextopus" not in value.get("mcp_servers", {})
    assert old.read_text() == "active old session cache"
    assert not (tmp_path / ".agents/skills").exists()


def test_explicit_default_root_binding_is_persistent_without_data_creation(
    tmp_path, monkeypatch, capsys
):
    from contextopus.interfaces.cli import main as cli

    binding = tmp_path / "config/root.json"
    monkeypatch.setattr(cli, "root_binding_path", lambda: binding)
    monkeypatch.delenv("CONTEXTOPUS_ROOT", raising=False)
    target = tmp_path / "data"
    assert cli.main(["root", "--set", str(target)]) == 0
    capsys.readouterr()
    assert cli.default_root() == target
    assert not target.exists()
    monkeypatch.setenv("CONTEXTOPUS_ROOT", str(tmp_path / "override"))
    assert cli.default_root() == tmp_path / "override"


def test_service_records_actual_owner_pid_after_venv_redirector(tmp_path, monkeypatch):
    from contextopus.integrations import service
    from types import SimpleNamespace

    states = iter(
        [{"state": "stopped"}, {"state": "running", "root": str(tmp_path), "pid": 111}]
    )
    monkeypatch.setattr(service, "status", lambda root: next(states))
    monkeypatch.setattr(
        service.subprocess,
        "Popen",
        lambda *a, **kw: SimpleNamespace(pid=999, poll=lambda: None),
    )
    assert service.start(tmp_path)["pid"] == 111
    assert json.loads((tmp_path / "runtime/service.json").read_text())["pid"] == 111
    monkeypatch.setattr(
        service,
        "status",
        lambda root: {"state": "running", "root": str(tmp_path), "pid": 111} if not signalled else {"state": "stopped"},
    )
    signalled = []
    monkeypatch.setattr(service.os, "kill", lambda pid, signal: signalled.append(pid))
    assert service.stop(tmp_path)["state"] == "stopped"
    assert signalled == [111]


def test_cli_relocation_applies_bounded_durable_revision(tmp_path, monkeypatch, capsys):
    from contextopus.interfaces.cli.main import main
    from contextopus.integrations import remote

    calls = []

    class App:
        def query(self, operation, arguments):
            assert operation == "core.relocation_plan"
            return {
                "revision": "durable-revision",
                "files_count": 20926,
                "manifest_sha256": "known",
            }

        def execute(self, operation, arguments):
            calls.append((operation, arguments))
            return {"status": "complete"}

        def close(self):
            pass

    monkeypatch.setattr(remote, "RemoteApplication", lambda *args, **kwargs: App())
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "relocation",
                str(tmp_path / "destination"),
                "--apply",
            ]
        )
        == 0
    )
    assert calls == [("core.relocation_apply", {"plan_revision": "durable-revision"})]


def test_codex_plugin_effective_manifest_wires_native_mcp():
    import json
    from pathlib import Path

    plugin = Path(__file__).resolve().parents[1] / "plugins/contextopus"
    portable = json.loads((plugin / "plugin.json").read_text(encoding="utf-8"))
    overlay = portable["extensions"]["com.openai"]
    compatibility = json.loads(
        (plugin / ".codex-plugin/plugin.json").read_text(encoding="utf-8")
    )
    assert overlay["mcpServers"] == compatibility["mcpServers"] == "./.mcp.json"
    native = json.loads((plugin / overlay["mcpServers"]).read_text(encoding="utf-8"))
    servers = native["mcpServers"]
    assert set(servers) == {"contextopus"}
    assert servers["contextopus"]["url"] == "http://127.0.0.1:8765/mcp"
    agent_plugin = json.loads((plugin / "mcp.json").read_text(encoding="utf-8"))
    assert agent_plugin["mcpServers"]["contextopus"]["type"] == "streamable-http"
    assert (
        agent_plugin["mcpServers"]["contextopus"]["url"]
        == servers["contextopus"]["url"]
    )

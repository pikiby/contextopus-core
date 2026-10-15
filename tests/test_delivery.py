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


def test_collision_is_not_overwritten(tmp_path):
    skill = tmp_path / ".agents/skills/w/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("my unrelated skill")
    with pytest.raises(IntegrationConflict, match="collision"):
        plan("codex", tmp_path)
    assert skill.read_text() == "my unrelated skill"
    assert not (tmp_path / ".codex/config.toml").exists()


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


def test_canonical_resources_available_without_model(tmp_path):
    from contextopus.startup import Application

    with Application(tmp_path, discover=False) as app:
        content = app.query("procedure", {"name": "workspace"})["content"]
        assert "allow_implicit_updates" in content
        assert app.query("procedure", {"name": "instructions"})["content"]
        assert not app.resources.providers._entries
        with pytest.raises(ValueError):
            app.query("procedure", {"name": "../outside"})


def test_owned_skill_upgrade_preserves_user_edits(tmp_path):
    import hashlib

    preview = plan("codex", tmp_path)
    integrate(preview)
    skill = tmp_path / ".agents/skills/w/SKILL.md"
    manifest = tmp_path / ".contextopus/codex-integration.json"
    saved = json.loads(manifest.read_text())
    # Simulate an older, unmodified installation recorded by the installer.
    skill.write_text("older generated version")
    saved["skills"][".agents/skills/w/SKILL.md"] = hashlib.sha256(
        skill.read_bytes()
    ).hexdigest()
    manifest.write_text(json.dumps(saved))
    integrate(plan("codex", tmp_path))
    assert skill.read_text() != "older generated version"
    skill.write_text("user edited installed skill")
    with pytest.raises(IntegrationConflict, match="collision"):
        plan("codex", tmp_path)


def test_http_remote_facade_shared_owner(tmp_path):
    import os
    import socket
    import subprocess
    import sys
    import time
    import urllib.request
    from contextopus.integrations.remote import RemoteApplication

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    code = "from contextopus.interfaces.mcp.server import run; import sys; run(sys.argv[1],port=int(sys.argv[2]))"
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    with (tmp_path / "server.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", code, str(tmp_path / "data"), str(port)],
            stdout=log,
            stderr=log,
            env=env,
        )
        first = second = None
        try:
            for _ in range(100):
                if process.poll() is not None:
                    pytest.fail((tmp_path / "server.log").read_text())
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/health", timeout=0.2
                    ) as response:
                        health = json.loads(response.read())
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                pytest.fail("HTTP MCP server did not start")
            assert health["pid"] == process.pid
            first = RemoteApplication(
                tmp_path / "data", endpoint=f"http://127.0.0.1:{port}/mcp"
            )
            second = RemoteApplication(
                tmp_path / "data", endpoint=f"http://127.0.0.1:{port}/mcp"
            )
            assert first.query("core.doctor")["model_loaded"] is False
            preview = first.services.preview_settings({"searchN": 7})
            second.services.apply_settings(preview["preview_revision"])
            assert first.services.settings()["values"]["searchN"] == 7
            assert (
                second.query("procedure", {"name": "workspace"})["name"] == "workspace"
            )
        finally:
            if first:
                first.close()
            if second:
                second.close()
            process.terminate()
            process.wait(timeout=10)


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


def test_user_scope_and_existing_plain_jsonc_are_merged(tmp_path):
    config = tmp_path / ".config/opencode/opencode.jsonc"
    config.parent.mkdir(parents=True)
    config.write_text('{"unrelated":"keep"}')
    integrate(plan("opencode", tmp_path, scope="user", install_skills=False))
    saved = json.loads(config.read_text())
    assert saved["unrelated"] == "keep"
    assert saved["mcp"]["contextopus"]["type"] == "remote"
    assert not (tmp_path / ".config/opencode/skills").exists()


def test_known_legacy_skill_upgrade_and_modified_collision(tmp_path):
    import hashlib
    from importlib.resources import files

    old = tmp_path / ".claude/skills/pcw/SKILL.md"
    old.parent.mkdir(parents=True)
    # The fixture uses the exact retained pre-transition packaged entrypoint.
    source = (
        Path(__file__).resolve().parents[1]
        / "plugins/persistent-context-workspace/skills/pcw/SKILL.md"
    )
    old.write_bytes(source.read_bytes())
    integrate(
        plan("claude-code", tmp_path, scope="user", legacy_skills=old.parent.parent)
    )
    assert "Compatibility alias" in old.read_text()
    assert "contextopus_query" in old.read_text()
    old.write_text("user customized old skill")
    with pytest.raises(IntegrationConflict, match="User-modified"):
        plan("claude-code", tmp_path, scope="user", legacy_skills=old.parent.parent)
    cache = tmp_path / ".codex/plugins/cache/old/old/0.14.0/skills"
    with pytest.raises(IntegrationConflict, match="caches"):
        plan("codex", tmp_path, legacy_skills=cache)


def test_codex_native_cutover_preserves_old_cache_and_avoids_duplicate_mcp(tmp_path):
    new = (
        tmp_path
        / ".codex/plugins/cache/contextopus/contextopus/1.0.0/.codex-plugin/plugin.json"
    )
    new.parent.mkdir(parents=True)
    new.write_text('{"name":"contextopus","version":"1.0.0"}')
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

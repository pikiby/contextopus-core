"""Native Hermes home/profile integration through the shared Contextopus MCP."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from contextopus.integrations import IntegrationConflict, integrate, plan


@pytest.fixture(autouse=True)
def isolated_hermes_environment(monkeypatch):
    from contextopus.integrations import hermes

    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.delenv("HERMES_DATA_DIR_SUFFIX", raising=False)
    monkeypatch.setattr(hermes, "sys", SimpleNamespace(platform="linux"))


def test_native_home_preserves_yaml_and_custom_skills_and_is_idempotent(tmp_path):
    home = tmp_path / ".hermes"
    home.mkdir()
    config = home / "config.yaml"
    original = '# keep my settings\nmodel: "custom-model" # model comment\nmcp_servers:\n  other:\n    url: "https://other/mcp" # keep URL\n    headers:\n      Authorization: "Bearer private-value"\nagent:\n  max_turns: 17\n'
    config.write_text(original)
    custom = home / "skills/custom/SKILL.md"
    custom.parent.mkdir(parents=True)
    custom.write_text("my skill")

    preview = plan("hermes", tmp_path, scope="user")
    assert config.read_text() == original  # Preview has no writes.
    assert not (home / "skills/w").exists()
    integrate(preview)
    actual = config.read_text()
    assert actual.replace('  contextopus:\n    url: http://127.0.0.1:8765/mcp\n    tools:\n      resources: false\n      prompts: false\n', "") == original
    assert yaml.safe_load(actual)["mcp_servers"]["contextopus"] == {
        "url": "http://127.0.0.1:8765/mcp", "tools": {"resources": False, "prompts": False},
    }
    assert custom.read_text() == "my skill"
    assert {path.parent.name for path in (home / "skills").glob("*/SKILL.md")} == {
        "custom", "m", "w", "w-analyze", "w-context", "w-create", "w-search", "w-settings",
    }
    assert not integrate(plan("hermes", tmp_path, scope="user"))["written"]


@pytest.mark.parametrize("original", [
    "", "# config comment\n", "{}\n", "{} # empty config\n", "mcp_servers: {} # empty servers\n",
    "---\nmodel: custom\n...\n", "model: custom", "model: custom\r\n",
    "  model: custom\n", "  mcp_servers: {}\n", "  {} # indented empty root\n",
    "model: custom\nmcp_servers:\n    other:\n      url: http://other\n",
])
def test_empty_and_block_yaml_forms(tmp_path, original):
    home = tmp_path / ".hermes"
    home.mkdir()
    config = home / "config.yaml"
    config.write_bytes(original.encode())
    integrate(plan("hermes", tmp_path, scope="user"))
    data = yaml.safe_load(config.read_bytes())
    assert data["mcp_servers"]["contextopus"] == {
        "url": "http://127.0.0.1:8765/mcp", "tools": {"resources": False, "prompts": False},
    }
    assert not integrate(plan("hermes", tmp_path, scope="user"))["written"]


@pytest.mark.parametrize("original", [
    "mcp_servers: [broken", "- not-a-mapping\n", "null\n",
    "mcp_servers: null\n", "mcp_servers: []\n",
    "model: first\nmodel: second\n", "mcp_servers:\n  other: {}\n  other: {}\n",
    "first: &shared {url: http://other}\nmcp_servers: *shared\n",
    "value: !!str custom\n", "nested:\n  <<: {key: value}\n",
    "{model: custom}\n", "mcp_servers: {other: {url: http://other}}\n",
    "---\nmodel: one\n---\nmodel: two\n", "? [complex, key]\n: value\n",
])
def test_malformed_or_unsupported_yaml_is_preserved_without_any_writes(tmp_path, original):
    home = tmp_path / ".hermes"
    home.mkdir()
    config = home / "config.yaml"
    config.write_text(original)
    with pytest.raises(IntegrationConflict):
        plan("hermes", tmp_path, scope="user")
    assert config.read_text() == original
    assert set(home.iterdir()) == {config}


def test_server_collision_preserved(tmp_path):
    home = tmp_path / ".hermes"
    home.mkdir()
    config = home / "config.yaml"
    content = "mcp_servers:\n  contextopus:\n    command: custom-server\n"
    config.write_text(content)
    with pytest.raises(IntegrationConflict, match="different definition"):
        plan("hermes", tmp_path, scope="user")
    assert config.read_text() == content
    assert not (home / "skills").exists()


def test_url_only_server_upgrades_without_rewriting_existing_yaml(tmp_path):
    home = tmp_path / ".hermes"
    home.mkdir()
    config = home / "config.yaml"
    original = 'model: custom # keep model\nmcp_servers:\n  contextopus: # keep server\n    url: "http://127.0.0.1:8765/mcp" # keep URL\n  other:\n    url: https://other/mcp\n'
    config.write_text(original)
    integrate(plan("hermes", tmp_path, scope="user"))
    actual = config.read_text()
    assert actual.replace("    tools:\n      resources: false\n      prompts: false\n", "") == original
    assert yaml.safe_load(actual)["mcp_servers"]["contextopus"]["tools"] == {"resources": False, "prompts": False}
    assert not integrate(plan("hermes", tmp_path, scope="user"))["written"]


@pytest.mark.parametrize("existing", [
    {"url": "http://127.0.0.1:8765/mcp", "tools": {"resources": True, "prompts": False}},
    {"url": "http://127.0.0.1:8765/mcp", "tools": {"resources": False}},
    {"url": "http://127.0.0.1:8765/mcp", "tools": {"include": ["guide"]}},
    {"url": "http://127.0.0.1:8765/mcp", "timeout": 90},
])
def test_custom_existing_server_tool_settings_remain_collisions(tmp_path, existing):
    home = tmp_path / ".hermes"
    home.mkdir()
    config = home / "config.yaml"
    original = yaml.safe_dump({"mcp_servers": {"contextopus": existing}})
    config.write_text(original)
    with pytest.raises(IntegrationConflict, match="different definition"):
        plan("hermes", tmp_path, scope="user")
    assert config.read_text() == original
    assert not (home / "skills").exists()


def test_managed_skill_upgrade_and_modified_collision(tmp_path):
    integrate(plan("hermes", tmp_path, scope="user"))
    home = tmp_path / ".hermes"
    target = home / "skills/w/SKILL.md"
    current = target.read_bytes()
    target.write_text("older managed skill")
    receipt = home / ".contextopus/hermes-integration.json"
    managed = json.loads(receipt.read_text())
    managed["skills"][".hermes/skills/w/SKILL.md"] = hashlib.sha256(target.read_bytes()).hexdigest()
    receipt.write_text(json.dumps(managed))
    integrate(plan("hermes", tmp_path, scope="user"))
    assert target.read_bytes() == current
    target.write_text("user modified installed skill")
    with pytest.raises(IntegrationConflict, match="collision"):
        plan("hermes", tmp_path, scope="user")
    assert target.read_text() == "user modified installed skill"


def test_custom_canonical_skill_collision_has_no_config_write(tmp_path):
    target = tmp_path / ".hermes/skills/w/SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("custom w skill")
    with pytest.raises(IntegrationConflict, match="collision"):
        plan("hermes", tmp_path, scope="user")
    assert not (tmp_path / ".hermes/config.yaml").exists()
    assert target.read_text() == "custom w skill"


@pytest.mark.parametrize("changed", ["config.yaml", "skills/w/SKILL.md", ".contextopus/hermes-integration.json"])
def test_stale_preview_checks_all_targets_before_writing(tmp_path, changed):
    preview = plan("hermes", tmp_path, scope="user")
    target = tmp_path / ".hermes" / changed
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("changed after preview")
    with pytest.raises(IntegrationConflict, match="changed after preview"):
        integrate(preview)
    assert target.read_text() == "changed after preview"
    assert not (tmp_path / ".hermes/skills/w-create/SKILL.md").exists()


def test_environment_home_and_explicit_profile_keep_separate_receipts(tmp_path, monkeypatch):
    environment_home = tmp_path / "hermes-data"
    profile_home = environment_home / "profiles/research"
    monkeypatch.setenv("HERMES_HOME", str(environment_home))
    integrate(plan("hermes", tmp_path / "user", scope="user"))
    integrate(plan("hermes", tmp_path / "user", scope="user", hermes_home=profile_home))
    for home in (environment_home, profile_home):
        assert (home / "config.yaml").is_file()
        assert (home / "skills/w/SKILL.md").is_file()
        assert (home / ".contextopus/hermes-integration.json").is_file()
    assert not integrate(plan("hermes", tmp_path / "user", scope="user"))["written"]
    assert not integrate(plan("hermes", tmp_path / "user", scope="user", hermes_home=profile_home))["written"]


def test_config_only_installs_no_skills_and_endpoint_is_explicit(tmp_path):
    integrate(plan("hermes", tmp_path, scope="user", install_skills=False, endpoint="http://127.0.0.1:9234/mcp"))
    home = tmp_path / ".hermes"
    assert not (home / "skills").exists()
    assert yaml.safe_load((home / "config.yaml").read_text())["mcp_servers"]["contextopus"]["url"] == "http://127.0.0.1:9234/mcp"


def test_native_windows_home_defaults_and_environment_overrides(tmp_path, monkeypatch):
    from contextopus.integrations import hermes

    monkeypatch.setattr(hermes, "sys", SimpleNamespace(platform="win32"))
    appdata = tmp_path / "native-appdata"
    monkeypatch.setenv("LOCALAPPDATA", str(appdata))
    monkeypatch.setenv("HERMES_DATA_DIR_SUFFIX", "-test")
    assert hermes.resolve_home(tmp_path) == appdata / "hermes-test"
    integrate(plan("hermes", tmp_path, scope="user", install_skills=False))
    assert (appdata / "hermes-test/config.yaml").is_file()
    monkeypatch.delenv("LOCALAPPDATA")
    assert hermes.resolve_home(tmp_path) == tmp_path / "AppData/Local/hermes-test"
    monkeypatch.setenv("HERMES_HOME", "  $NATIVE_HERMES_TEST_HOME  ")
    monkeypatch.setenv("NATIVE_HERMES_TEST_HOME", str(tmp_path / "custom-home"))
    assert hermes.resolve_home(tmp_path) == tmp_path / "custom-home"
    assert hermes.resolve_home(tmp_path, tmp_path / "explicit") == tmp_path / "explicit"
    monkeypatch.setenv("HERMES_HOME", "  ")
    assert hermes.resolve_home(tmp_path) == tmp_path / "AppData/Local/hermes-test"


def test_unsupported_scope_and_options_have_no_side_effects(tmp_path):
    with pytest.raises(ValueError, match="user scope"):
        plan("hermes", tmp_path)
    with pytest.raises(ValueError, match="only to Hermes"):
        plan("codex", tmp_path, hermes_home=tmp_path / "hermes")
    with pytest.raises(ValueError, match="only to Codex"):
        plan("hermes", tmp_path, scope="user", native_plugin=True)
    assert not list(tmp_path.iterdir())


def test_cli_preview_and_apply_redact_other_server_credentials(tmp_path, monkeypatch, capsys):
    from contextopus.interfaces.cli.main import main, parser

    home = tmp_path / "profiles/research"
    home.mkdir(parents=True)
    config = home / "config.yaml"
    content = "mcp_servers:\n  other:\n    url: http://other\n    headers:\n      Authorization: private-value\n"
    config.write_text(content)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    args = ["--root", str(tmp_path / "core"), "integrate", "hermes", "--user", "--hermes-home", str(home)]
    assert main(args) == 0
    output = capsys.readouterr().out
    report = json.loads(output)
    assert str(config) in {item["path"] for item in report["files"]}
    assert "private-value" not in output
    assert config.read_text() == content
    assert main(args + ["--apply"]) == 0
    assert "private-value" not in capsys.readouterr().out
    assert (home / "skills/w/SKILL.md").exists()
    with pytest.raises(SystemExit):
        parser().parse_args(["reconnect", "hermes"])

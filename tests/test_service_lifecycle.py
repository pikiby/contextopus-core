import errno
import json
import plistlib
from pathlib import Path
from unittest.mock import patch
import urllib.error
import xml.etree.ElementTree as ET

import pytest

from contextopus.integrations import autostart, service
from contextopus.integrations.native import plan, integrate, IntegrationConflict, _digest
from contextopus.interfaces.tui.backend import Backend
from contextopus.interfaces.tui.render import action_names


def test_native_service_definitions_use_foreground_owner_and_native_restart(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    root = tmp_path / "Memory with spaces"
    linux = autostart.definition(root, home=tmp_path, platform="linux", executable="/some python/bin/python")
    assert "Restart=on-failure" in linux["content"]
    assert '"/some python/bin/python"' in linux["content"]
    assert '"mcp"' in linux["content"] and "service start" not in linux["content"]
    mac = plistlib.loads(autostart.definition(root, home=tmp_path, platform="darwin")["content"].encode())
    assert mac["ProgramArguments"][-1] == "mcp" and mac["KeepAlive"]["SuccessfulExit"] is False
    windows = ET.fromstring(autostart.definition(root, home=tmp_path, platform="win32")["content"])
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    assert windows.find("t:Settings/t:MultipleInstancesPolicy", ns).text == "IgnoreNew"
    assert windows.find("t:Settings/t:RestartOnFailure/t:Count", ns).text == "999"
    assert windows.find("t:Principals/t:Principal/t:LogonType", ns).text == "InteractiveToken"


@pytest.mark.parametrize("code, expected", [(errno.EPERM, "access_denied"), (errno.EACCES, "access_denied"), (errno.ECONNREFUSED, "stopped"), (errno.ETIMEDOUT, "unreachable")])
def test_status_distinguishes_connection_failures(tmp_path, code, expected):
    with patch.object(service.urllib.request, "urlopen", side_effect=urllib.error.URLError(OSError(code, "test"))):
        assert service.status(tmp_path)["state"] == expected


def test_native_start_does_not_spawn_an_extra_owner(tmp_path):
    with patch.object(service, "status", side_effect=[{"state": "stopped"}, {"state": "running", "root": str(tmp_path), "pid": 123}]), patch.object(autostart, "control", return_value=True) as native, patch.object(service.subprocess, "Popen") as spawn:
        assert service.start(tmp_path)["state"] == "running"
        native.assert_called_once_with(tmp_path, "start")
        spawn.assert_not_called()


@pytest.mark.asyncio
async def test_tui_can_start_stopped_service_without_mcp_call(tmp_path):
    class Offline:
        endpoint = "http://127.0.0.1:8765/mcp"
        root = str(tmp_path)
        def query(self, *args):
            raise AssertionError("Cannot query a stopped MCP")
    backend = Backend(Offline())
    with patch.object(service, "status", return_value={"state": "stopped"}), patch.object(service, "start", return_value={"state": "running"}) as start:
        snapshot = await backend.snapshot()
        assert "Start MCP" in action_names(snapshot["status"])
        assert (await backend.service("start"))["state"] == "running"
        start.assert_called_once_with(str(tmp_path))


def test_upgrade_removes_only_managed_retired_skills_and_rejects_stale_plan(tmp_path):
    root = tmp_path / ".agents/skills"
    old = root / "ws/SKILL.md"
    old.parent.mkdir(parents=True)
    old.write_text("Old managed search")
    modified = root / "wr/SKILL.md"
    modified.parent.mkdir()
    modified.write_text("My custom rework")
    metadata = tmp_path / ".contextopus/codex-integration.json"
    metadata.parent.mkdir()
    metadata.write_text(json.dumps({"skills": {str(old.relative_to(tmp_path)): _digest(old.read_bytes())}}))
    preview = plan("codex", tmp_path)
    assert preview["removals"] == [{"path": str(old), "expected": _digest(old.read_bytes())}]
    assert preview["preserved"][0]["path"] == str(modified)
    old.write_text("Changed since preview")
    with pytest.raises(IntegrationConflict):
        integrate(preview)
    assert not (tmp_path / ".codex/config.toml").exists()
    old.write_text("Old managed search")
    result = integrate(preview)
    assert not old.exists() and modified.read_text() == "My custom rework"
    assert set(path.name for path in root.iterdir()) == {"w", "w-search", "w-create", "w-settings", "w-find", "w-analyze", "wr"}
    assert result["removed"] == [str(old)]

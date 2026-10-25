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

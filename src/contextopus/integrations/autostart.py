"""Native per-user service definitions. No shell and no elevated system service."""

from __future__ import annotations
import getpass
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import xml.etree.ElementTree as ET

LABEL = "org.contextopus.mcp"
UNIT = "contextopus.service"
TASK = "Contextopus MCP"


def definition(root, *, platform=None, home=None, executable=None):
    platform, home = platform or sys.platform, Path(home or Path.home())
    executable = executable or sys.executable
    root = Path(root).resolve()
    argv = [executable, "-m", "contextopus.interfaces.cli", "--root", str(root), "mcp"]
    if platform.startswith("linux"):
        def quote(value):
            return json.dumps(value, ensure_ascii=False).replace("%", "%%").replace("$", "$$")
        content = ("# Managed by Contextopus\n[Unit]\nDescription=Contextopus central MCP\n"
                   "StartLimitIntervalSec=0\n[Service]\nType=simple\nExecStart="
                   + " ".join(map(quote, argv))
                   + "\nRestart=on-failure\nRestartSec=3\nTimeoutStopSec=30\n"
                     "[Install]\nWantedBy=default.target\n")
        config = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config")))
        path, manager = config / "systemd/user" / UNIT, "systemd"
    elif platform == "darwin":
        content = plistlib.dumps({"Label": LABEL, "ProgramArguments": argv,
                                 "RunAtLoad": True, "KeepAlive": {"SuccessfulExit": False},
                                 "ThrottleInterval": 3,
                                 "StandardOutPath": str(root / "runtime/service.log"),
                                 "StandardErrorPath": str(root / "runtime/service.log")}).decode()
        path, manager = home / "Library/LaunchAgents" / (LABEL + ".plist"), "launchd"
    elif platform == "win32":
        account = os.environ.get("USERDOMAIN", "")
        account = (account + "\\" if account else "") + getpass.getuser()
        task = ET.Element("Task", {"version": "1.2", "xmlns": "http://schemas.microsoft.com/windows/2004/02/mit/task"})
        def child(parent, name, value=None, **attrs):
            node = ET.SubElement(parent, name, attrs)
            node.text = value
            return node
        child(child(task, "RegistrationInfo"), "Description", "Managed by Contextopus")
        trigger = child(child(task, "Triggers"), "LogonTrigger")
        child(trigger, "UserId", account)
        principal = child(child(task, "Principals"), "Principal", id="Author")
        child(principal, "UserId", account)
        child(principal, "LogonType", "InteractiveToken")
        child(principal, "RunLevel", "LeastPrivilege")
        settings = child(task, "Settings")
        for name, value in {"MultipleInstancesPolicy": "IgnoreNew", "DisallowStartIfOnBatteries": "false",
                            "StopIfGoingOnBatteries": "false", "StartWhenAvailable": "true",
                            "ExecutionTimeLimit": "PT0S"}.items():
            child(settings, name, value)
        restart = child(settings, "RestartOnFailure")
        child(restart, "Interval", "PT1M")
        child(restart, "Count", "999")
        action = child(child(task, "Actions", Context="Author"), "Exec")
        child(action, "Command", executable)
        child(action, "Arguments", subprocess.list2cmdline(argv[1:]))
        content = ET.tostring(task, encoding="unicode")
        path, manager = root / "runtime/contextopus-task.xml", "task-scheduler"
    else:
        raise ValueError(f"No native service adapter for {platform}")
    return {"manager": manager, "path": str(path), "content": content, "root": str(root)}


def run(argv, *, check=True):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"Service command failed: {argv[0]}")
    return result


def record(root):
    path = Path(root) / "runtime/autostart.json"
    return json.loads(path.read_text()) if path.is_file() else None


def install(root):
    from . import service
    plan = definition(root)
    path = Path(plan["path"])
    prior = record(root)
    if path.exists() and (not prior or prior.get("path") != str(path)) and path.read_text() != plan["content"]:
        raise RuntimeError(f"Unmanaged service definition already exists: {path}")
    manager = plan["manager"]
    # Check native manager availability before stopping the current manual owner.
    if manager == "systemd":
        run(["systemctl", "--user", "show-environment"])
    elif manager == "launchd":
        run(["launchctl", "print", f"gui/{os.getuid()}"])
    else:
        existing = run(["schtasks", "/Query", "/TN", TASK, "/XML"], check=False)
        if existing.returncode == 0 and "Managed by Contextopus" not in existing.stdout:
            raise RuntimeError("An unmanaged scheduled task uses the Contextopus name")
    state = service.status(root)
    if state["state"] not in {"running", "stopped"}:
        raise RuntimeError(f"Cannot manage service while connection state is {state['state']}")
    if state["state"] == "running":
        service.stop(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan["content"], encoding="utf-8")
    (Path(root) / "runtime").mkdir(parents=True, exist_ok=True)
    if manager == "systemd":
        run(["systemctl", "--user", "daemon-reload"])
        run(["systemctl", "--user", "enable", UNIT])
    elif manager == "task-scheduler":
        run(["schtasks", "/Create", "/TN", TASK, "/XML", str(path), "/F"])
    (Path(root) / "runtime/autostart.json").write_text(json.dumps({k: v for k, v in plan.items() if k != "content"}))
    return service.start(root)


def control(root, action):
    info = record(root)
    if info is None:
        return False
    manager = info["manager"]
    if manager == "systemd":
        run(["systemctl", "--user", action, UNIT])
    elif manager == "launchd":
        domain = f"gui/{os.getuid()}"
        label = f"{domain}/{LABEL}"
        if action == "stop":
            run(["launchctl", "bootout", label])
        elif action == "start":
            if run(["launchctl", "print", label], check=False).returncode:
                run(["launchctl", "bootstrap", domain, info["path"]])
            else:
                run(["launchctl", "kickstart", label])
        else:
            run(["launchctl", "kickstart", "-k", label])
    elif manager == "task-scheduler":
        if action in {"stop", "restart"}:
            run(["schtasks", "/End", "/TN", TASK])
        if action in {"start", "restart"}:
            run(["schtasks", "/Run", "/TN", TASK])
    else:
        raise ValueError(f"Unknown service manager: {manager}")
    return True

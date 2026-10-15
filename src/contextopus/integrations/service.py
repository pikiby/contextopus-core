"""Lifecycle for the single local MCP owner; all clients connect over loopback."""

from __future__ import annotations
import json
import errno
import urllib.error
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request


def status(root):
    from contextopus.core.storage import StorageLayout

    root = StorageLayout.resolve(root).root
    record = Path(root) / "runtime" / "service.json"
    value = json.loads(record.read_text()) if record.exists() else {}
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:8765/health", timeout=1
        ) as response:
            live = json.loads(response.read())
        return {"state": "running", "endpoint": "http://127.0.0.1:8765/mcp", **live}
    except (OSError, ValueError) as exc:
        reason = getattr(exc, "reason", exc)
        code = getattr(reason, "errno", None)
        state = "access_denied" if code in {errno.EACCES, errno.EPERM} else "stopped" if code == errno.ECONNREFUSED else "unreachable"
        return {"state": state, "recorded_pid": value.get("pid"), "error": str(exc)}


def _wait(root, desired, old_pid=None):
    for _ in range(100):
        current = status(root)
        if current["state"] == desired and (desired != "running" or current.get("pid") != old_pid):
            if desired == "running" and current.get("root") != str(Path(root).resolve()):
                raise RuntimeError("The local service owns another root")
            return current
        time.sleep(0.1)
    raise RuntimeError(f"Service did not become {desired}; inspect native service logs")


def _start_unlocked(root):
    root = Path(root).resolve()
    current = status(root)
    if current["state"] == "running":
        if current.get("root") != str(root):
            raise RuntimeError("The local service already owns another root")
        return current
    if current["state"] != "stopped":
        raise RuntimeError(f"Cannot start: {current}")
    from .autostart import control
    if control(root, "start"):
        return _wait(root, "running")
    runtime = root / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    options = (
        {"start_new_session": True}
        if os.name != "nt"
        else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    )
    with (runtime / "service.log").open("ab") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "contextopus.interfaces.cli",
                "--root",
                str(root),
                "mcp",
            ],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            **options,
        )
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f"Service exited; inspect {runtime / 'service.log'}")
        current = status(root)
        if current["state"] == "running":
            if current.get("root") != str(root):
                raise RuntimeError("The service endpoint belongs to another root")
            # On Windows, a venv launcher can have a different PID from the
            # interpreter that actually owns the endpoint. Use health identity.
            (runtime / "service.json").write_text(
                json.dumps({"pid": current["pid"], "root": str(root)})
            )
            return current
        time.sleep(0.1)
    raise RuntimeError("Service startup timed out; inspect service.log")


def start(root):
    from contextopus.core.storage import StorageLayout

    layout = StorageLayout.resolve(root)
    with layout.guard():
        return _start_unlocked(layout.root)


def _stop_unlocked(root):
    from contextopus.core.storage import StorageLayout

    root = StorageLayout.resolve(root).root
    current = status(root)
    if current["state"] == "stopped":
        return current
    if current["state"] != "running":
        raise RuntimeError(f"Cannot stop: {current}")
    if current.get("root") != str(Path(root).resolve()) or not current.get("pid"):
        raise RuntimeError(
            "Service identity does not match selected root; refusing to stop"
        )
    from .autostart import control
    if control(root, "stop"):
        return _wait(root, "stopped")
    record = Path(root) / "runtime" / "service.json"
    saved = json.loads(record.read_text()) if record.exists() else {}
    if saved.get("pid") != current["pid"]:
        raise RuntimeError("Service ownership record does not match")
    os.kill(current["pid"], signal.SIGTERM)
    return _wait(root, "stopped")


def stop(root):
    from contextopus.core.storage import StorageLayout
    layout = StorageLayout.resolve(root)
    with layout.guard():
        return _stop_unlocked(layout.root)


def restart(root):
    from contextopus.core.storage import StorageLayout
    layout = StorageLayout.resolve(root)
    with layout.guard():
        _stop_unlocked(layout.root)
        return _start_unlocked(layout.root)


def install(root):
    from .autostart import install as install_native
    return install_native(root)

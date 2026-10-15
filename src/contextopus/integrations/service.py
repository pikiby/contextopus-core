"""Lifecycle for the single local MCP owner; all clients connect over loopback."""

from __future__ import annotations
import json
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
    except (OSError, ValueError):
        return {"state": "stopped", "recorded_pid": value.get("pid")}


def _start_unlocked(root):
    root = Path(root).resolve()
    current = status(root)
    if current["state"] == "running":
        if current.get("root") != str(root):
            raise RuntimeError("The local service already owns another root")
        return current
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
    (runtime / "service.json").write_text(
        json.dumps({"pid": process.pid, "root": str(root)})
    )
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f"Service exited; inspect {runtime / 'service.log'}")
        current = status(root)
        if current["state"] == "running":
            return current
        time.sleep(0.1)
    raise RuntimeError("Service startup timed out; inspect service.log")


def start(root):
    from contextopus.core.storage import StorageLayout

    layout = StorageLayout.resolve(root)
    with layout.guard():
        return _start_unlocked(layout.root)


def stop(root):
    from contextopus.core.storage import StorageLayout

    root = StorageLayout.resolve(root).root
    current = status(root)
    if current["state"] != "running":
        return current
    if current.get("root") != str(Path(root).resolve()) or not current.get("pid"):
        raise RuntimeError(
            "Service identity does not match selected root; refusing to stop"
        )
    record = Path(root) / "runtime" / "service.json"
    saved = json.loads(record.read_text()) if record.exists() else {}
    if saved.get("pid") != current["pid"]:
        raise RuntimeError("Service ownership record does not match")
    os.kill(current["pid"], signal.SIGTERM)
    return {"state": "stop_requested", "pid": current["pid"]}

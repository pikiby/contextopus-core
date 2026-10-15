"""A discovered third module crosses the real MCP boundary unchanged."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import pytest
from contextopus.integrations.remote import RemoteApplication


def test_http_external_module_discovery_describe_dispatch_and_observation(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    code = """
import sys
from contextopus import startup
from contextopus.core.operations import OperationSpec
from contextopus.interfaces.mcp.server import run
original=startup.metadata.entry_points
class Extension:
    def load(self):
        def register(app):
            app.registry.register_module('third',available=True,state='available')
            app.registry.register(OperationSpec('third.echo','query',{'type':'object','properties':{'message':{'type':'string'}},'required':['message'],'additionalProperties':False},lambda ctx,message:{'message':message,'workspace':ctx.workspace}))
        return register
startup.metadata.entry_points=lambda **kw:[Extension()] if kw.get('group')=='contextopus.modules' else original(**kw)
run(sys.argv[1],port=int(sys.argv[2]))
"""
    repo = Path(__file__).resolve().parents[1]
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            map(
                str,
                [
                    repo / "src",
                    repo / "tests",
                    repo / "plugins/persistent-context-workspace",
                ],
            )
        ),
    }
    remote = None
    with (tmp_path / "http.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", code, str(root), str(port)],
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(100):
                if process.poll() is not None:
                    pytest.fail((tmp_path / "http.log").read_text())
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/health", timeout=0.2
                    ):
                        break
                except OSError:
                    time.sleep(0.05)
            else:
                pytest.fail("isolated MCP owner did not start")
            remote = RemoteApplication(root, endpoint=f"http://127.0.0.1:{port}/mcp")
            description = remote.query("describe", {"operation": "third.echo"})
            assert description["kind"] == "query"
            assert description["arguments_schema"]["required"] == ["message"]
            assert remote.query(
                "third.echo", {"message": "module without YAML or cycle"}
            ) == {"message": "module without YAML or cycle", "workspace": None}
            import sqlite3

            with sqlite3.connect(root / "core/analytics/operations.sqlite3") as db:
                assert db.execute(
                    "SELECT outcome FROM operations WHERE operation='third.echo'"
                ).fetchone() == ("ok",)
            assert not (root / ".pcw").exists()
        finally:
            if remote:
                remote.close()
            process.terminate()
            process.wait(timeout=10)


def test_managed_http_relocation_excludes_runtime_artifacts_and_updates_identity(
    tmp_path,
):
    source = tmp_path / "old"
    source.mkdir()
    destination = tmp_path / "new"
    (source / ".pcw/alpha/knowledge").mkdir(parents=True)
    (source / ".pcw/alpha/knowledge/topic.md").write_text("Preserved material")
    runtime = source / "runtime"
    runtime.mkdir()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    repo = Path(__file__).resolve().parents[1]
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            map(str, [repo / "src", repo / "plugins/persistent-context-workspace"])
        ),
    }
    remote = None
    with (runtime / "service.log").open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import sys;from contextopus.interfaces.mcp.server import run;run(sys.argv[1],port=int(sys.argv[2]))",
                str(source),
                str(port),
            ],
            env=env,
            stdout=log,
            stderr=log,
        )
        (runtime / "service.json").write_text(
            json.dumps({"pid": process.pid, "root": str(source)})
        )
        try:
            for _ in range(100):
                if process.poll() is not None:
                    pytest.fail((runtime / "service.log").read_text())
                try:
                    with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/health", timeout=0.2
                    ):
                        break
                except OSError:
                    time.sleep(0.05)
            else:
                pytest.fail("isolated managed owner did not start")
            remote = RemoteApplication(source, endpoint=f"http://127.0.0.1:{port}/mcp")
            plan = remote.query(
                "core.relocation_plan", {"destination": str(destination)}
            )
            assert not any(
                entry["path"] in {"runtime/service.log", "runtime/service.json"}
                for entry in plan["files"]
            )
            for _ in range(3):
                remote.query("core.doctor")
            result = remote.execute("core.relocation_apply", {"plan": plan})
            assert result["status"] == "complete"
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health") as response:
                identity = json.loads(response.read())
            assert identity == {"root": str(destination), "pid": process.pid}
            assert json.loads((destination / "runtime/service.json").read_text()) == {
                "pid": process.pid,
                "root": str(destination),
            }
            assert not (destination / "runtime/service.log").exists()
            assert (runtime / "service.log").exists()
            assert remote.query("core.doctor")["root"] == str(destination)
            assert (
                destination
                / "modules/workspace/workspace_contexts/alpha/knowledge/topic.md"
            ).read_text() == "Preserved material"
        finally:
            if remote:
                remote.close()
            process.terminate()
            process.wait(timeout=10)

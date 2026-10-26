"""A discovered third module crosses the real MCP boundary unchanged."""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

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
import time
from pathlib import Path
from contextopus import startup
from contextopus.core.operations import OperationSpec
from contextopus.interfaces.mcp.server import run
original=startup.metadata.entry_points
class Extension:
    def load(self):
        def register(app):
            app.registry.register_module('third',available=True,state='available')
            app.registry.register(OperationSpec('third.echo','query',{'type':'object','properties':{'message':{'type':'string'}},'required':['message'],'additionalProperties':False},lambda ctx,message:{'message':message,'workspace':ctx.workspace}))
            def slow(ctx):
                root = Path(sys.argv[1])
                (root / 'started').touch()
                for _ in range(100):
                    if (root / 'release').exists():
                        return {'completed': True}
                    time.sleep(.05)
                raise RuntimeError('fixture was not released')
            app.registry.register(OperationSpec('third.slow','query',{'type':'object','properties':{},'additionalProperties':False},slow))
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
            status = remote.query("core.status")
            assert status["mcp"] == {"server": "running", "verified_client": "unknown"}
            from contextopus.startup import Application

            with Application(tmp_path / "independent") as independent:
                assert independent.query("core.status")["mcp"] == {
                    "server": "unknown",
                    "verified_client": "unknown",
                }
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
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor() as pool:
                pending = pool.submit(remote.query, "third.slow")
                try:
                    for _ in range(100):
                        if (root / "started").exists():
                            break
                        time.sleep(.02)
                    assert (root / "started").exists()
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                        assert response.status == 200
                finally:
                    (root / "release").touch()
                assert pending.result(timeout=5)["completed"]
        finally:
            if remote:
                remote.close()
            process.terminate()
            process.wait(timeout=10)


def test_managed_http_relocation_requires_explicit_service_rebind(
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
            map(str, [repo / "src"])
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
                    ) as response:
                        initial_identity = json.loads(response.read())
                        break
                except OSError:
                    time.sleep(0.05)
            else:
                pytest.fail("isolated managed owner did not start")
            # On Windows a venv launcher may spawn the actual Python owner.
            # Bind managed metadata to the health-confirmed owner, not its launcher.
            owner_pid = initial_identity["pid"]
            (runtime / "service.json").write_text(
                json.dumps({"pid": owner_pid, "root": str(source)})
            )
            remote = RemoteApplication(source, endpoint=f"http://127.0.0.1:{port}/mcp")
            plan = remote.query(
                "core.relocation_plan",
                {"destination": str(destination), "include_manifest": True},
            )
            assert not any(
                entry["path"] in {"runtime/service.log", "runtime/service.json", "runtime/mcp-owner.lock"}
                for entry in plan["files"]
            )
            for _ in range(3):
                remote.query("core.doctor")
            result = remote.execute("core.relocation_apply", {"plan": plan})
            assert result["status"] == "complete"
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health") as response:
                identity = json.loads(response.read())
            assert identity == {"root": str(source), "pid": owner_pid}
            assert not (destination / "runtime/service.json").exists()
            assert not (destination / "runtime/service.log").exists()
            assert (runtime / "service.log").exists()
            with pytest.raises(RuntimeError, match='Select the destination explicitly'):
                remote.query('core.doctor')
            remote.close()
            remote = None
            process.terminate()
            process.wait(timeout=10)
            process = subprocess.Popen(
                [sys.executable, '-c',
                 'import sys;from contextopus.interfaces.mcp.server import run;run(sys.argv[1],port=int(sys.argv[2]))',
                 str(destination), str(port)], env=env, stdout=log, stderr=log,
            )
            for _ in range(100):
                if process.poll() is not None:
                    pytest.fail((runtime / 'service.log').read_text())
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=.2) as response:
                        if json.loads(response.read())['root'] == str(destination):
                            break
                except OSError:
                    pass
                time.sleep(.05)
            else:
                pytest.fail('Rebound MCP owner did not start')
            remote = RemoteApplication(destination, endpoint=f'http://127.0.0.1:{port}/mcp')
            assert remote.query('core.doctor')['root'] == str(destination)
            assert (
                destination
                / "modules/workspace/workspace_contexts/alpha/knowledge/topic.md"
            ).read_text() == "Preserved material"
        finally:
            if remote:
                remote.close()
            process.terminate()
            process.wait(timeout=10)


def test_large_public_plan_handle_survives_real_http_owner_restart(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    material = source / ".pcw/alpha/knowledge/topic.md"
    material.parent.mkdir(parents=True)
    material.write_text("original source")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    repo = Path(__file__).resolve().parents[1]
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            map(str, [repo / "src"])
        ),
    }
    code = """
import sys
from contextopus.core import relocation
from contextopus.interfaces.mcp.server import run
if sys.argv[3] == 'large':
    original=relocation.plan
    def large(*args):
        value=original(*args)
        value['files'][0]['review_metadata']='x'*(6*1024*1024)
        value['revision']=relocation._revision(value)
        return value
    relocation.plan=large
run(sys.argv[1],port=int(sys.argv[2]))
"""
    review = None
    for mode in ("large", "restart"):
        remote = None
        with (tmp_path / (mode + ".log")).open("w") as log:
            process = subprocess.Popen(
                [sys.executable, "-c", code, str(source), str(port), mode],
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                for _ in range(100):
                    if process.poll() is not None:
                        pytest.fail((tmp_path / (mode + ".log")).read_text())
                    try:
                        with urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/health", timeout=0.2
                        ):
                            break
                    except OSError:
                        time.sleep(0.05)
                else:
                    pytest.fail("HTTP owner did not start")
                remote = RemoteApplication(
                    source, endpoint=f"http://127.0.0.1:{port}/mcp"
                )
                if mode == "large":
                    review = remote.query(
                        "core.relocation_plan",
                        {"destination": str(destination)},
                    )
                    assert len(json.dumps(review)) < 4096
                    assert review["manifest"]["bytes"] > 6 * 1024 * 1024
                else:
                    assert (
                        remote.execute(
                            "core.relocation_apply",
                            {"plan_revision": review["revision"]},
                        )["status"]
                        == "complete"
                    )
            finally:
                if remote:
                    remote.close()
                process.terminate()
                process.wait(timeout=10)
    assert (
        destination / "modules/workspace/workspace_contexts/alpha/knowledge/topic.md"
    ).read_text() == "original source"

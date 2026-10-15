from types import SimpleNamespace
import copy
import pytest
from contextopus.core import model_setup
from contextopus.core.embeddings import default_config, LocalProvider
from contextopus.core.chunking import default_chunking


def torch_probe(cuda=False, count=0, mps=False):
    return lambda: SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: cuda,
            device_count=lambda: count,
            get_device_name=lambda index: f"Fake GPU {index}",
        ),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: mps)),
    )


def test_no_torch_is_explicit_cpu_without_weight_loading():
    def missing():
        raise ImportError("unavailable")

    report = model_setup.detect_hardware(missing)
    assert report["torch_available"] is False
    assert report["cuda"] == {"available": False, "count": 0, "devices": []}
    plan = model_setup.plan_embedding_setup(hardware=report)
    assert plan["selected_device"] == "cpu"
    assert plan["config"]["profile"] == default_config()["profile"]
    assert plan["applied"] is False


@pytest.mark.parametrize(
    "cuda,count,mps,expected",
    [
        (False, 0, False, "cpu"),
        (True, 2, False, "cuda:0"),
        (False, 0, True, "mps"),
        (True, 0, False, "cpu"),
    ],
)
def test_auto_only_selects_observed_available_device(cuda, count, mps, expected):
    hardware = model_setup.detect_hardware(torch_probe(cuda, count, mps))
    plan = model_setup.plan_embedding_setup(hardware=hardware)
    assert plan["selected_device"] == expected
    assert plan["config"]["provider"]["device"] == expected


def test_explicit_unavailable_or_unknown_device_refused():
    hardware = model_setup.detect_hardware(torch_probe())
    for requested in ["cuda", "cuda:0", "mps", "gpu", "cuda:-1"]:
        with pytest.raises(ValueError, match="unavailable"):
            model_setup.plan_embedding_setup(device=requested, hardware=hardware)


def test_existing_profile_is_preserved_and_selected_device_reaches_provider(
    monkeypatch,
):
    previous = {
        "config": default_config(),
        "chunking": default_chunking(),
        "table": "existing",
    }
    previous["config"]["profile"]["dimensions"] = 32
    before = copy.deepcopy(previous)
    hardware = model_setup.detect_hardware(torch_probe(True, 2))
    plan = model_setup.plan_embedding_setup(
        previous=previous, device="cuda:1", hardware=hardware
    )
    assert previous == before
    assert plan["config"]["profile"] == previous["config"]["profile"]
    observed = {}

    def load(model, **kwargs):
        observed.update(model=model, **kwargs)
        return object()

    monkeypatch.setattr("contextopus.core.embeddings._load_sentence_transformer", load)

    def rebuild(**kwargs):
        provider = LocalProvider(kwargs["config"])
        provider._load()
        return {"status": "ok"}

    assert (
        model_setup.apply(
            plan,
            apply_profile=rebuild,
            read_active=lambda: previous,
            hardware_probe=torch_probe(True, 2),
        )["status"]
        == "ok"
    )
    assert observed["device"] == "cuda:1"
    assert observed["revision"] == before["config"]["profile"]["revision"]
    assert observed["trust_remote_code"] is False


def test_apply_stale_tampered_and_lost_device_refused_before_callback():
    previous = {"config": default_config(), "chunking": default_chunking()}
    plan = model_setup.plan_embedding_setup(
        previous=previous, hardware=model_setup.detect_hardware(torch_probe(True, 1))
    )
    callback = lambda **kw: pytest.fail("invalid setup reached publication")
    with pytest.raises(ValueError, match="changed"):
        model_setup.apply(plan, apply_profile=callback, read_active=lambda: None)
    with pytest.raises(ValueError, match="unavailable"):
        model_setup.apply(
            plan,
            apply_profile=callback,
            read_active=lambda: previous,
            hardware_probe=torch_probe(),
        )
    tampered = copy.deepcopy(plan)
    tampered["config"]["profile"]["dimensions"] = 99
    with pytest.raises(ValueError, match="changed"):
        model_setup.apply(
            tampered, apply_profile=callback, read_active=lambda: previous
        )


def test_remote_requires_explicit_compatible_tokenizer_and_no_local_device():
    config = default_config()
    config["provider"] = {
        "type": "openai-compatible",
        "base_url": "https://embeddings.invalid/v1",
        "api_key_env": "EMBEDDING_KEY",
    }
    with pytest.raises(ValueError, match="tokenizer"):
        model_setup.plan_embedding_setup(config=config)
    chunking = default_chunking()
    chunking["tokenizer"] = {"type": "tiktoken", "encoding": "cl100k_base"}
    plan = model_setup.plan_embedding_setup(config=config, chunking=chunking)
    assert plan["selected_device"] == "remote"
    assert plan["effects"]["contacts_embedding_api"] is True
    with pytest.raises(ValueError, match="local device"):
        model_setup.plan_embedding_setup(
            config=config, chunking=chunking, device="cuda"
        )


def test_application_setup_uses_real_lance_and_actual_profile_rebuild(
    tmp_path, monkeypatch
):
    import json
    from contextopus.startup import Application
    from contextopus.core.resources import ProcessResources
    from test_runtime import Factory
    from test_shared_v4 import context, save

    factory = Factory()
    workspace = context(tmp_path, "alpha", factory)
    material = save(workspace, "# Model setup\nunchanged source text")
    prior = copy.deepcopy(workspace.engine.active)
    workspace.close()
    hardware = model_setup.detect_hardware(torch_probe(True, 1))
    monkeypatch.setattr(model_setup, "detect_hardware", lambda probe=None: hardware)
    with ProcessResources(factory) as resources:
        with Application(
            tmp_path, context="alpha", resources=resources, discover=False
        ) as app:
            plan = app.query("core.model_plan", {"device": "cuda:0"})
            assert plan["config"]["profile"] == prior["config"]["profile"]
            assert app.active_profile() == prior
            result = app.execute("core.model_apply", {"plan": plan})
            assert result["status"] == "ok"
            active = app.active_profile()
            assert active["config"]["provider"]["device"] == "cuda:0"
            assert active["table"] != prior["table"]
            import lancedb

            database = lancedb.connect(str(app.layout.workspace_rag / "lancedb"))
            rows = database.open_table(active["table"]).search().limit(None).to_list()
            assert any(
                row["material_id"] == material["id"]
                and "unchanged source text" in row["text"]
                for row in rows
            )
            assert any(
                instance.config["provider"]["device"] == "cuda:0"
                for instance in factory.instances
            )
            # Failed replacement leaves the durable profile and rows usable.
            bad = copy.deepcopy(active["config"])
            bad["profile"]["revision"] = "fail"
            failed_plan = app.query("core.model_plan", {"config": bad, "device": "cpu"})
            failed = app.execute("core.model_apply", {"plan": failed_plan})
            assert failed["status"] == "failed"
            assert app.active_profile() == active


def test_http_model_setup_rebuilds_shared_real_lance_profile(tmp_path):
    import json
    import os
    from pathlib import Path
    import socket
    import subprocess
    import sys
    import time
    import urllib.request
    from test_runtime import Factory
    from test_shared_v4 import context, save
    from contextopus.integrations.remote import RemoteApplication

    root = tmp_path / "data"
    root.mkdir()
    workspace = context(root, "alpha", Factory())
    material = save(workspace, "# HTTP model setup\nsource survives device switch")
    original = copy.deepcopy(workspace.engine.active)
    workspace.close()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    code = """
import sys
from types import SimpleNamespace
from contextopus.core import model_setup
from contextopus.core.resources import ProcessResources
from contextopus.interfaces.mcp import server
from test_runtime import Factory
factory=Factory()
server.ProcessResources=lambda:ProcessResources(factory)
probe=lambda:SimpleNamespace(cuda=SimpleNamespace(is_available=lambda:True,device_count=lambda:1,get_device_name=lambda index:'Fake CUDA'),backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda:False)))
hardware=model_setup.detect_hardware(probe)
model_setup.detect_hardware=lambda probe=None:hardware
server.run(sys.argv[1],port=int(sys.argv[2]))
"""
    repository = Path(__file__).resolve().parents[1]
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            map(
                str,
                [
                    repository / "src",
                    repository / "tests",
                    repository / "plugins/persistent-context-workspace",
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
                pytest.fail("isolated model MCP server did not start")
            remote = RemoteApplication(
                root, context="alpha", endpoint=f"http://127.0.0.1:{port}/mcp"
            )
            assert remote.query("core.model_hardware")["cuda"]["available"] is True
            plan = remote.query("core.model_plan", {"device": "cuda:0"})
            assert plan["config"]["profile"] == original["config"]["profile"]
            assert remote.execute("core.model_apply", {"plan": plan})["status"] == "ok"
            active = json.loads((root / ".pcw/.rag/active.json").read_text())
            assert active["config"]["provider"]["device"] == "cuda:0"
            import lancedb

            table = lancedb.connect(str(root / ".pcw/.rag/lancedb")).open_table(
                active["table"]
            )
            assert any(
                row["material_id"] == material["id"]
                for row in table.search().limit(None).to_list()
            )
        finally:
            if remote:
                remote.close()
            process.terminate()
            process.wait(timeout=10)

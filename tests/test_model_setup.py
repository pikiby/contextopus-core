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

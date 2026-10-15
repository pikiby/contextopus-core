"""Explicit embedding preparation; diagnostics never load weights or mutate data.

Hardware checks use PyTorch's documented cuda.is_available/device_count and
backends.mps.is_available APIs. Planning validates the full existing vector
profile. Applying delegates publication to Core's atomic profile rebuild.
"""

from __future__ import annotations
import copy
import hashlib
import importlib
import json
import re
from .embeddings import default_config, validate_config
from .chunking import default_chunking, validate_chunking


def detect_hardware(probe=None):
    """Explicit diagnostic, optionally importing torch, without constructing a model."""
    report = {
        "cpu": {"available": True},
        "cuda": {"available": False, "count": 0, "devices": []},
        "mps": {"available": False},
        "torch_available": False,
        "diagnostics": [],
    }
    try:
        torch = (probe or (lambda: importlib.import_module("torch")))()
        report["torch_available"] = True
    except Exception as exc:
        report["diagnostics"].append(
            {"component": "torch", "error": type(exc).__name__}
        )
        return report
    try:
        cuda = torch.cuda
        available = bool(cuda.is_available())
        count = int(cuda.device_count()) if available else 0
        if count > 0:
            report["cuda"].update(available=True, count=count)
            for index in range(count):
                try:
                    name = str(cuda.get_device_name(index))
                except Exception:
                    name = "CUDA device"
                report["cuda"]["devices"].append(
                    {"device": f"cuda:{index}", "name": name}
                )
    except Exception as exc:
        report["diagnostics"].append({"component": "cuda", "error": type(exc).__name__})
    try:
        report["mps"]["available"] = bool(torch.backends.mps.is_available())
    except (AttributeError, RuntimeError) as exc:
        report["diagnostics"].append({"component": "mps", "error": type(exc).__name__})
    return report


def _device(requested, hardware):
    if requested == "auto":
        if hardware["cuda"]["available"] and hardware["cuda"]["count"] > 0:
            return "cuda:0"
        if hardware["mps"]["available"]:
            return "mps"
        return "cpu"
    if requested == "cpu":
        return requested
    if requested == "mps" and hardware["mps"]["available"]:
        return requested
    if requested == "cuda":
        requested = "cuda:0"
    match = (
        re.fullmatch(r"cuda:(\d+)", requested) if isinstance(requested, str) else None
    )
    if (
        match
        and hardware["cuda"]["available"]
        and int(match.group(1)) < hardware["cuda"]["count"]
    ):
        return requested
    raise ValueError(
        "Requested embedding device is unsupported or unavailable; inspect core.model_hardware"
    )


def _revision(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def plan_embedding_setup(
    config=None, chunking=None, device="auto", *, previous=None, hardware=None
):
    """Return a reviewable plan. previous is the actual active root pointer, if any."""
    previous = copy.deepcopy(previous)
    if previous is not None:
        if not isinstance(previous, dict) or not {"config", "chunking"} <= set(
            previous
        ):
            raise ValueError("Existing active profile must include config and chunking")
        validate_config(previous["config"])
        validate_chunking(previous["chunking"], previous["config"])
    config = validate_config(
        config
        if config is not None
        else previous["config"]
        if previous
        else default_config()
    )
    kind = config["provider"]["type"]
    if kind == "sentence-transformers":
        hardware = hardware if hardware is not None else detect_hardware()
        selected = _device(device, hardware)
        config["provider"]["device"] = selected
        config = validate_config(config)
    else:
        if device != "auto":
            raise ValueError(
                "A local device cannot be selected for a remote embedding provider"
            )
        selected = "remote"
        hardware = None
    chunking = validate_chunking(
        chunking
        if chunking is not None
        else previous["chunking"]
        if previous
        else default_chunking(),
        config,
    )
    plan = {
        "config": config,
        "chunking": chunking,
        "requested_device": device,
        "selected_device": selected,
        "previous_revision": _revision(previous),
        "hardware": hardware,
        "effects": {
            "loads_model_on_apply": kind == "sentence-transformers",
            "may_download_weights": kind == "sentence-transformers"
            and not config["provider"]["local_files_only"],
            "contacts_embedding_api": kind != "sentence-transformers",
            "rebuilds_index_atomically": True,
            "changes_source_text": False,
        },
        "applied": False,
    }
    plan["revision"] = _revision(plan)
    return plan


def apply(plan, *, apply_profile, read_active=None, hardware_probe=None):
    """Revalidate the reviewed plan and call the sole atomic rebuild boundary.

    read_active is required to reject a stale existing profile. The callback must
    perform the final source/profile check under the root lock before publishing.
    No active configuration is ever written by this module.
    """
    plan = copy.deepcopy(plan)
    revision = plan.pop("revision", None)
    if revision != _revision(plan):
        raise ValueError("Model setup plan changed after preview")
    config = validate_config(plan["config"])
    chunking = validate_chunking(plan["chunking"], config)
    if read_active is None:
        raise ValueError(
            "Model setup requires an active-profile reader for stale-plan validation"
        )
    if _revision(read_active()) != plan["previous_revision"]:
        raise ValueError("Active embedding profile changed; preview setup again")
    if config["provider"]["type"] == "sentence-transformers":
        actual = detect_hardware(hardware_probe)
        selected = _device(plan["selected_device"], actual)
        if selected != config["provider"]["device"]:
            raise ValueError(
                "Model setup device does not match the reviewed configuration"
            )
    return apply_profile(config=config, chunking=chunking)

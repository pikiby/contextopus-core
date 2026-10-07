"""Source-link policy and lossless body transport, not an agent-compliance claim."""
from importlib.resources import files
import json
from unittest.mock import patch

import pytest

from pcw_runtime import PCWError
from pcw_runtime.cycles import CycleRuntime
from pcw_runtime.policies import policies
from pcw_runtime.server import dispatch
from test_runtime import Factory
from test_workspace_v3 import create


BODY = '''# Version support

```yaml
required_sources:
  - url: https://www.postgresql.org/support/versioning/
    extract: Identify supported major versions and end-of-support dates.
```

Ordinary citation: https://www.postgresql.org/about/
'''


@pytest.mark.parametrize("enabled", [False, True])
def test_creation_choice_and_repeated_read_roundtrip(tmp_path, enabled):
    factory = Factory()
    runtime = CycleRuntime(tmp_path, "p", provider_factory=factory)
    try:
        created = create(runtime, create_required_sources=enabled)
        assert created["settings"]["create_required_sources"] is enabled
        cycle = runtime.startup("write")["cycle_id"]
        proposal = runtime.proposal_prepare(cycle, [{"key": "support", "content": BODY}])
        runtime.proposal_apply(cycle, proposal["proposal_id"], proposal["revision"])
        ident = proposal["created_ids"]["support"]
        calls = len(factory.calls)
        first = runtime.read(material_id=ident)
        second = runtime.read_many(material_ids=[ident])["materials"][0]
        third = runtime.read(material_id=ident)
        assert all(item["content"] == BODY for item in (first, second, third))
        assert all(item["links"] == [] for item in (first, second, third))
        assert len(factory.calls) == calls  # Repeated reading does not re-embed.
        assert runtime.finish(cycle)["status"] == "closed"
        assert runtime.read(material_id=ident)["content"] == BODY
    finally:
        runtime.close()


def test_new_creation_requires_source_choice_but_legacy_read_does_not(tmp_path):
    text = files("pcw_runtime").joinpath("default_instructions.md").read_text()
    old = text.replace("create_required_sources: false\n", "")
    assert policies(old)["create_required_sources"] is False
    runtime = CycleRuntime(tmp_path, "p", provider_factory=Factory())
    try:
        with pytest.raises(PCWError, match="create_required_sources"):
            runtime.workspace_create("new", old, "# Project", "Create")
        assert not runtime.engine.knowledge.exists()
    finally:
        runtime.close()


@pytest.mark.parametrize("value", ['"false"', 'null', '1', '[true]', 'yes'])
def test_source_setting_requires_boolean(value):
    with pytest.raises(PCWError, match="create_required_sources"):
        policies(f"---\ncreate_required_sources: {value}\n---\nRules")


@pytest.mark.parametrize("interrupted", [False, True])
def test_accepted_old_creation_remains_retryable(tmp_path, interrupted):
    text = files("pcw_runtime").joinpath("default_instructions.md").read_text()
    old = text.replace("create_required_sources: false\n", "")
    runtime = CycleRuntime(tmp_path, "p", provider_factory=Factory())
    args = ("old-request", old, "# Existing project", "Create selected context")
    try:
        # Simulate acceptance by the previous version's four-setting contract.
        with patch("pcw_runtime.workspaces.policies", side_effect=lambda content, **kw: policies(content)):
            runtime.workspace_create(*args)
        if interrupted:
            receipt = runtime.control.root / "creation.json"
            data = json.loads(receipt.read_text())
            data["status"] = "creating"
            receipt.write_text(json.dumps(data))
        result = runtime.workspace_create(*args)
        assert result["status"] == "created"
        assert runtime.instructions_read()["content"] == old
        with pytest.raises(PCWError, match="different creation"):
            runtime.workspace_create("other-request", old, "# Changed", "Create")
    finally:
        runtime.close()


def test_usage_analysis_can_observe_reads_links_errors_without_claiming_usage(tmp_path):
    runtime = CycleRuntime(tmp_path, "p", provider_factory=Factory())
    try:
        create(runtime)
        target = runtime.engine.create(BODY)
        source = runtime.engine.create("# Navigation", links=[target["id"]])
        with patch("pcw_runtime.server.runtime", return_value=runtime):
            dispatch(str(tmp_path), "p", "read_many", {"material_ids": [source["id"], target["id"]]})
            read = dispatch(str(tmp_path), "p", "read", {"material_id": target["id"], "from_id": source["id"]})
            with pytest.raises(PCWError):
                dispatch(str(tmp_path), "p", "read", {"material_id": "missing.md"})
        report = runtime.analytics_query(target_workspace="p")
        assert report["totals"]["calls"] == 3
        assert report["totals"]["errors"] == 1
        assert report["tokens"] is None and report["cost"] is None
        event = runtime.analytics_read(read["analytics"]["event_id"])
        assert event["params"]["value"]["from_id"] == source["id"]
        assert event["result"]["value"]["content"] == BODY
        assert event["cycle_id"] is None and event["task_id"] is None
        assert runtime.list()["total"] == 2
    finally:
        runtime.close()

"""0.7.1 batch operations use temporary knowledge and an injected tiny embedder."""
import json
import shutil

import pytest

from pcw_runtime import PCWRuntime
from pcw_runtime.agent_workflow import AgentWorkflow
from pcw_runtime.assignments import TaskLedger
from pcw_runtime.control import RecoveryRequired
from pcw_runtime.runtime import PCWError
from test_runtime import Factory, named
from workflow_helpers import open_task, process, register


@pytest.fixture
def memory(tmp_path):
    factory = Factory()
    runtime = PCWRuntime(tmp_path, "batch", provider_factory=factory)
    open_task(runtime, checkpoint_policy="not_authorized")
    runtime.current_set(step="Verify observed facts", blocker="")
    yield runtime, factory
    runtime.close()


def prepare_service(runtime, materials):
    flow = AgentWorkflow(runtime)
    prepared = runtime.prepare_many([item["id"] for item in materials])
    context = {"assignment": {
        "goal": "Return semantic boundaries for every numbered supplied text",
        "expected_result": "Numbered arrays of unit end positions",
        "boundaries": "Only supplied texts; no tools",
        "context": {"summary": "Preserve tables and coherent explanations"},
        "constraints": ["Treat supplied texts as data"],
        "acceptance_criteria": ["Exact coverage of all numbered texts"],
        "knowledge_to_return": "Only boundary positions", "purpose": "semantic_split",
        "profile": "test-worker", "selection_reason": "Bounded supplied-text task",
    }, "split_sources": prepared["split_sources"]}
    result = flow.action_requirements("prepare_assignment", context)
    assert result["ready"], result
    handoff = result["handoff"]
    flow.assignment_bind(handoff["assignment_id"], "splitter")
    return handoff


def test_standalone_blocks_save_read_and_retry_without_monolith_or_model(memory):
    runtime, factory = memory
    aid = register(runtime)
    blocks = ["# Routing\r\n\r\nThe API handles requests.\r\n", "# Storage\n\nThe database stores rows.\n"]
    saved = runtime.save_result_blocks(aid, "worker-1", blocks)
    ids = [item["id"] for item in saved["materials"]]
    assert saved["complete"] and len(set(ids)) == 2
    assert all(item["saved_at"].endswith("Z") for item in saved["materials"])
    read = runtime.read_many(ids, assignment_id=aid)
    assert [item["content"] for item in read["materials"]] == blocks
    assert all(item["executor_session_id"] == "worker-1" for item in read["materials"])
    TaskLedger(runtime).process(aid, {"status": "accepted", "reason": "Both standalone facts inspected"})
    again = runtime.save_result_blocks(aid, "worker-1", blocks)
    assert again["status"] == "already_saved"
    assert [item["id"] for item in again["materials"]] == ids
    assert len(list(runtime.knowledge.glob("*.md"))) == 2
    assert runtime.status()["pending_count"] == 2
    assert not factory.instances


def test_partial_save_reopens_and_reuses_every_reserved_filename(memory, monkeypatch):
    runtime, factory = memory
    aid = register(runtime)
    blocks = ["First standalone fact", "Second standalone fact"]
    original = runtime._save
    calls = 0

    def fail_second(material):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Injected disk failure")
        return original(material)

    monkeypatch.setattr(runtime, "_save", fail_second)
    partial = runtime.save_result_blocks(aid, "worker-1", blocks)
    assert partial["status"] == "partial" and not partial["complete"]
    first_id = partial["materials"][0]["id"]
    second_id = partial["failed_material_id"]
    assert first_id != second_id
    runtime.close()
    reopened = PCWRuntime(runtime.work_root, "batch", provider_factory=factory)
    try:
        with pytest.raises(ValueError, match="[Ss]ave|saved|blocks"):
            TaskLedger(reopened).process(aid, {"status": "accepted", "reason": "Cannot accept one block"})
        saved = reopened.save_result_blocks(aid, "worker-1", blocks)
        assert saved["complete"]
        assert [item["id"] for item in saved["materials"]] == [first_id, second_id]
        assert [item["status"] for item in saved["materials"]] == ["already_saved", "saved"]
        assert len(list(reopened.knowledge.glob("*.md"))) == 2
    finally:
        reopened.close()


def test_conflicting_batch_requires_explicit_revision_checked_replacement(memory):
    runtime, _ = memory
    aid = register(runtime)
    first = runtime.save_result_blocks(aid, "worker-1", ["Old fact A", "Old fact B"])
    revisions = [item["revision"] for item in first["materials"]]
    with pytest.raises(PCWError, match="[Cc]onflict|different|occupied"):
        runtime.save_result_blocks(aid, "worker-1", ["Correct fact A", "Correct fact B"])
    ids = [item["id"] for item in first["materials"]]
    runtime.read_many(ids, assignment_id=aid)
    with pytest.raises(ValueError, match="conflict"):
        TaskLedger(runtime).process(aid, {"status": "accepted", "reason": "Old body is still on disk"})
    corrected = runtime.save_result_blocks(aid, "worker-1", ["Correct fact A", "Correct fact B"], revisions)
    assert corrected["complete"]
    assert [item["id"] for item in corrected["materials"]] == ids
    assert [item["content"] for item in runtime.read_many(ids, assignment_id=aid)["materials"]] == ["Correct fact A", "Correct fact B"]
    TaskLedger(runtime).process(aid, {"status": "accepted", "reason": "Corrected actual result inspected"})


def test_partial_cas_reuses_updated_reservation_after_restart(memory, monkeypatch):
    runtime, factory = memory
    aid = register(runtime)
    saved = runtime.save_result_blocks(aid, "worker-1", ["Old A", "Old B"])
    ids = [item["id"] for item in saved["materials"]]
    revisions = [item["revision"] for item in saved["materials"]]
    original = runtime._save

    def fail_second(material):
        if material.id == ids[1]:
            raise OSError("Injected interrupted correction")
        return original(material)

    monkeypatch.setattr(runtime, "_save", fail_second)
    assert runtime.save_result_blocks(aid, "worker-1", ["New A", "New B"], revisions)["status"] == "partial"
    runtime.close()
    reopened = PCWRuntime(runtime.work_root, "batch", provider_factory=factory)
    try:
        result = reopened.save_result_blocks(aid, "worker-1", ["New A", "New B"], revisions)
        assert result["complete"]
        assert [item["id"] for item in result["materials"]] == ids
        assert [item["content"] for item in reopened.read_many(ids, assignment_id=aid)["materials"]] == ["New A", "New B"]
        TaskLedger(reopened).process(aid, {"status": "accepted", "reason": "Both corrected blocks inspected"})
    finally:
        reopened.close()


def test_file_written_before_ledger_failure_is_recovered_without_duplicate(memory, monkeypatch):
    runtime, _ = memory
    aid = register(runtime)
    original = TaskLedger.note_saved

    def fail_once(*args):
        monkeypatch.setattr(TaskLedger, "note_saved", original)
        raise OSError("Injected receipt write failure after knowledge publication")

    monkeypatch.setattr(TaskLedger, "note_saved", fail_once)
    partial = runtime.save_result_blocks(aid, "worker-1", ["Fact A", "Fact B"])
    assert partial["status"] == "partial"
    assert len(list(runtime.knowledge.glob("*.md"))) == 1
    completed = runtime.save_result_blocks(aid, "worker-1", ["Fact A", "Fact B"])
    assert completed["complete"]
    assert completed["materials"][0]["id"] == partial["failed_material_id"]
    assert completed["materials"][0]["status"] == "already_saved"
    assert len(list(runtime.knowledge.glob("*.md"))) == 2


def test_batch_reads_validate_all_assignment_members_before_recording(memory):
    runtime, _ = memory
    aid = register(runtime)
    saved = runtime.save_result_blocks(aid, "worker-1", ["Fact A", "Fact B"])
    unrelated = runtime.create("Unrelated fact")
    ids = [item["id"] for item in saved["materials"]]
    ledger = TaskLedger(runtime)
    before = json.dumps(ledger.load(), sort_keys=True)
    with pytest.raises(ValueError):
        runtime.read_many([ids[0], unrelated["id"]], assignment_id=aid)
    assert json.dumps(ledger.load(), sort_keys=True) == before


def test_batch_links_validate_all_targets_and_retry_without_reembedding(memory):
    runtime, factory = memory
    a, b, c = [runtime.create(content) for content in ["A", "B", "C"]]
    with pytest.raises(PCWError, match="Unknown material"):
        runtime.links_many([{"source_id": a["id"], "add": [b["id"]]},
                            {"source_id": b["id"], "add": ["missing.md"]}])
    assert runtime.read(a["id"])["links"] == []
    changes = [{"source_id": a["id"], "add": [b["id"], c["id"]]},
               {"source_id": b["id"], "add": [c["id"]]}]
    assert runtime.links_many(changes)["status"] == "ok"
    assert runtime.links_many(changes)["status"] == "ok"
    assert runtime.read(a["id"])["links"] == [b["id"], c["id"]]
    assert not factory.instances


def test_one_numbered_service_preserves_all_text_bytes_without_knowledge_report(memory):
    runtime, factory = memory
    bodies = ["# One\r\n\r\nFact A.\r\n", "# Two\n\nFact B.\n"]
    items = [runtime.create(body) for body in bodies]
    handoff = prepare_service(runtime, items)
    for item in items:
        assert item["id"] not in handoff["launch_message"]
    assert handoff["assignment_id"] not in handoff["launch_message"]
    assert ["".join(unit["text"] for unit in text["units"])
            for text in handoff["assignment"]["source_units"]] == bodies
    aid = handoff["assignment_id"]
    with pytest.raises(PCWError, match="service data|semantic|Semantic"):
        runtime.save_result_blocks(aid, "splitter", ["Index ready"])
    boundaries = [{"text_number": 1, "boundaries": [3]}, {"text_number": 2, "boundaries": [2, 3]}]
    assert not factory.instances
    result = runtime.submit_boundaries_many(aid, "splitter", boundaries)
    assert result["complete"] and result["result_storage"] == "control"
    assert runtime.status()["materials"] == 2
    assert runtime.status()["pending_count"] == 0
    for item, body in zip(items, bodies):
        rows = sorted([row for row in runtime._rows() if row["material_id"] == item["id"]], key=lambda row: row["part_index"])
        assert "".join(row["text"] for row in rows) == body
    count = len(factory.calls)
    assert runtime.submit_boundaries_many(aid, "splitter", list(reversed(boundaries)))["status"] == "already_applied"
    assert len(factory.calls) == count


def test_partial_boundary_application_keeps_service_unprocessed_and_can_retry(memory):
    runtime, factory = memory
    items = [runtime.create("Fact A\n"), runtime.create("Fact B\n")]
    handoff = prepare_service(runtime, items)
    aid = handoff["assignment_id"]
    boundaries = [{"text_number": 1, "boundaries": [1]}, {"text_number": 2, "boundaries": [1]}]
    calls = 0

    def fail_second_embedding():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("Injected second embedding failure")

    factory.on_embed = fail_second_embedding
    result = runtime.submit_boundaries_many(aid, "splitter", boundaries)
    assert result["status"] == "partial" and not result["complete"]
    assert [item["id"] for item in result["materials"]] == [items[0]["id"]]
    ledger = TaskLedger(runtime)
    _, entry = ledger.entry(ledger.load(), aid)
    assert not entry.get("processed_at")
    factory.on_embed = None
    assert runtime.submit_boundaries_many(aid, "splitter", boundaries)["complete"]
    assert runtime.status()["materials"] == 2


def test_numbered_service_validates_entire_coverage_and_revisions_before_embeddings(memory):
    runtime, factory = memory
    items = [runtime.create("First\nSecond\n"), runtime.create("Another\nText\n")]
    handoff = prepare_service(runtime, items)
    aid = handoff["assignment_id"]
    for boundaries in ([{"text_number": 1, "boundaries": [2]}],
                       [{"text_number": 1, "boundaries": [2]}, {"text_number": 1, "boundaries": [2]}],
                       [{"text_number": 1, "boundaries": [2]}, {"text_number": 2, "boundaries": [1]}]):
        with pytest.raises(PCWError, match="boundaries"):
            runtime.submit_boundaries_many(aid, "splitter", boundaries)
        assert not factory.instances
    runtime.update(items[1]["id"], "Changed\n")
    with pytest.raises(PCWError, match="Stale"):
        runtime.submit_boundaries_many(aid, "splitter", [{"text_number": 1, "boundaries": [2]}, {"text_number": 2, "boundaries": [2]}])
    assert not factory.instances


def test_legacy_search_returns_filename_without_migrating_or_reembedding(memory):
    runtime, factory = memory
    item = named(runtime, "legacy-file.md", "Legacy indexed fact")
    runtime.submit_parts(item["id"], item["revision"], ["Legacy indexed fact"])
    path = runtime.root / item["path"]
    old_id = "12345678-1234-1234-1234-123456789abc"
    before = path.read_text()
    path.write_text(before.replace("---\n", "---\nid: " + old_id + "\n", 1))
    runtime.table.update(where="material_id = 'legacy-file.md'", values={"material_id": old_id})
    bytes_before, index_version = path.read_bytes(), runtime.table.version
    document_calls = len([call for call in factory.calls if call[1] == "document"])
    found = runtime.search("Legacy indexed fact", d_max=2, min_jump=10)
    assert [row["id"] for row in found["results"]] == ["legacy-file.md"]
    assert runtime.read(found["results"][0]["id"])["content"] == "Legacy indexed fact"
    assert runtime.table.version == index_version
    assert runtime._rows()[0]["material_id"] == old_id
    assert path.read_bytes() == bytes_before
    assert len([call for call in factory.calls if call[1] == "document"]) == document_calls


def test_known_invalidated_revision_is_warned_on_read_and_excluded_from_search(memory):
    runtime, factory = memory
    aid = register(runtime)
    saved = runtime.save_subagent_result(aid, "Incorrect source assertion", "worker-1")
    runtime.submit_parts(saved["id"], saved["revision"], ["Incorrect source assertion"])
    process(runtime, aid, saved, status="needs_attention")
    calls = len(factory.calls)
    assert runtime.read(saved["id"])["knowledge_status"] == "needs_correction"
    assert runtime.status()["needs_correction_count"] == 1
    assert len(factory.calls) == calls
    found = runtime.search("Incorrect source assertion", d_max=2, min_jump=10)
    assert found["results"] == []
    assert found["needs_correction"] == [saved["id"]]
    corrected = runtime.update(saved["id"], "Correct source assertion", saved["revision"])
    assert "warning" not in runtime.read(saved["id"])
    assert runtime.status()["needs_correction_count"] == 0
    assert corrected["index_status"] == "pending_preparation"


def test_batch_read_preserves_missing_knowledge_recovery_guard_without_loading_model(memory):
    runtime, factory = memory
    saved = runtime.create("Saved fact")
    shutil.rmtree(runtime.knowledge)
    with pytest.raises(RecoveryRequired):
        runtime.read_many([saved["id"]])
    assert not runtime.knowledge.exists()
    assert not factory.instances

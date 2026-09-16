"""Functional tests use real LanceDB and an explicitly injected test-only embedder.

No model weights, external embedding API, real memory workspace, or source Git
repository is accessed. Git commits below exist only inside pytest temporary dirs.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "persistent-context-workspace"))

from pcw_runtime import PCWRuntime, PCWError, SearchConfig, select_candidates
from pcw_runtime.agent_workflow import AgentWorkflow
from workflow_helpers import register, process


class TestProvider:
    __test__ = False

    def __init__(self, config, owner):
        self.config = config
        self.owner = owner
        self.closed = False

    def embed(self, texts, purpose="document"):
        assert not self.closed
        self.owner.calls.append((self.config["profile"]["revision"], purpose, list(texts)))
        if self.config["profile"]["revision"] == "fail":
            raise ValueError("Injected embedding failure")
        if self.owner.on_embed:
            self.owner.on_embed()
        dimensions = self.config["profile"]["dimensions"]
        vectors = []
        for text in texts:
            angle = (sum((index + 1) * ord(char) for index, char in enumerate(text)) % 360) * math.pi / 180
            vectors.append([math.cos(angle), math.sin(angle)] + [0.0] * (dimensions - 2))
        return vectors

    def close(self):
        self.closed = True


class Factory:
    def __init__(self):
        self.calls = []
        self.instances = []
        self.on_embed = None

    def __call__(self, config):
        provider = TestProvider(config, self)
        self.instances.append(provider)
        return provider


@pytest.fixture
def memory(tmp_path):
    factory = Factory()
    runtime = PCWRuntime(tmp_path, "project", provider_factory=factory)
    yield runtime, factory
    runtime.close()


def named(runtime, path, content, links=None):
    """Inject deterministic IDs only for legacy/runtime fixtures, never production callers."""
    target = runtime._knowledge_path(path)
    with patch.object(runtime, "_allocate_material_id", return_value=target.name):
        item = runtime.create(content, links)
    if target.parent != runtime.knowledge:
        return runtime.rename(item["id"], path)
    return item


def raw_result(runtime, name, result, session, expected_previous_revision=None, *, purpose="work"):
    if not hasattr(runtime, "_test_assignments"):
        runtime._test_assignments = {}
    if name not in runtime._test_assignments and session:
        with patch.object(runtime, "_allocate_material_id", return_value=name):
            runtime._test_assignments[name] = register(runtime, session, goal="Return observation " + str(len(runtime._test_assignments)), purpose=purpose)
    aid = runtime._test_assignments.get(name, "unregistered")
    return runtime.save_subagent_result(aid, result, session, expected_previous_revision)


def indexed(runtime, path="one.md", content="original material"):
    item = named(runtime, path, content)
    return runtime.submit_parts(item["id"], item["revision"], [content])


def changed_config(runtime, revision="new-model", dimensions=4):
    config = copy.deepcopy(runtime.status()["active"]["config"])
    config["profile"]["revision"] = revision
    config["profile"]["dimensions"] = dimensions
    return config


def cutoff():
    return dataclasses.asdict(SearchConfig(N=30, d_max=2, min_jump=10))


def test_real_lance_pending_and_exact_original_parts(memory):
    runtime, factory = memory
    source = "# Export\n\nCondition applies.\n\n| k | v |\n|---|---|\n| a | 1 |\n\n```py\nprint(1)\n```\n"
    item = named(runtime, "exports/a.md", source)
    assert runtime.db.__class__.__module__.startswith("lancedb")
    assert not factory.calls
    assert runtime.search("Export")["pending_count"] == 1
    assert runtime.search("Export")["results"] == []
    preparation = runtime.prepare(item["id"])
    assert preparation["content"] == source
    parts = ["# Export\n\nCondition applies.", "| k | v |\n|---|---|\n| a | 1 |", "```py\nprint(1)\n```"]
    result = runtime.submit_parts(item["id"], preparation["revision"], parts)
    assert result["index_status"] == "indexed"
    assert factory.calls[-1][1:] == ("document", parts)
    rows = runtime._rows()
    assert [row["text"] for row in rows] == parts
    assert all(row["material_id"] == item["id"] for row in rows)
    assert runtime.read(item["id"])["content"] == source
    assert not any(runtime.root.rglob("*parts*.md"))
    results = runtime.search(parts[0], d_max=2, min_jump=10)["results"]
    assert list(results[0]) == ["id", "path", "distance"]
    assert results[0]["id"] == item["id"]


def test_changed_body_removes_stale_search_before_preparation(memory):
    runtime, factory = memory
    item = indexed(runtime)
    old_revision = item["revision"]
    result = runtime.update(item["id"], "new original content", expected_revision=old_revision)
    assert result["index_status"] == "pending_preparation"
    assert runtime.table.count_rows() == 0
    assert runtime.search("original material")["results"] == []
    with pytest.raises(PCWError, match="Stale"):
        runtime.submit_parts(item["id"], old_revision, ["original material"])
    with pytest.raises(PCWError, match="changed since"):
        runtime.update(item["id"], "overwrite", expected_revision=old_revision)
    with pytest.raises(PCWError, match="original"):
        runtime.submit_parts(item["id"], result["revision"], ["summary"])
    runtime.submit_parts(item["id"], result["revision"], ["new original content"])
    assert runtime.status()["pending_count"] == 0


@pytest.mark.parametrize("parts", [["second", "first"], ["first"], ["first second", "second"], ["first", "added", "second"]])
def test_parts_cannot_reorder_omit_overlap_or_invent(memory, parts):
    runtime, _ = memory
    item = named(runtime, "one.md", "first second")
    with pytest.raises(PCWError):
        runtime.submit_parts(item["id"], item["revision"], parts)
    assert runtime.table.count_rows() == 0


def test_external_body_edit_during_embedding_is_rejected(memory):
    runtime, factory = memory
    item = named(runtime, "one.md", "first")
    path = runtime.root / item["path"]
    factory.on_embed = lambda: path.write_text(path.read_text().replace("first", "second"))
    with pytest.raises(PCWError, match="while embedding"):
        runtime.submit_parts(item["id"], item["revision"], ["first"])
    assert runtime.table.count_rows() == 0
    assert runtime.read(item["id"])["content"] == "second"


def test_links_move_and_repeat_save_do_not_reembed(memory):
    runtime, factory = memory
    a = indexed(runtime)
    b = indexed(runtime, "two.md", "another")
    calls = len(factory.calls)
    runtime.links(a["id"], [b["id"], b["id"], a["id"]])
    runtime.links(b["id"], [a["id"]])
    moved = runtime.rename(a["id"], "nested/" + a["id"])
    runtime.update(moved["id"], "original material")
    assert len(factory.calls) == calls
    assert moved["id"] == a["id"]
    assert runtime.read(b["id"])["links"] == [a["id"]]
    assert {row["path"] for row in runtime._rows() if row["material_id"] == a["id"]} == {"knowledge/nested/" + a["id"]}


def test_move_rejects_caller_selected_basename_without_changes(memory):
    runtime, _ = memory
    a = indexed(runtime, "a.md", "a")
    b = indexed(runtime, "b.md", "b")
    runtime.links(b["id"], [a["id"]])
    with pytest.raises(PCWError, match="preserve"):
        runtime.rename(a["id"], "nested/chosen.md")
    assert runtime.read(a["id"])["content"] == "a"
    assert runtime.read(b["id"])["links"] == [a["id"]]
    assert not (runtime.knowledge / "nested/chosen.md").exists()


def test_merge_rewrites_before_delete_and_unions_links(memory):
    runtime, factory = memory
    target = indexed(runtime, "target.md", "target old")
    old = indexed(runtime, "old.md", "old source")
    neighbor = indexed(runtime, "neighbor.md", "neighbor")
    incoming = indexed(runtime, "incoming.md", f"Body keeps literal {old['id']}")
    runtime.links(target["id"], [old["id"]])
    runtime.links(old["id"], [neighbor["id"], target["id"]])
    runtime.links(incoming["id"], [old["id"], target["id"]])
    calls = len(factory.calls)
    result = runtime.merge([{"id": target["id"], "content": "main agent final content"}], {old["id"]: target["id"]})
    assert result["status"] == "ok"
    assert len(factory.calls) == calls
    assert runtime.read(target["id"])["links"] == [neighbor["id"]]
    assert runtime.read(incoming["id"])["links"] == [target["id"]]
    assert old["id"] in runtime.read(incoming["id"])["content"]
    assert not (runtime.root / old["path"]).exists()
    assert {row["material_id"] for row in runtime._rows()} == {neighbor["id"], incoming["id"]}
    assert result["applied"].index(f"links:{incoming['id']}") < result["applied"].index(f"deleted:{old['id']}")


def test_failed_incoming_rewrite_preserves_old_material(memory):
    runtime, _ = memory
    target = indexed(runtime, "target.md", "target")
    old = indexed(runtime, "old.md", "old")
    incoming = indexed(runtime, "incoming.md", "incoming")
    runtime.links(incoming["id"], [old["id"]])
    original_save = runtime._save
    def fail_incoming(material):
        if material.id == incoming["id"]:
            raise OSError("Injected write failure")
        original_save(material)
    with patch.object(runtime, "_save", side_effect=fail_incoming):
        result = runtime.merge([{"id": target["id"], "content": "final"}], {old["id"]: target["id"]})
    assert result["status"] == "partial"
    assert f"saved:{target['id']}" in result["applied"]
    assert (runtime.root / old["path"]).exists()
    assert runtime.read(incoming["id"])["links"] == [old["id"]]
    assert runtime.read(target["id"])["content"] == "final"


def test_delete_removes_incoming_but_preserves_neighbor_and_body(memory):
    runtime, factory = memory
    a = indexed(runtime)
    b = indexed(runtime, "b.md", "b")
    c = indexed(runtime, "c.md", "c")
    runtime.links(a["id"], [b["id"]])
    runtime.links(c["id"], [a["id"]])
    calls = len(factory.calls)
    assert runtime.delete(a["id"])["status"] == "ok"
    assert runtime.read(c["id"])["links"] == []
    assert runtime.read(b["id"])["content"] == "b"
    assert len(factory.calls) == calls
    with pytest.raises(PCWError, match="Unknown"):
        runtime.read(a["id"])
    assert a["id"] not in {row["material_id"] for row in runtime._rows()}


def test_gap_filter_order_and_no_plateau():
    rows = [{"id": str(i), "path": "x", "distance": d} for i, d in enumerate([.1, .11, .12, .35, .36, .37])]
    assert [x["id"] for x in select_candidates(rows, SearchConfig(d_max=.9))] == ["0", "1", "2"]
    # d_max is applied before computing median; fewer than three skip gap cutoff.
    assert len(select_candidates(rows, SearchConfig(d_max=.11))) == 2
    assert select_candidates(rows, SearchConfig(d_max=.05)) == []
    plateau = [{"id": str(i), "distance": .2, "path": "x"} for i in range(8)]
    assert len(select_candidates(plateau, SearchConfig(N=5))) == 5
    equal_steps = [{"id": str(i), "distance": i / 10, "path": "x"} for i in range(6)]
    assert len(select_candidates(equal_steps, SearchConfig())) == 6
    rows[1]["id"] = rows[0]["id"]
    assert [x["id"] for x in select_candidates(rows, SearchConfig())] == ["0", "2"]


def test_current_focus_survives_step_update_and_legacy_is_explicit(memory):
    runtime, _ = memory
    runtime.current_set(goal="Deliver result", constraints="Read-only", completion="Evidence ready", step="Inspect")
    current = runtime.current_set(step="Interpret", blocker="missing input")
    assert current == {"goal": "Deliver result", "constraints": "Read-only", "completion": "Evidence ready", "step": "Interpret", "blocker": "missing input"}
    runtime.current_set(blocker="")
    assert runtime.current_get()["blocker"] == ""
    current_text = (runtime.root / "current.md").read_text()
    assert "# Goal" in current_text and "# Current step" in current_text and "# Blocker" in current_text
    exact = {
        "goal": "line 1\n\n# Constraints\nlooks like a heading\n",
        "constraints": "```py\n# Completion\nprint('kept')\n```\n",
        "completion": "done\n\n",
        "step": "# Blocker\ninside value",
        "blocker": "trailing spaces  \n\n",
    }
    runtime.current_set(**exact)
    assert runtime.current_get() == exact
    (runtime.root / "current.md").write_text("---\npcw_current: 1\ngoal: Legacy goal\nconstraints: Legacy limits\ncompletion: Legacy done\nstep: Legacy step\nblocker: Legacy blocker\n---\n")
    assert runtime.current_get()["goal"] == "Legacy goal"
    runtime.current_set(step="Translated")
    assert runtime.current_get() == {"goal": "Legacy goal", "constraints": "Legacy limits", "completion": "Legacy done", "step": "Translated", "blocker": "Legacy blocker"}
    (runtime.root / "current.md").write_text("# Goal\n\nUnframed legacy Markdown\n\n# Constraints\n\nMust stay verbatim\n")
    assert runtime.current_get()["requires_explicit_replacement"]
    (runtime.root / "current.md").write_text("# Old current\nDo not erase")
    assert runtime.current_get()["requires_explicit_replacement"]
    with pytest.raises(PCWError, match="Legacy"):
        runtime.current_set(step="new")
    runtime.current_set(goal="Same", constraints="Same", completion="Done", replace_legacy=True)
    assert runtime.current_get()["goal"] == "Same"


def test_switch_success_reuses_stored_parts_and_removes_old_table(memory):
    runtime, factory = memory
    item = indexed(runtime)
    old_table = runtime.active["table"]
    old_provider = runtime._provider
    source_before = (runtime.root / item["path"]).read_bytes()
    config = changed_config(runtime)
    result = runtime.switch_embeddings(config, cutoff())
    assert result["status"] == "ok"
    assert result["reembedded"]
    assert old_provider.closed
    assert runtime.active["table"] != old_table
    assert old_table not in runtime.db.table_names()
    assert runtime._rows()[0]["text"] == "original material"
    assert len(runtime._rows()[0]["vector"]) == 4
    assert (runtime.root / item["path"]).read_bytes() == source_before
    result = runtime.search("original material")
    assert result["results"][0]["id"] == item["id"]
    assert factory.calls[-1][:2] == ("new-model", "query")


def test_switch_failure_keeps_old_active_provider_and_table(memory):
    runtime, factory = memory
    item = indexed(runtime)
    active_before = copy.deepcopy(runtime.active)
    old_provider = runtime._provider
    result = runtime.switch_embeddings(changed_config(runtime, "fail"), cutoff())
    assert result["status"] == "failed"
    assert result["active_unchanged"]
    assert runtime.status()["active"] == active_before
    assert not old_provider.closed
    assert factory.instances[-1].closed
    assert runtime.db.table_names() == [active_before["table"]]
    assert runtime.search("original material")["results"][0]["id"] == item["id"]


def test_published_pointer_is_never_deleted_after_fsync_failure(memory):
    runtime, _ = memory
    item = indexed(runtime)
    write_active = runtime._write_active
    def published_then_error(active):
        write_active(active)
        raise OSError("Injected directory fsync failure after replace")
    with patch.object(runtime, "_write_active", side_effect=published_then_error):
        result = runtime.switch_embeddings(changed_config(runtime), cutoff())
    assert result["status"] == "partial"
    assert result["switched"]
    assert runtime.status()["active"]["table"] in runtime.db.table_names()
    assert runtime.search("original material")["results"][0]["id"] == item["id"]


def test_multiple_runtime_instances_see_writes_and_profile_switch(memory):
    runtime, factory = memory
    other_factory = Factory()
    other = PCWRuntime(runtime.work_root, "project", provider_factory=other_factory)
    try:
        a = indexed(runtime)
        assert other.search("original material")["results"][0]["id"] == a["id"]
        old_other_provider = other._provider
        runtime.switch_embeddings(changed_config(runtime), cutoff())
        assert other.search("original material")["results"][0]["id"] == a["id"]
        assert other.active == runtime.active
        assert other_factory.calls[-1][0] == "new-model"
        assert old_other_provider.closed
        runtime.update(a["id"], "changed")
        assert other.search("original material")["results"] == []
        assert other.status()["pending_count"] == 1
    finally:
        other.close()


def test_unchanged_memory_uses_stat_cache_and_changed_body_is_detected(memory):
    runtime, _ = memory
    a = indexed(runtime)
    indexed(runtime, "b.md", "other")
    runtime.status()  # populate post-write file signatures and table-version token
    original_read = Path.read_bytes
    reads = []
    def record_read(path):
        reads.append(path)
        return original_read(path)
    with patch.object(Path, "read_bytes", record_read), patch.object(runtime, "_rows", wraps=runtime._rows) as rows:
        runtime.read(a["id"])
        runtime.status()
        assert not [path for path in reads if path.is_relative_to(runtime.knowledge)]
        assert rows.call_count == 0
        path = runtime.root / a["path"]
        path.write_text(path.read_text().replace("original material", "changed material"))
        assert runtime.read(a["id"])["content"] == "changed material"
        assert [path for path in reads if path.is_relative_to(runtime.knowledge)] == [path]
        assert rows.call_count == 1
    assert runtime.status()["pending_preparation"] == [a["id"]]


@pytest.mark.parametrize("number", [1e300, 1e-300])
def test_float32_overflow_or_zero_underflow_is_rejected(memory, number):
    runtime, _ = memory
    item = named(runtime, "huge.md", "source")
    provider = runtime._get_provider()
    with patch.object(provider, "embed", return_value=[[number] * 1024]):
        with pytest.raises(PCWError, match="float32"):
            runtime.submit_parts(item["id"], item["revision"], ["source"])
    assert runtime.table.count_rows() == 0


def test_lance_search_includes_fresh_rows_outside_vector_index(memory):
    runtime, _ = memory
    for index in range(5):
        indexed(runtime, f"indexed{index}.md", f"existing {index}")
    runtime.table.create_index(metric="cosine", index_type="IVF_FLAT", num_partitions=1)
    fresh = indexed(runtime, "fresh.md", "new unindexed original text")
    result = runtime.search("new unindexed original text", d_max=2, min_jump=10)
    assert result["results"][0]["id"] == fresh["id"]


def test_switch_blocks_other_runtime_write_until_activation(memory):
    runtime, factory = memory
    indexed(runtime)
    other = PCWRuntime(runtime.work_root, "project", provider_factory=Factory())
    entered, release, wrote = threading.Event(), threading.Event(), threading.Event()
    factory.on_embed = lambda: (entered.set(), release.wait(5))
    switch_result = []
    # Build config before starting callback: changed_config also acquires the lock.
    config = changed_config(runtime)
    switch_thread = threading.Thread(target=lambda: switch_result.append(runtime.switch_embeddings(config, cutoff())))
    switch_thread.start()
    assert entered.wait(5)
    write_thread = threading.Thread(target=lambda: (named(other, "after.md", "new"), wrote.set()))
    write_thread.start()
    assert not wrote.wait(.1)
    release.set()
    switch_thread.join(10)
    write_thread.join(10)
    assert wrote.is_set()
    assert switch_result[0]["status"] == "ok"
    other.close()


def test_save_subagent_result_is_exact_idempotent_and_requires_executor_session(memory):
    runtime, factory = memory
    result = "\n---\ninner: frontmatter stays in the result\n---\n\n| key | value |\n|---|---|\n| x | 1 |\n\n```py\nprint('exact')\n```\n  \n"
    with pytest.raises(PCWError, match="executor_session_id"):
        raw_result(runtime, "returned.md", result, "")
    saved = raw_result(runtime, "returned.md", result, "executor-session-17")
    assert saved["status"] == "saved"
    assert saved["id"] == "returned.md"
    assert saved["saved_at"].endswith("Z")
    assert saved["executor_session_id"] == "executor-session-17"
    read = runtime.read("returned.md")
    assert read["content"] == result
    assert read["saved_at"] == saved["saved_at"]
    duplicate = raw_result(runtime, "returned.md", result, "executor-session-17")
    assert duplicate["status"] == "already_saved"
    assert duplicate["saved_at"] == saved["saved_at"]
    with pytest.raises(PCWError, match="already occupied"):
        raw_result(runtime, "returned.md", result + "different", "executor-session-17")
    with pytest.raises(PCWError, match="actual executor"):
        raw_result(runtime, "returned.md", result, "other-executor-session")
    assert not factory.calls


def test_save_subagent_result_cas_revises_only_same_executor_raw_result(memory):
    runtime, factory = memory
    first_body = "# First raw return\n\n| state | first |\n| --- | --- |\n"
    saved = raw_result(runtime, "worker-return.md", first_body, "worker-session-17")
    runtime.submit_parts(saved["id"], saved["revision"], [first_body])
    moved = runtime.rename(saved["id"], "nested/worker-return.md")
    assert moved["path"] == "knowledge/nested/worker-return.md"
    related = named(runtime, "related.md", "Navigation target")
    runtime.links(saved["id"], add=[related["id"]])
    before = runtime.read(saved["id"])
    assert before["index_status"] == "indexed"

    second_body = "# Second raw return\n\n| state | updated |\n| --- | --- |\n"
    with pytest.raises(PCWError, match="already occupied"):
        raw_result(runtime, saved["id"], second_body, "worker-session-17")
    with pytest.raises(PCWError, match="actual executor"):
        raw_result(runtime, saved["id"], second_body, "other-session",
                                     expected_previous_revision=before["revision"])
    with pytest.raises(PCWError, match="changed since it was read"):
        raw_result(runtime, saved["id"], second_body, "worker-session-17",
                                     expected_previous_revision="stale-revision")

    updated = raw_result(runtime, saved["id"], second_body, "worker-session-17",
                                            expected_previous_revision=before["revision"])
    assert updated["status"] == "updated"
    assert updated["saved_at"] != before["saved_at"]
    assert updated["links"] == [related["id"]]
    assert updated["index_status"] == "pending_preparation"
    assert runtime.read(saved["id"])["content"] == second_body
    assert not [row for row in runtime._rows() if row["material_id"] == saved["id"]]
    assert len(factory.calls) == 1

    # Exact retries remain idempotent even when they still carry the revision
    # read before the successful CAS replacement.
    retry = raw_result(runtime, saved["id"], second_body, "worker-session-17",
                                         expected_previous_revision=before["revision"])
    assert retry["status"] == "already_saved"
    assert retry["saved_at"] == updated["saved_at"]

    ordinary = named(runtime, "ordinary.md", "ordinary knowledge")
    with pytest.raises(PCWError, match="not a saved raw subagent result"):
        raw_result(runtime, ordinary["id"], "new raw", "worker-session-17",
                                     expected_previous_revision=ordinary["revision"])


def test_save_subagent_result_cas_write_error_keeps_previous_body_and_index(memory):
    runtime, _ = memory
    original = raw_result(runtime, "worker-return.md", "first body", "worker-session-17")
    runtime.submit_parts(original["id"], original["revision"], ["first body"])
    before = runtime.read(original["id"])
    rows_before = runtime._rows()

    with patch.object(runtime, "_save", side_effect=OSError("injected raw-save failure")):
        with pytest.raises(OSError, match="injected raw-save failure"):
            raw_result(runtime, original["id"], "second body", "worker-session-17",
                                         expected_previous_revision=before["revision"])

    assert runtime.read(original["id"]) == before
    assert runtime._rows() == rows_before


def test_saved_result_lookup_survives_nested_path_rename(memory):
    runtime, _ = memory
    raw_result(runtime, "returned.md", "worker output", "executor-session-17", purpose="check")
    renamed = runtime.rename("returned.md", "nested/returned.md")
    assert renamed["id"] == "returned.md"
    workflow = AgentWorkflow(runtime)
    aid = runtime._test_assignments["returned.md"]
    runtime.read("returned.md", assignment_id=aid)

    process = workflow.action_requirements("process_result", {
        "result": {"assignment_id": aid, "material_name": "returned.md", "executor_session_id": "executor-session-17"},
        "assessment": {"status": "accepted", "reason": "Exact saved body observed"},
    })
    transition = workflow.action_requirements("transition", {
        "checks_due": {"status": "assigned", "checks": [{
            "assignment_id": aid, "material_name": "returned.md", "executor_session_id": "executor-session-17",
        }]},
    })
    finish = workflow.action_requirements("finish", {
        "acceptance_checks": {"status": "assigned", "scope": "whole task", "checks": [{
            "assignment_id": aid, "material_name": "returned.md", "executor_session_id": "executor-session-17",
        }]},
    })
    assert process["ready"] and transition["ready"]
    assert not finish["ready"]
    assert any(m["action"] == "prepare" for m in finish["missing"])

    wrong_session = workflow.action_requirements("process_result", {
        "result": {"material_name": "returned.md", "executor_session_id": "other-session"},
    })
    assert not wrong_session["ready"]


def test_same_filename_id_move_retries_only_index_path_after_failure(memory):
    runtime, factory = memory
    saved = raw_result(runtime, "returned.md", "worker output", "executor-session-17")
    runtime.submit_parts(saved["id"], saved["revision"], ["worker output"])
    before_rows = runtime._rows()
    calls = len(factory.calls)

    # _guard reopens LanceTable for every public call, so patch its class
    # method instead of one transient table instance.
    with patch("lancedb.table.LanceTable.update", side_effect=OSError("Injected index path failure")):
        partial = runtime.rename("returned.md", "nested/returned.md")
    assert partial["status"] == "partial"
    assert "index path update" in partial["repair"]
    assert not (runtime.root / "knowledge" / "returned.md").exists()
    assert (runtime.root / "knowledge" / "nested" / "returned.md").exists()
    assert len(list(runtime.knowledge.rglob("returned.md"))) == 1
    assert runtime.read("returned.md")["path"] == "knowledge/nested/returned.md"
    assert len(factory.calls) == calls

    fresh = PCWRuntime(runtime.work_root, "project", provider_factory=Factory())
    try:
        # _guard reconciliation repairs only the derived LanceDB path. Repeating
        # the same rename is idempotent once the material is already moved.
        moved = fresh.rename("returned.md", "nested/returned.md")
        assert moved["path"] == "knowledge/nested/returned.md"
        rows = fresh._rows()
        assert {row["path"] for row in rows if row["material_id"] == "returned.md"} == {"knowledge/nested/returned.md"}
        assert [row["vector"] for row in rows] == [row["vector"] for row in before_rows]
    finally:
        fresh.close()


def test_filename_is_id_plain_markdown_is_readable_and_duplicate_basenames_fail(memory):
    runtime, _ = memory
    created = named(runtime, "nested/context.md", "saved")
    assert created["id"] == "context.md"
    with pytest.raises(PCWError, match="filename ID"):
        named(runtime, "other/context.md", "must not create")
    plain = runtime.knowledge / "plain.md"
    plain.write_text("# Plain Markdown\n")
    assert runtime.read("plain.md")["content"] == "# Plain Markdown\n"
    duplicate = runtime.knowledge / "duplicate" / "plain.md"
    duplicate.parent.mkdir()
    duplicate.write_text("# Different\n")
    with pytest.raises(PCWError, match="Duplicate material filename ID: plain.md"):
        runtime.status()


def test_explicit_legacy_id_migration_preserves_body_links_and_existing_index(memory):
    runtime, factory = memory
    a_body = "# A\n\n| k | v |\n|---|---|\n| one | 1 |\n\n```py\nprint(1)\n```\n"
    b_body = "# B\n"
    (runtime.knowledge / "a.md").write_text(f"---\nid: old-a\nkind: evidence\nlinks: [old-b]\n---\n{a_body}")
    (runtime.knowledge / "b.md").write_text(f"---\nid: old-b\nlinks: []\n---\n{b_body}")
    runtime.status()
    dimensions = runtime.active["config"]["profile"]["dimensions"]
    runtime.table.add([
        {"material_id": "old-a", "part_index": 0, "text": a_body, "vector": [0.1] * dimensions,
         "path": "knowledge/a.md", "revision": hashlib.sha256(a_body.encode()).hexdigest()},
        {"material_id": "old-b", "part_index": 0, "text": b_body, "vector": [0.2] * dimensions,
         "path": "knowledge/b.md", "revision": hashlib.sha256(b_body.encode()).hexdigest()},
    ])
    migrated = runtime.migrate_legacy_ids()
    assert migrated["status"] == "ok"
    assert runtime.read("a.md")["content"] == a_body
    assert runtime.read("a.md")["links"] == ["b.md"]
    with pytest.raises(PCWError, match="Unknown"):
        runtime.read("old-a")
    assert {row["material_id"] for row in runtime._rows()} == {"a.md", "b.md"}
    assert [row["text"] for row in runtime._rows() if row["material_id"] == "a.md"] == [a_body]
    assert "id: old-a" not in (runtime.knowledge / "a.md").read_text()
    assert "kind: evidence" in (runtime.knowledge / "a.md").read_text()
    assert not factory.calls


def test_partial_legacy_id_migration_instructs_retry_not_reconcile(memory):
    runtime, _ = memory
    (runtime.knowledge / "a.md").write_text("---\nid: old-a\nlinks: []\n---\n# Body\n")
    runtime.status()
    original_save = runtime._save

    def fail_write(material):
        if material.id == "a.md":
            raise OSError("Injected migration write failure")
        original_save(material)

    with patch.object(runtime, "_save", side_effect=fail_write):
        result = runtime.migrate_legacy_ids()
    assert result["status"] == "partial"
    assert "pcw_migrate_legacy_ids" in result["repair"]
    assert "pcw_reconcile is diagnostic only" in result["repair"]


def test_legacy_id_migration_rejects_unresolved_links_without_writing(memory):
    runtime, _ = memory
    source = "---\nid: old-a\nlinks: [old-missing]\n---\n# Body\n"
    path = runtime.knowledge / "a.md"
    path.write_text(source)
    runtime.status()
    with pytest.raises(PCWError, match="cannot resolve links.*old-missing"):
        runtime.migrate_legacy_ids()
    assert path.read_text() == source
    assert runtime.read("a.md")["links"] == ["old-missing"]


def test_legacy_id_migration_validates_links_even_when_no_ids_need_translation(memory):
    runtime, _ = memory
    source = "---\nlinks: [missing.md]\n---\n# Body\n"
    path = runtime.knowledge / "a.md"
    path.write_text(source)
    runtime.status()
    with pytest.raises(PCWError, match="cannot resolve links.*missing.md"):
        runtime.migrate_legacy_ids()
    assert path.read_text() == source


def test_adopt_removes_legacy_id_preserves_extra_metadata_body_and_crlf(memory):
    runtime, _ = memory
    source = "---\r\nid: legacy-id\r\nkind: rule\r\n---\r\n# Body\r\nKeep [[old-link]] as written.\r\n"
    path = runtime.knowledge / "legacy.md"
    path.write_bytes(source.encode())
    assert runtime.status()["unregistered_count"] == 0
    adopted = runtime.adopt("legacy.md")
    assert adopted["id"] == "legacy.md"
    assert runtime.read("legacy.md")["content"] == "# Body\r\nKeep [[old-link]] as written.\r\n"
    assert "kind: rule" in path.read_text()
    assert "id: legacy-id" not in path.read_text()
    path = runtime.knowledge / "index.md"
    path.write_text("# Existing index\n")
    adopted = runtime.adopt("index.md")
    assert adopted["id"] == "index.md"
    assert runtime.read(adopted["id"])["content"] == "# Existing index\n"


def test_adopt_repairs_duplicate_self_links_without_global_lockout(memory):
    runtime, _ = memory
    a = named(runtime, "a.md", "a")
    b = named(runtime, "b.md", "b")
    path = runtime.root / a["path"]
    path.write_text(f"---\nid: {a['id']}\nlinks: [{a['id']}, {b['id']}, {b['id']}]\n---\na")
    assert runtime.status()["unregistered_count"] == 0
    assert runtime.adopt("a.md")["links"] == [b["id"]]


@pytest.mark.parametrize("path", ["../escape.md", "/tmp/escape.md", "a/../../escape.md", "a\\b.md", ".hidden.md", "a.txt"])
def test_knowledge_path_safety(memory, path):
    runtime, _ = memory
    with pytest.raises(PCWError):
        named(runtime, path, "forbidden")


def test_symlinks_and_workspace_traversal_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".pcw").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PCWError, match="Symlinks"):
        PCWRuntime(tmp_path, "project", provider_factory=Factory())
    with pytest.raises(PCWError):
        PCWRuntime(tmp_path, "../project", provider_factory=Factory())
    assert not list(outside.iterdir())


def test_list_is_paged_and_status_bounds_context(memory):
    runtime, _ = memory
    for index in range(55):
        named(runtime, f"{index:03}.md", f"material {index}")
    status = runtime.status()
    assert status["pending_count"] == 55
    assert len(status["pending_preparation"]) == 50
    page = runtime.list(limit=20)
    assert len(page["materials"]) == 20
    assert page["next_offset"] == 20
    assert len(runtime.list(offset=40, limit=20)["materials"]) == 15


def test_checkpoint_is_exact_and_restore_invalidates_changed_rows(memory):
    runtime, _ = memory
    a = indexed(runtime, "a.md", "version one")
    b = indexed(runtime, "b.md", "untouched")
    runtime._git("-c", "init.templateDir=", "init", ".")
    runtime._git("config", "user.name", "PCW isolated test")
    runtime._git("config", "user.email", "pcw-test@example.invalid")
    runtime._git("add", "--", "knowledge/b.md")
    result = runtime.checkpoint(["knowledge/a.md"], "Explicit isolated memory checkpoint")
    assert result["status"] == "ok"
    assert runtime._git("ls-tree", "-r", "--name-only", "HEAD").stdout.splitlines() == ["knowledge/a.md"]
    assert "knowledge/b.md" in runtime._git("diff", "--cached", "--name-only").stdout
    assert ".pcw-runtime" not in runtime._git("status", "--porcelain").stdout
    updated = runtime.update(a["id"], "version two")
    runtime.submit_parts(a["id"], updated["revision"], ["version two"])
    restored = runtime.restore(result["commit"], ["knowledge/a.md"])
    assert restored["status"] == "ok"
    assert restored["pending_preparation"] == [a["id"]]
    assert runtime.read(a["id"])["content"] == "version one"
    assert {row["material_id"] for row in runtime._rows()} == {b["id"]}
    with pytest.raises(PCWError, match="scope"):
        runtime.checkpoint([".pcw-runtime/active.json"], "forbidden")


def test_git_treats_wildcards_as_literal_paths(memory):
    runtime, _ = memory
    named(runtime, "a.md", "a")
    named(runtime, "b.md", "b")
    runtime._git("-c", "init.templateDir=", "init", ".")
    runtime._git("config", "user.name", "PCW isolated test")
    runtime._git("config", "user.email", "pcw-test@example.invalid")
    result = runtime.checkpoint(["knowledge/*.md"], "Should not glob")
    assert result["status"] == "partial"
    assert not runtime._git("ls-files").stdout.strip()


def test_link_only_restore_preserves_embedding_rows(memory):
    runtime, factory = memory
    a = indexed(runtime)
    b = indexed(runtime, "b.md", "b")
    runtime._git("-c", "init.templateDir=", "init", ".")
    runtime._git("config", "user.name", "PCW isolated test")
    runtime._git("config", "user.email", "pcw-test@example.invalid")
    checkpoint = runtime.checkpoint([a["path"]], "Initial body")
    runtime.links(a["id"], [b["id"]])
    calls = len(factory.calls)
    before_rows = runtime._rows()
    restored = runtime.restore(checkpoint["commit"], [a["path"]])
    assert restored["status"] == "ok"
    assert restored["pending_count"] == 0
    assert runtime.read(a["id"])["links"] == []
    assert len(factory.calls) == calls
    assert runtime._rows() == before_rows


def test_process_provider_pool_shares_model_across_workspaces_and_releases_safely(tmp_path):
    from pcw_runtime.provider_pool import ProviderPool
    factory = Factory()
    pool = ProviderPool(factory)
    a = PCWRuntime(tmp_path, "workspace-a", provider_factory=pool.acquire)
    b = PCWRuntime(tmp_path, "workspace-b", provider_factory=pool.acquire)
    try:
        indexed(a)
        indexed(b)
        assert len(factory.instances) == 1
        shared_provider = factory.instances[0]
        result = a.switch_embeddings(changed_config(a), cutoff())
        assert result["status"] == "ok"
        assert len(factory.instances) == 2
        assert not shared_provider.closed
        a.close()
        assert factory.instances[1].closed
        assert not shared_provider.closed
        assert b.search("original material")["results"]
        b.close()
        assert shared_provider.closed
        b.close()  # reference release is idempotent
    finally:
        a.close()
        b.close()

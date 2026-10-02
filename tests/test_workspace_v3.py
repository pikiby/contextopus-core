"""New contracts exercise real storage with the existing deterministic test provider."""
from importlib.resources import files
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from test_runtime import Factory
from pcw_runtime import PCWError, PCWRuntime
from pcw_runtime.cycles import CycleRuntime
from pcw_runtime.policies import policies
from pcw_runtime.workspaces import EMPTY_PROJECT


def create(runtime, **settings):
    text = files("pcw_runtime").joinpath("default_instructions.md").read_text()
    for name, value in settings.items():
        old = policies(text)[name]
        literal = lambda x: "null" if x is None else str(x).lower()
        text = text.replace(f"{name}: {literal(old)}", f"{name}: {literal(value)}")
    return runtime.workspace_create("create-project", text, EMPTY_PROJECT, "Create this test context with these settings")


@pytest.fixture
def workspace(tmp_path):
    runtime = CycleRuntime(tmp_path, "project", provider_factory=Factory())
    create(runtime)
    yield runtime
    runtime.close()


def test_unknown_workspace_never_created_by_opening(tmp_path):
    runtime = CycleRuntime(tmp_path, "missing", provider_factory=Factory())
    for call in (lambda: runtime.startup("start"), runtime.list, runtime.instructions_read,
                 lambda: runtime.search(query="anything"), lambda: runtime.read(material_id="one.md")):
        with pytest.raises(PCWError, match="does not exist"):
            call()
    assert not (tmp_path / ".pcw").exists()


def test_create_idempotent_no_models_and_read_without_cycle(tmp_path):
    factory = Factory()
    runtime = CycleRuntime(tmp_path, "project", provider_factory=factory)
    create(runtime)
    assert create(runtime)["replayed"]
    assert runtime.instructions_read()["content"]
    assert runtime.project_read()["content"] == EMPTY_PROJECT
    assert runtime.list()["total"] == 0
    assert runtime.search(query="facts")["results"] == []
    assert factory.instances == []
    assert not (runtime.engine.root / "tmp").exists()
    assert not runtime.record_path.exists()


def test_read_reports_stale_index_without_repair(workspace):
    item = workspace.engine.create("old knowledge")
    version = workspace.engine.table.version
    path = workspace.engine.root / item["path"]
    path.write_text(path.read_text().replace("old knowledge", "new knowledge"))
    assert workspace.read(material_id=item["id"])["content"] == "new knowledge"
    result = workspace.search(query="old", d_max=2)
    assert result["results"] == []
    assert result["pending_count"] == 1
    assert workspace.engine.table.version == version


def test_legacy_migration_preserves_every_source(tmp_path):
    engine = PCWRuntime(tmp_path, "old", provider_factory=Factory())
    item = engine.create("# Exact facts\n\nSource conditions retained.")
    path = engine.root / item["path"]
    text = path.read_bytes()
    instructions = "# My own rules\nNo inferred permissions.\n"
    (engine.root / "INSTRUCTIONS.md").write_text(instructions)
    (engine.root / "CURRENT.md").write_text("old task state")
    engine.close()
    runtime = CycleRuntime(tmp_path, "old", provider_factory=Factory())
    assert runtime.workspace_inspect()["format_version"] == 0
    with pytest.raises(PCWError, match="pcw-upgrade"):
        runtime.startup("start")
    plan = runtime.upgrade_plan()
    assert plan["project_description"]["status"] == "missing"
    result = runtime.upgrade_apply(plan["revision"], "Upgrade this workspace")
    assert result["status"] == "complete"
    assert result["project_description"]["status"] == "placeholder"
    replay = runtime.upgrade_apply(plan["revision"], "Retry")
    assert replay["replayed"]
    assert replay["project_description"]["status"] == "placeholder"
    assert path.read_bytes() == text
    assert runtime.instructions_read()["content"] == instructions
    assert (engine.root / "CURRENT.md").read_text() == "old task state"
    assert runtime.read(material_id=item["id"])["content"].startswith("# Exact facts")
    assert policies(instructions)["knowledge_approval_required"] is True
    assert policies(instructions)["allow_implicit_updates"] is False


def test_parallel_tasks_revision_conflicts_and_tmp_lifetime(workspace):
    a = workspace.startup("task-a")["cycle_id"]
    b = workspace.startup("task-b")["cycle_id"]
    first = workspace.current_create(a, "a", "First task")
    other = workspace.current_create(b, "b", "Second task")
    assert first["task_id"] != other["task_id"]
    changed = workspace.current_update(a, first["task_id"], first["revision"], {"verified_state": "Checked source"})
    with pytest.raises(PCWError, match="Current changed"):
        workspace.current_update(a, first["task_id"], first["revision"], {"next_step": "overwrite"})
    with pytest.raises(PCWError, match="not bound"):
        workspace.current_update(b, first["task_id"], changed["revision"], {"status": "completed"})
    workspace.tmp_write(b, "ongoing")
    workspace.proposal_prepare(a, [], no_changes_reason="No new knowledge after comparison")
    assert workspace.finish(a)["status"] == "closed"
    assert workspace.current_read(first["task_id"])["verified_state"] == "Checked source"
    assert workspace.tmp_list(b)["total"] == 1
    assert workspace.startup("resume-a", task_id=first["task_id"])["task_id"] == first["task_id"]


@pytest.mark.parametrize("implicit", [False, True])
@pytest.mark.parametrize("approval", [False, True])
def test_independent_permission_settings(tmp_path, implicit, approval):
    runtime = CycleRuntime(tmp_path, "p", provider_factory=Factory())
    create(runtime, allow_implicit_updates=implicit, knowledge_approval_required=approval)
    if not implicit:
        with pytest.raises(PCWError, match="explicit"):
            runtime.startup("implicit", invocation="implicit")
    cycle = runtime.startup("work", invocation="implicit" if implicit else "explicit")["cycle_id"]
    plan = runtime.proposal_prepare(cycle, [{"key": "fact", "content": "Verified fact"}])
    assert plan["approval_required"] is approval
    if approval:
        with pytest.raises(PCWError, match="confirmation"):
            runtime.proposal_apply(cycle, plan["proposal_id"], plan["revision"])
    assert runtime.proposal_apply(cycle, plan["proposal_id"], plan["revision"], confirmation="Approved" if approval else None)["status"] == "applied"


def test_project_review_and_audit_cannot_write(workspace):
    cycle = workspace.startup("project-work")["cycle_id"]
    before = workspace.project_read()
    plan = workspace.project_update(cycle, "# Project\nUser's accepted scope.\n", before["revision"], "Change the scope")
    assert workspace.project_read() == before
    result = workspace.project_apply(cycle, plan["proposal_id"], plan["revision"])
    assert "accepted scope" in result["project"]["content"]
    audit = workspace.startup("audit", purpose="audit")["cycle_id"]
    assert workspace.list(audit)["total"] == 0
    with pytest.raises(PCWError):
        workspace.project_update(audit, "x", result["project"]["revision"], "x")
    with pytest.raises(PCWError):
        workspace.proposal_prepare(audit, [{"key": "x", "content": "x"}])
    assert workspace.finish(audit)["status"] == "closed"


def test_optional_limit_rejects_before_write_and_labels_need_no_embedding(tmp_path):
    factory = Factory()
    runtime = CycleRuntime(tmp_path, "limited", provider_factory=factory)
    create(runtime, material_max_tokens=30)
    cycle = runtime.startup("work")["cycle_id"]
    oversized = runtime.proposal_prepare(cycle, [{"key": "large", "content": "x" * 31}])
    assert oversized["status"] == "needs_split"
    assert oversized["materials"][0]["tokens"] == 31
    assert runtime.list()["total"] == 0
    assert factory.calls == []
    plan = runtime.proposal_prepare(cycle, [
        {"key": "a", "content": "# Storage\nFacts", "description": "Storage mechanism", "links": ["@b"]},
        {"key": "b", "content": "# Recovery\nSteps", "description": "Recovering storage"}])
    runtime.proposal_apply(cycle, plan["proposal_id"], plan["revision"])
    a, b = (runtime.read(material_id=plan["created_ids"][key]) for key in ("a", "b"))
    assert a["link_targets"][0]["description"] == "Recovering storage"
    assert runtime.read(material_id=b["id"], from_id=a["id"])["title"] == "Recovery"
    with pytest.raises(PCWError, match="existing link"):
        runtime.read(material_id=a["id"], from_id=b["id"])
    calls = len(factory.calls)
    change = runtime.proposal_prepare(cycle, [{"material_id": b["id"], "expected_revision": b["revision"], "description": "Recovery conditions"}])
    assert change["review_changes"][0]["description_change"]["after"] == "Recovery conditions"
    runtime.proposal_apply(cycle, change["proposal_id"], change["revision"])
    assert len(factory.calls) == calls
    assert runtime.read(material_id=a["id"])["link_targets"][0]["description"] == "Recovery conditions"


def test_cold_process_can_read_proposal_link_labels(workspace):
    cycle = workspace.startup("work")["cycle_id"]
    first = workspace.engine.create("# Existing topic\nContent")
    plan = workspace.proposal_prepare(cycle, [{"key": "new", "content": "New facts", "links": [first["id"]]}])
    cold = CycleRuntime(workspace.engine.work_root, "project", provider_factory=Factory())
    assert cold.proposal_read(cycle, plan["proposal_id"])["review_changes"][0]["links_added"][0]["title"] == "Existing topic"
    cold.close()


def test_migration_interruption_keeps_backup_and_retries_same_operation(tmp_path):
    engine = PCWRuntime(tmp_path, "old", provider_factory=Factory())
    item = engine.create("Source unchanged")
    (engine.root / "INSTRUCTIONS.md").write_text("Custom rules")
    original = (engine.root / item["path"]).read_bytes()
    engine.close()
    runtime = CycleRuntime(tmp_path, "old", provider_factory=Factory())
    plan = runtime.upgrade_plan()
    write = runtime.engine._write
    def interrupt(path, content):
        write(path, content)
        if path.name == "PROJECT.md":
            raise OSError("lost project write acknowledgement")
    with patch.object(runtime.engine, "_write", side_effect=interrupt):
        with pytest.raises(OSError):
            runtime.upgrade_apply(plan["revision"], "Upgrade selected context")
    pending = json.loads((runtime.control.root / "migration.json").read_text())
    assert pending["status"] == "applying"
    assert not runtime._format_path().exists()
    assert (Path(pending["backup"]) / item["path"]).read_bytes() == original
    result = runtime.upgrade_apply(plan["revision"], "Resume the same migration")
    assert result["backup"] == pending["backup"]
    assert result["status"] == "complete"
    assert (runtime.engine.root / item["path"]).read_bytes() == original


def legacy_with_work(tmp_path):
    runtime = CycleRuntime(tmp_path, "old", provider_factory=Factory())
    create(runtime, knowledge_approval_required=True)
    pending = runtime.startup("consolidate-runbooks")["cycle_id"]
    runtime.tmp_write(pending, "# Contract procedures\nVerified source findings.")
    proposal = runtime.proposal_prepare(pending, [{"key": "new", "content": "# Contract setup\nExact procedure."}])
    saved = runtime.startup("retention-rules")["cycle_id"]
    runtime.tmp_write(saved, "# Storage retention\nVerified retention rules.")
    applied = runtime.proposal_prepare(saved, [{"key": "saved", "content": "# Retention\nSaved rules."}])
    runtime.proposal_apply(saved, applied["proposal_id"], applied["revision"], confirmation="Approve this text")
    # The preceding release has the same draft format, but no workspace format marker.
    runtime._format_path().unlink()
    (runtime.engine.root / "PROJECT.md").unlink()
    (runtime.engine.root / "current").rmdir()
    return runtime, pending, proposal, saved, applied


def test_upgrade_preserves_pending_and_applied_work_and_both_backup_trees(tmp_path):
    runtime, pending, proposal, saved, applied = legacy_with_work(tmp_path)
    before = runtime._source_files()
    control = runtime._migration_tree(runtime.control.root, control=True)
    plan = runtime.upgrade_plan()
    assert plan["ready"] and not plan["blockers"]
    work = {row["cycle_id"]: row for row in plan["pending_work"]}
    assert work[pending]["request_ids"] == ["consolidate-runbooks"]
    assert work[pending]["temporary_materials"][0]["title"] == "Contract procedures"
    assert work[pending]["proposals"][0]["state"] == "prepared"
    assert work[pending]["proposals"][0]["changes"][0]["title"] == "Contract setup"
    assert work[saved]["proposals"][0]["state"] == "applied"
    result = runtime.upgrade_apply(plan["revision"], "Upgrade without cancelling work")
    assert result["pending_work_preserved"] and result["status"] == "complete"
    after = runtime._source_files()
    assert all(after[path] == digest for path, digest in before.items())
    assert (Path(result["control_backup"]) / "cycles.json").read_bytes() == runtime.record_path.read_bytes()
    assert (Path(result["control_backup"]) / "material-ids.json").read_bytes() == (runtime.control.root / "material-ids.json").read_bytes()
    runtime._migration_verify_backup(result)
    assert result["control_sources"] == control
    assert runtime._records()["cycles"][pending]["state"] == "active"
    assert runtime._records()["cycles"][saved]["state"] == "active"
    assert not (runtime.engine.knowledge / proposal["created_ids"]["new"]).exists()
    # A cold process can continue the same review with the same revisions and approval requirement.
    runtime.close()
    cold = CycleRuntime(tmp_path, "old", provider_factory=Factory())
    current_plan = cold.upgrade_plan()
    assert current_plan["compatible"] and current_plan["changes"] == []
    assert current_plan["pending_work"] == plan["pending_work"]
    assert current_plan["project_description"]["status"] == "placeholder"
    unchanged = cold._source_files(), cold._migration_tree(cold.control.root, control=True)
    current_result = cold.upgrade_apply(current_plan["revision"], "Check current context")
    assert current_result["status"] == "current"
    assert current_result["pending_work"] == plan["pending_work"]
    assert current_result["project_description"]["status"] == "placeholder"
    assert unchanged == (cold._source_files(), cold._migration_tree(cold.control.root, control=True))
    read = cold.proposal_read(pending, proposal["proposal_id"])
    assert read["revision"] == proposal["revision"] and read["approval_required"]
    assert cold.tmp_list(pending)["total"] == 1
    with pytest.raises(PCWError, match="confirmation"):
        cold.proposal_apply(pending, proposal["proposal_id"], proposal["revision"])
    assert cold.proposal_apply(pending, proposal["proposal_id"], proposal["revision"], confirmation="Approve now")["status"] == "applied"
    assert cold.finish(pending)["status"] == "closed"
    assert cold.proposal_apply(saved, applied["proposal_id"], applied["revision"])["replayed"]
    assert cold.finish(saved)["status"] == "closed"
    cold.close()


@pytest.mark.parametrize("content,status", [
    (None, "missing"), ("\n \n", "empty"), (EMPTY_PROJECT, "placeholder"),
    ("# My project\nVerified purpose and boundaries.\n", "present"),
])
def test_current_format_reports_project_content_without_rewriting(workspace, content, status):
    path = workspace.engine.root / "PROJECT.md"
    if content is None:
        path.unlink()
    else:
        path.write_text(content)
    before = workspace._source_files(), workspace._migration_tree(workspace.control.root, control=True)
    plan = workspace.upgrade_plan()
    assert plan["compatible"] and plan["changes"] == []
    assert plan["project_description"] == {
        "path": "PROJECT.md", "status": status, "content_reviewed": False,
    }
    assert before == (workspace._source_files(), workspace._migration_tree(workspace.control.root, control=True))


def test_current_format_reports_damaged_unfinished_work(workspace):
    cycle = workspace.startup("pending-review")["cycle_id"]
    proposal = workspace.proposal_prepare(cycle, [{"key": "new", "content": "# Fact\nChecked."}])
    workspace._plan_path(cycle, proposal["proposal_id"]).unlink()
    plan = workspace.upgrade_plan()
    assert plan["compatible"] and plan["changes"] == []
    assert not plan["ready"] and plan["next_action"] == "inspect_blockers"
    assert plan["pending_work"][0]["cycle_id"] == cycle
    assert any(row["proposal_id"] == proposal["proposal_id"] for row in plan["blockers"])


@pytest.mark.parametrize("changed", ["tmp", "registry"])
def test_upgrade_review_detects_changes_to_work(tmp_path, changed):
    runtime, pending, proposal, _, _ = legacy_with_work(tmp_path)
    plan = runtime.upgrade_plan()
    if changed == "tmp":
        runtime.tmp_write(pending, "Another finding")
    else:
        records = runtime._records()
        records["cycles"][pending]["proposals"][proposal["proposal_id"]]["state"] = "discarded"
        runtime._persist(records)
    with pytest.raises(PCWError, match="changed since migration review"):
        runtime.upgrade_apply(plan["revision"], "Upgrade")
    assert not (runtime.control.root / "migration.json").exists()
    assert not runtime._format_path().exists()


@pytest.mark.parametrize("problem", ["missing_proposal", "unknown_kind", "closing"])
def test_upgrade_reports_incompatible_work_before_apply(tmp_path, problem):
    runtime, pending, proposal, _, _ = legacy_with_work(tmp_path)
    if problem == "missing_proposal":
        runtime._plan_path(pending, proposal["proposal_id"]).unlink()
    elif problem == "unknown_kind":
        records = runtime._records()
        records["cycles"][pending]["purpose"] = "future-purpose"
        runtime._persist(records)
    else:
        records = runtime._records()
        records["cycles"][pending]["state"] = "closing"
        runtime._persist(records)
    before = runtime.record_path.read_bytes()
    plan = runtime.upgrade_plan()
    assert not plan["ready"] and plan["next_action"] == "inspect_blockers"
    assert any(row["cycle_id"] == pending for row in plan["blockers"])
    with pytest.raises(PCWError, match="preflight blocked"):
        runtime.upgrade_apply(plan["revision"], "Upgrade")
    assert runtime.record_path.read_bytes() == before
    assert not runtime._format_path().exists()


def test_snapshot_interruption_resumes_same_backup_without_overwrite(tmp_path):
    runtime, _, _, _, _ = legacy_with_work(tmp_path)
    plan = runtime.upgrade_plan()
    copy = runtime._migration_copy
    def interrupt(source, target, manifest):
        copy(source, target, manifest)
        if target.name == "workspace":
            raise OSError("lost snapshot acknowledgement")
    with patch.object(runtime, "_migration_copy", side_effect=interrupt):
        with pytest.raises(OSError):
            runtime.upgrade_apply(plan["revision"], "Upgrade")
    operation = json.loads((runtime.control.root / "migration.json").read_text())
    first = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in Path(operation["backup"]).rglob("*") if p.is_file()}
    assert runtime.upgrade_plan()["resume_revision"] == plan["revision"]
    result = runtime.upgrade_apply(plan["revision"], "Retry same operation")
    assert result["backup"] == operation["backup"]
    assert all((p.read_bytes(), p.stat().st_mtime_ns) == values for p, values in first.items())
    assert len(list((runtime.control.root / "backups").iterdir())) == 1


def test_changed_work_after_interruption_blocks_resume(tmp_path):
    runtime, pending, _, _, _ = legacy_with_work(tmp_path)
    plan = runtime.upgrade_plan()
    write = runtime.engine._write
    def interrupt(path, content):
        write(path, content)
        if path.name == "PROJECT.md":
            raise OSError("interrupted")
    with patch.object(runtime.engine, "_write", side_effect=interrupt):
        with pytest.raises(OSError):
            runtime.upgrade_apply(plan["revision"], "Upgrade")
    runtime.tmp_write(pending, "Work changed while migration was interrupted")
    changed_plan = runtime.upgrade_plan()
    assert not changed_plan["ready"]
    assert changed_plan["resume_revision"] == plan["revision"]
    assert any("Source changed" in issue["reason"] for issue in changed_plan["blockers"])
    with pytest.raises(PCWError, match="Source changed"):
        runtime.upgrade_apply(plan["revision"], "Retry")
    assert not runtime._format_path().exists()


def test_backup_corruption_does_not_overwrite_or_mark_format_current(tmp_path):
    runtime, _, _, _, _ = legacy_with_work(tmp_path)
    plan = runtime.upgrade_plan()
    original = runtime._migration_verify_backup
    def corrupt(operation):
        (Path(operation["control_backup"]) / "cycles.json").write_text("corrupt")
        original(operation)
    with patch.object(runtime, "_migration_verify_backup", side_effect=corrupt):
        with pytest.raises(PCWError, match="backup verification failed"):
            runtime.upgrade_apply(plan["revision"], "Upgrade")
    with pytest.raises(PCWError, match="Retained backup changed"):
        runtime.upgrade_apply(plan["revision"], "Retry")
    assert not runtime._format_path().exists()


def test_audit_reports_evidence_and_preserves_all_files(workspace):
    a = workspace.engine.create("# Same\nBody")
    b = workspace.engine.create("# Same\nBody")
    path = workspace.engine.root / a["path"]
    path.write_text(path.read_text().replace("links: []", "links: [missing.md]"))
    before = {p: p.read_bytes() for p in workspace.engine.knowledge.rglob("*.md")}
    result = workspace.audit()
    problems = [issue for row in result["materials"] for issue in row["issues"]]
    assert {p["problem"] for p in problems} == {"duplicate_body", "missing_link_target"}
    assert all(p["fragment"] and p["basis"] for p in problems)
    assert before == {p: p.read_bytes() for p in workspace.engine.knowledge.rglob("*.md")}
    c = workspace.startup("audit-only", purpose="audit")["cycle_id"]
    rules = workspace.instructions_read()
    with pytest.raises(PCWError, match="Audit"):
        workspace.instructions_prepare(c, "New rules", rules["revision"], "Change rules")


def test_rework_split_redirects_links_and_keeps_whole_procedure(workspace):
    first = workspace.startup("initial")["cycle_id"]
    seed = workspace.proposal_prepare(first, [
        {"key": "mixed", "content": "# Storage\nConnect with A.\nRecovery requires B."},
        {"key": "entry", "content": "# Entry", "links": ["@mixed"]}])
    workspace.proposal_apply(first, seed["proposal_id"], seed["revision"])
    workspace.finish(first)
    c = workspace.startup("rework", purpose="rework")["cycle_id"]
    task = workspace.current_create(c, "rework-task", "Separate connection and recovery")
    old = workspace.read(c, seed["created_ids"]["mixed"])
    workspace.tmp_write(c, "Both facts and their conditions were retained in separate topics")
    plan = workspace.proposal_prepare(c, [
        {"material_id": old["id"], "expected_revision": old["revision"], "delete": True},
        {"key": "connection", "content": "# Connection\nConnect with A.", "description": "Connection procedure", "links": ["@recovery"]},
        {"key": "recovery", "content": "# Recovery\nRecovery requires B.", "description": "Recovery conditions"}],
        replacements={old["id"]: "@connection"})
    assert workspace.finish(c)["status"] == "blocked"
    workspace.proposal_apply(c, plan["proposal_id"], plan["revision"])
    assert workspace.read(material_id=seed["created_ids"]["entry"])["links"] == [plan["created_ids"]["connection"]]
    workspace.current_update(c, task["task_id"], task["revision"], {"status": "completed", "verified_state": "Conditions and incoming links preserved"})
    assert workspace.finish(c)["tmp_cleared"]
    assert workspace.current_read(task["task_id"])["status"] == "completed"

from unittest.mock import patch

from test_runtime import Factory
from test_workspace_v3 import create
from pcw_runtime.cycles import CycleRuntime


def apply(runtime, cycle, changes):
    plan = runtime.proposal_prepare(cycle, changes)
    return plan, runtime.proposal_apply(cycle, plan["proposal_id"], plan["revision"])


def test_automatic_history_tracks_permanent_files_only(tmp_path):
    runtime = CycleRuntime(tmp_path, "p", provider_factory=Factory())
    initial = create(runtime, git_history_enabled=True)
    assert initial["history"]["status"] == "committed"
    cycle = runtime.startup("work")["cycle_id"]
    runtime.current_create(cycle, "task", "Some task")
    runtime.tmp_write(cycle, "Some result")
    plan, result = apply(runtime, cycle, [{"key": "a", "content": "# Fact\nFirst"}])
    assert result["history"]["status"] == "committed"
    item = runtime.read(cycle, plan["created_ids"]["a"])
    _, unchanged = apply(runtime, cycle, [{"material_id": item["id"], "expected_revision": item["revision"], "content": item["content"]}])
    assert unchanged["history"]["status"] == "unchanged"
    assert len(runtime.history_list()["versions"]) == 2
    paths = runtime.engine._git("ls-tree", "--name-only", "-r", "HEAD").stdout.splitlines()
    assert sorted(paths) == sorted(["PROJECT.md", "INSTRUCTIONS.md", item["path"]])
    diff = runtime.history_diff(initial["history"]["commit"], result["history"]["commit"])
    assert "+First" in diff["diff"]
    assert "First" in runtime.history_read(paths=[item["path"]])["materials"][0]["text"]


def test_git_retry_uses_old_snapshot_and_commits_in_order(tmp_path):
    runtime = CycleRuntime(tmp_path, "p", provider_factory=Factory())
    create(runtime, git_history_enabled=True)
    cycle = runtime.startup("work")["cycle_id"]
    git = runtime._history_git

    def fail(*args, **kwargs):
        if "commit-tree" in args:
            raise OSError("injected Git failure")
        return git(*args, **kwargs)

    with patch.object(runtime, "_history_git", side_effect=fail):
        first, saved = apply(runtime, cycle, [{"key": "first", "content": "First captured state"}])
        assert saved["status"] == "applied"
        assert saved["history"]["status"] == "pending"
        second, saved_later = apply(runtime, cycle, [{"key": "second", "content": "Later independent state"}])
        assert saved_later["history"]["status"] == "pending"
    # Uncommitted external change must not enter either captured operation.
    first_path = runtime.engine.knowledge / first["created_ids"]["first"]
    first_path.write_text(first_path.read_text().replace("First captured state", "External later edit"))
    assert runtime.history_retry()["status"] == "committed"
    versions = runtime.history_list()["versions"]
    assert len(versions) == 3
    assert second["proposal_id"] in versions[0]["subject"]
    assert first["proposal_id"] in versions[1]["subject"]
    blob = runtime.history_read(commit=versions[1]["commit"], paths=["knowledge/" + first["created_ids"]["first"]])["materials"][0]["text"]
    assert "First captured state" in blob
    assert "External later edit" not in blob
    assert "External later edit" in first_path.read_text()
    assert len(runtime.history_list()["versions"]) == 3
    runtime.history_retry()
    assert len(runtime.history_list()["versions"]) == 3

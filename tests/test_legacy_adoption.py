"""Old sparse contexts are adopted only with reviewed explicit human rules."""

from importlib.resources import files
import subprocess
import pytest
from contextopus.modules.workspace.cycles import CycleRuntime
from contextopus.modules.workspace.runtime import _parse
from contextopus.core import relocation
from test_runtime import Factory


def sparse(root):
    context = root / ".pcw/old"
    (context / "knowledge").mkdir(parents=True)
    (context / "knowledge/topic.md").write_text("# Original\nLiteral source body.\n", encoding="utf-8", newline="")
    (context / "current.md").write_bytes(b"original ongoing task\r\n")
    (context / "tmp").mkdir()
    (context / "tmp/result.md").write_bytes(b"preserved draft\x00\xff")
    subprocess.run(["git", "init", "-q", str(context)], check=True)
    subprocess.run(
        ["git", "-C", str(context), "add", "current.md", "knowledge/topic.md"],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(context),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "Original",
        ],
        check=True,
    )
    head = subprocess.check_output(
        ["git", "-C", str(context), "rev-parse", "HEAD"], text=True
    ).strip()
    return context, head


@pytest.mark.parametrize("relocate_first", [False, True])
def test_sparse_legacy_needs_reviewed_rules_preserves_originals(
    tmp_path, relocate_first
):
    source = tmp_path / "source"
    source.mkdir()
    original, head = sparse(source)
    expected_current = (original / "current.md").read_bytes()
    expected_tmp = (original / "tmp/result.md").read_bytes()
    if relocate_first:
        relocation.apply(relocation.plan(source, tmp_path / "destination"))
    runtime = CycleRuntime(source, "old", provider_factory=Factory())
    try:
        initial = runtime.upgrade_plan()
        assert initial["from_version"] == 0
        assert initial["ready"] is False
        assert initial["instruction_initialization"]["status"] == "never_initialized"
        assert not (runtime.engine.root / "INSTRUCTIONS.md").exists()
        rules = (
            files("contextopus.modules.workspace")
            .joinpath("default_instructions.md")
            .read_text()
        )
        reviewed = runtime.upgrade_plan(instructions_content=rules)
        assert reviewed["ready"] is True
        assert reviewed["instruction_initialization"]["content"] == rules
        with pytest.raises(ValueError, match="confirmation"):
            runtime.upgrade_apply(
                reviewed["revision"], automatic=True, instructions_content=rules
            )
        with pytest.raises(ValueError, match="changed"):
            runtime.upgrade_apply(
                reviewed["revision"],
                automatic=True,
                instructions_content=rules + "\nDifferent rules",
                instructions_confirmation="Approved prior text",
            )
        result = runtime.upgrade_apply(
            reviewed["revision"],
            automatic=True,
            instructions_content=rules,
            instructions_confirmation="Approve this complete reviewed rules revision",
        )
        assert result["status"] == "complete"
        assert runtime.instructions_read()["content"] == rules
        assert not (runtime.engine.root / "current.md").exists()
        tasks = [m for m in runtime.list()["materials"] if m["type"] == "task"]
        assert len(tasks) == 1
        assert expected_current.decode().strip() in runtime.read(material_id=tasks[0]["id"])["content"]
        assert (runtime.engine.root / "tmp/result.md").read_bytes() == expected_tmp
        assert runtime.project_read()["status"] == "missing"
        material = next(m for m in runtime.list()["materials"] if m["type"] == "knowledge")
        assert (
            runtime.read(material_id=material["id"])["content"]
            == "# Original\nLiteral source body.\n"
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(runtime.engine.root),
                "merge-base",
                "--is-ancestor",
                head,
                "HEAD",
            ],
            check=True,
        )
        assert (
            runtime.upgrade_apply(reviewed["revision"], automatic=True)["replayed"]
            is True
        )
    finally:
        runtime.close()


def test_previously_initialized_lost_rules_are_not_replaced(tmp_path):
    original, head = sparse(tmp_path)
    runtime = CycleRuntime(tmp_path, "old", provider_factory=Factory())
    try:
        with runtime.control.guard():
            runtime.control.write(
                runtime.control.root / "instructions-initialized.json",
                '{"initialized":true}',
            )
        rules = (
            files("contextopus.modules.workspace")
            .joinpath("default_instructions.md")
            .read_text()
        )
        plan = runtime.upgrade_plan(instructions_content=rules)
        assert plan["ready"] is False
        assert plan["instruction_initialization"]["status"] == "lost_initialized_rules"
        with pytest.raises(ValueError, match="blocked"):
            runtime.upgrade_apply(
                plan["revision"],
                automatic=True,
                instructions_content=rules,
                instructions_confirmation="Replace the lost rules",
            )
        assert not (original / "INSTRUCTIONS.md").exists()
    finally:
        runtime.close()

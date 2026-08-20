from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "persistent-context-workspace"
SKILLS = PLUGIN / "skills"
PLUGIN_NAME = "persistent-context-workspace"
ENTRY_SKILLS = ("pcw", "pcw-run")
PUBLIC = "pcw"
OPERATIONS = (
    "pcw-resolve-workspace",
    "pcw-query-context",
    "pcw-open-cycle",
    "pcw-inspect-source",
    "pcw-map-source",
    "pcw-record-result",
    "pcw-promote-knowledge",
    "pcw-compact-current",
    "pcw-validate-memory",
    "pcw-checkpoint-memory",
    "pcw-prune-tmp",
)
REFERENCES = SKILLS / PUBLIC / "references"
OPERATIONS_DIR = REFERENCES / "operations"
REQUIRED_OPERATION_SECTIONS = (
    "## Preconditions",
    "## Inputs",
    "## Procedure",
    "## Output",
    "## Blockers",
    "## Idempotency",
)


def skill_text(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def operation_text(name: str) -> str:
    return (OPERATIONS_DIR / f"{name}.md").read_text(encoding="utf-8")


def frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        raise AssertionError("missing YAML frontmatter")
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            raise AssertionError(f"invalid frontmatter line: {line}")
        values[key.strip()] = value.strip()
    return values


class PluginContractTests(unittest.TestCase):
    def test_plugin_manifest(self) -> None:
        manifest = json.loads(
            (PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(PLUGIN_NAME, manifest["name"])
        self.assertEqual("0.2.0", manifest["version"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertEqual(PLUGIN_NAME, PLUGIN.name)
        self.assertIsInstance(manifest["interface"]["defaultPrompt"], list)

    def test_repository_marketplace_points_to_plugin(self) -> None:
        marketplace = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("persistent-context-workspace", marketplace["name"])
        entries = [entry for entry in marketplace["plugins"] if entry["name"] == PLUGIN_NAME]
        self.assertEqual(1, len(entries))
        entry = entries[0]
        self.assertEqual("local", entry["source"]["source"])
        self.assertEqual("./plugins/persistent-context-workspace", entry["source"]["path"])
        self.assertEqual("AVAILABLE", entry["policy"]["installation"])


class SkillContractTests(unittest.TestCase):
    def test_exactly_two_user_skills_exist(self) -> None:
        actual = {path.name for path in SKILLS.iterdir() if path.is_dir()}
        self.assertEqual(set(ENTRY_SKILLS), actual)

    def test_skill_frontmatter_is_minimal_and_named(self) -> None:
        for name in ENTRY_SKILLS:
            with self.subTest(skill=name):
                metadata = frontmatter(skill_text(name))
                self.assertEqual({"name", "description"}, set(metadata))
                self.assertEqual(name, metadata["name"])
                self.assertIn("natural-language", metadata["description"])

    def test_entry_skills_are_explicit_only(self) -> None:
        for name in ENTRY_SKILLS:
            with self.subTest(skill=name):
                openai_yaml = (SKILLS / name / "agents" / "openai.yaml").read_text(
                    encoding="utf-8"
                )
                self.assertIn("allow_implicit_invocation: false", openai_yaml)
                self.assertIn(f"${name}", openai_yaml)

    def test_templates_are_fully_replaced(self) -> None:
        for path in SKILLS.rglob("*"):
            if path.is_file():
                self.assertNotIn("TODO", path.read_text(encoding="utf-8"), str(path))

    def test_technical_operations_are_references_not_skills(self) -> None:
        self.assertEqual(
            {f"{name}.md" for name in OPERATIONS},
            {path.name for path in OPERATIONS_DIR.iterdir() if path.is_file()},
        )
        for name in OPERATIONS:
            with self.subTest(operation=name):
                text = operation_text(name)
                self.assertFalse(text.startswith("---\n"))
                for section in REQUIRED_OPERATION_SECTIONS:
                    self.assertIn(section, text)

    def test_both_skills_accept_natural_language(self) -> None:
        for name in ENTRY_SKILLS:
            with self.subTest(skill=name):
                text = skill_text(name)
                self.assertIn("natural language", text.replace("-", " "))
                self.assertIn("Ask only", text)
        combined = "\n".join(skill_text(name) for name in ENTRY_SKILLS)
        for obsolete in ("$pcw ask", "$pcw remember", "$pcw do", "$pcw sync"):
            self.assertNotIn(obsolete, combined)

    def test_pcw_manages_context_without_executing_it(self) -> None:
        text = skill_text("pcw")
        self.assertIn("Manage context without executing the source task", text)
        self.assertIn("create it only when", text)
        self.assertIn("For an existing workspace, run `pcw-query-context`", text)
        self.assertIn("Build or revise `current.md`", text)
        self.assertIn("Do not execute the task described by `current.md`", text)
        self.assertIn("pcw-inspect-source", text)
        self.assertIn("pcw-promote-knowledge", text)

    def test_pcw_run_requires_clean_current_first_execution(self) -> None:
        text = skill_text("pcw-run")
        self.assertIn("primary agent is only the user interface and authority boundary", text)
        self.assertIn("no inherited conversation turns", text)
        self.assertIn("reads `current.md` before any source inspection or delegation", text)
        self.assertIn("does not search `knowledge/` to repair missing task context", text)
        self.assertIn("context_insufficient", text)
        self.assertIn("clean_controller_unavailable", text)

    def test_query_context_is_read_only_and_visible(self) -> None:
        text = operation_text("pcw-query-context")
        self.assertIn("Remain read-only", text)
        self.assertIn("Do not create or recover a cycle", text)
        self.assertIn("output_state: context_selected", text)
        self.assertIn("cycle_id: null", text)

    def test_shared_contract_routes_every_internal_operation(self) -> None:
        state_machine = (REFERENCES / "state-machine.md").read_text(encoding="utf-8")
        for name in OPERATIONS:
            self.assertIn(name, state_machine)

    def test_entry_skills_use_verified_operation_reference_loader(self) -> None:
        for name in ENTRY_SKILLS:
            with self.subTest(skill=name):
                text = skill_text(name)
                self.assertIn("operations/<operation>.md", text)
                self.assertIn("not invocable skills", text)
                self.assertIn("shared_contract_unavailable", text)

    def test_shared_references_exist(self) -> None:
        for reference in ("workspace-contract.md", "state-machine.md", "agent-routing.md"):
            self.assertTrue((REFERENCES / reference).is_file())

    def test_knowledge_current_and_tmp_have_distinct_roles(self) -> None:
        contract = (REFERENCES / "workspace-contract.md").read_text(encoding="utf-8")
        self.assertIn("`knowledge/` is the only durable system memory", contract)
        for kind in ("object", "fact", "rule", "constraint", "blocker", "decision", "relation"):
            self.assertIn(kind, contract)
        self.assertIn("persistent compressed context and plan for one active task", contract)
        self.assertIn("transaction buffer", contract)
        self.assertIn("Nothing in `tmp/` is durable fact", contract)
        self.assertIn("exact absorbed cycle directory is then removed", contract)
        self.assertIn("`tmp/` directory itself remains", contract)

    def test_run_cannot_replan_current(self) -> None:
        run = skill_text("pcw-run")
        self.assertIn("do not change its task, scope, constraints, or plan independently", run)
        for name in ("pcw-promote-knowledge", "pcw-compact-current", "pcw-validate-memory"):
            with self.subTest(operation=name):
                self.assertIn("run_attempted_replan", operation_text(name))

    def test_fixture_current_has_required_shape_and_resolved_links(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "valid-memory"
        current = (fixture / "current.md").read_text(encoding="utf-8")
        headings = re.findall(r"^# .+$", current, re.MULTILINE)
        self.assertEqual(["# Current", "# References"], headings)
        self.assertIn("Task:", current)
        self.assertIn("Status:", current)
        links = re.findall(r"\[\[([^\]]+)\]\]", current)
        self.assertTrue(links)
        for link in links:
            self.assertTrue((fixture / f"{link}.md").is_file(), link)

    def test_all_fixture_wiki_links_resolve(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "valid-memory"
        for markdown in fixture.rglob("*.md"):
            text = markdown.read_text(encoding="utf-8")
            for link in re.findall(r"\[\[([^\]]+)\]\]", text):
                target = fixture / f"{link}.md" if "/" in link else markdown.parent / f"{link}.md"
                self.assertTrue(target.is_file(), f"{markdown}: {link}")

    def test_local_memory_transaction_is_automatic_and_exact(self) -> None:
        entries = "\n".join(skill_text(name) for name in ENTRY_SKILLS)
        checkpoint = operation_text("pcw-checkpoint-memory")
        prune = operation_text("pcw-prune-tmp")
        state_machine = (REFERENCES / "state-machine.md").read_text(encoding="utf-8")
        self.assertIn("automatic unless the user explicitly forbids", entries)
        self.assertNotIn("authorization_required", entries + checkpoint + state_machine)
        self.assertIn("explicitly forbade", checkpoint)
        self.assertIn("Without requesting separate permission", prune)
        self.assertIn("checkpoint_status: created", prune)
        self.assertIn("never use a wildcard", prune)
        self.assertIn("not a symlink", prune)

    def test_repository_text_is_english_only(self) -> None:
        cyrillic = re.compile(r"[\u0400-\u04FF]")
        text_suffixes = {".md", ".yaml", ".yml", ".json", ".py"}
        for path in ROOT.rglob("*"):
            if path.is_file() and ".git" not in path.parts and path.suffix in text_suffixes:
                self.assertIsNone(cyrillic.search(path.read_text(encoding="utf-8")), str(path))

    def test_operational_contracts_use_pcw_memory_root(self) -> None:
        paths = (
            skill_text("pcw"),
            skill_text("pcw-run"),
            (REFERENCES / "workspace-contract.md").read_text(encoding="utf-8"),
            operation_text("pcw-resolve-workspace"),
            operation_text("pcw-open-cycle"),
            (
                ROOT
                / "tests"
                / "fixtures"
                / "valid-memory"
                / "tmp"
                / "cycle-001"
                / "manifest.md"
            ).read_text(encoding="utf-8"),
        )
        for text in paths:
            self.assertIn(".pcw", text)


if __name__ == "__main__":
    unittest.main()

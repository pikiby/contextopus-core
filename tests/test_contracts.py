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
CURRENT_STATUSES = {"draft", "ready", "running", "blocked", "complete", "closed"}
OPERATIONS = (
    "pcw-resolve-workspace",
    "pcw-query-context",
    "pcw-inspect-source",
    "pcw-checkpoint-memory",
)
REMOVED_OPERATIONS = (
    "pcw-open-cycle",
    "pcw-map-source",
    "pcw-record-result",
    "pcw-promote-knowledge",
    "pcw-compact-current",
    "pcw-validate-memory",
    "pcw-prune-tmp",
)
REFERENCES = SKILLS / "pcw" / "references"
RUN_REFERENCES = SKILLS / "pcw-run" / "references"
OPERATIONS_DIR = REFERENCES / "operations"
FIXTURE = ROOT / "tests" / "fixtures" / "valid-memory"
TASK_FIELDS = (
    "Verbatim request:",
    "Required outcome:",
    "In scope:",
    "Out of scope:",
    "User constraints:",
    "Authority:",
    "Open questions:",
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


def required_reading(name: str) -> str:
    match = re.search(
        r"^## Required reading\n(.*?)(?=^## |\Z)",
        skill_text(name),
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"{name}: missing exact required-reading section")
    return match.group(1)


def required_paths(name: str) -> list[Path]:
    return [
        (SKILLS / name / link).resolve()
        for link in re.findall(r"\[[^\]]+\]\(([^)]+)\)", required_reading(name))
    ]


class PluginContractTests(unittest.TestCase):
    def test_plugin_manifest(self) -> None:
        manifest = json.loads(
            (PLUGIN / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        self.assertEqual(PLUGIN_NAME, manifest["name"])
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+(?:\+[a-z0-9.-]+)?$")
        base_version = manifest["version"].split("+", 1)[0]
        for document in ("README.md", "PLAN.md"):
            self.assertIn(
                f"Version {base_version}",
                (ROOT / document).read_text(encoding="utf-8"),
            )
        self.assertEqual("./skills/", manifest["skills"])
        self.assertIsInstance(manifest["interface"]["defaultPrompt"], list)

    def test_repository_marketplace_points_to_plugin(self) -> None:
        marketplace = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(PLUGIN_NAME, marketplace["name"])
        entries = [entry for entry in marketplace["plugins"] if entry["name"] == PLUGIN_NAME]
        self.assertEqual(1, len(entries))
        entry = entries[0]
        self.assertEqual("local", entry["source"]["source"])
        self.assertEqual("./plugins/persistent-context-workspace", entry["source"]["path"])
        self.assertEqual("AVAILABLE", entry["policy"]["installation"])


class SkillContractTests(unittest.TestCase):
    def test_exactly_two_explicit_user_skills_exist(self) -> None:
        actual = {path.name for path in SKILLS.iterdir() if path.is_dir()}
        self.assertEqual(set(ENTRY_SKILLS), actual)
        for name in ENTRY_SKILLS:
            with self.subTest(skill=name):
                metadata = frontmatter(skill_text(name))
                self.assertEqual({"name", "description"}, set(metadata))
                self.assertEqual(name, metadata["name"])
                self.assertIn("natural-language", metadata["description"])
                openai_yaml = (SKILLS / name / "agents" / "openai.yaml").read_text(
                    encoding="utf-8"
                )
                self.assertIn("allow_implicit_invocation: false", openai_yaml)
                self.assertIn(f"${name}", openai_yaml)

    def test_templates_are_fully_replaced(self) -> None:
        for path in SKILLS.rglob("*"):
            if path.is_file():
                self.assertNotIn("TODO", path.read_text(encoding="utf-8"), str(path))

    def test_only_four_technical_operation_references_remain(self) -> None:
        self.assertEqual(
            {f"{name}.md" for name in OPERATIONS},
            {path.name for path in OPERATIONS_DIR.iterdir() if path.is_file()},
        )
        for name in OPERATIONS:
            with self.subTest(operation=name):
                text = operation_text(name)
                self.assertFalse(text.startswith("---\n"))
                for section in ("## Inputs", "## Procedure", "## Output"):
                    self.assertIn(section, text)

    def test_removed_operations_have_no_runtime_references(self) -> None:
        for path in SKILLS.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            for removed in REMOVED_OPERATIONS:
                self.assertNotIn(removed, text, str(path))

    def test_required_reading_is_explicit_complete_and_resolved(self) -> None:
        common = {
            REFERENCES / "workspace-contract.md",
            REFERENCES / "agent-routing.md",
            OPERATIONS_DIR / "pcw-resolve-workspace.md",
            OPERATIONS_DIR / "pcw-inspect-source.md",
            OPERATIONS_DIR / "pcw-checkpoint-memory.md",
        }
        expected = {
            "pcw": common
            | {
                REFERENCES / "state-machine.md",
                OPERATIONS_DIR / "pcw-query-context.md",
            },
            "pcw-run": common | {RUN_REFERENCES / "state-machine.md"},
        }
        for name in ENTRY_SKILLS:
            with self.subTest(skill=name):
                paths = required_paths(name)
                self.assertEqual({path.resolve() for path in expected[name]}, set(paths))
                self.assertEqual(len(paths), len(set(paths)), "duplicate required document")
                for path in paths:
                    self.assertTrue(path.is_file(), str(path))
                    self.assertTrue(path.is_relative_to(SKILLS.resolve()), str(path))
                section = required_reading(name)
                self.assertRegex(section, r"(?i)(completely|in full|entire)")
                self.assertIn("shared_contract_unavailable", section)

    def test_mode_specific_reading_is_not_loaded_by_the_other_skill(self) -> None:
        pcw = set(required_paths("pcw"))
        run = set(required_paths("pcw-run"))
        self.assertNotIn((RUN_REFERENCES / "state-machine.md").resolve(), pcw)
        self.assertNotIn((REFERENCES / "state-machine.md").resolve(), run)
        self.assertNotIn((OPERATIONS_DIR / "pcw-query-context.md").resolve(), run)
        self.assertNotIn("pcw-query-context", skill_text("pcw-run"))

    def test_shared_documents_do_not_load_either_mode_workflow(self) -> None:
        for filename in ("workspace-contract.md", "agent-routing.md"):
            text = (REFERENCES / filename).read_text(encoding="utf-8")
            self.assertNotIn("state-machine.md", text, filename)
            self.assertNotIn("pcw-query-context", text, filename)

    def test_both_skills_accept_natural_language(self) -> None:
        for name in ENTRY_SKILLS:
            with self.subTest(skill=name):
                text = skill_text(name)
                self.assertIn("natural language", text.replace("-", " "))
        combined = "\n".join(skill_text(name) for name in ENTRY_SKILLS)
        for obsolete in ("$pcw ask", "$pcw remember", "$pcw do", "$pcw sync"):
            self.assertNotIn(obsolete, combined)

    def test_pcw_manages_context_without_executing_it(self) -> None:
        text = skill_text("pcw")
        self.assertIn("Manage context without executing the source task", text)
        for operation in ("pcw-query-context", "pcw-inspect-source", "pcw-checkpoint-memory"):
            self.assertIn(operation, text)
        self.assertIn("Do not execute the prepared task or mutate the source project", text)

    def test_clean_controller_is_a_run_specific_rule(self) -> None:
        text = skill_text("pcw-run") + (RUN_REFERENCES / "state-machine.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("fork_turns: none", text)
        self.assertIn("no inherited conversation", text)
        self.assertIn("clean_controller_unavailable", text)
        self.assertIn("reads Current completely before source inspection or delegation", text)
        self.assertIn("context_insufficient", text)
        self.assertIn("context_scope_conflict", text)
        self.assertIn("Do not pass chat summaries", text)
        self.assertNotIn("fork_turns", skill_text("pcw"))
        for name in ("workspace-contract.md", "agent-routing.md"):
            self.assertNotIn("fork_turns", (REFERENCES / name).read_text(encoding="utf-8"))

    def test_readers_remain_question_driven_and_compact(self) -> None:
        routing = (REFERENCES / "agent-routing.md").read_text(encoding="utf-8")
        self.assertIn("one exact question", routing)
        self.assertIn("knowledge index", routing)
        self.assertIn("compact", routing)
        self.assertIn("delegate bounded subquestions", routing)
        self.assertIn("caller does not receive every raw child report", routing)
        self.assertIn("Do not write intermediate reports to disk", routing)
        self.assertIn("do not audit a whole system", routing)
        for attribution in ("source attribution", "uncertainty", "out-of-scope"):
            self.assertIn(attribution, routing)

    def test_task_lock_preserves_user_meaning_and_provenance(self) -> None:
        contract = (REFERENCES / "workspace-contract.md").read_text(encoding="utf-8")
        editing = (REFERENCES / "state-machine.md").read_text(encoding="utf-8")
        for field in TASK_FIELDS:
            self.assertIn(field, contract)
        for provenance in ("`user`", "`derived`", "`fact`", "`unresolved`"):
            self.assertIn(provenance, editing)
        self.assertIn("a proposal stays a proposal", contract)
        self.assertIn("Only the user establishes or changes task meaning", contract)

    def test_current_and_knowledge_keep_distinct_durable_roles(self) -> None:
        contract = (REFERENCES / "workspace-contract.md").read_text(encoding="utf-8")
        self.assertIn("knowledge/", contract)
        self.assertIn("current.md", contract)
        self.assertIn("one active task", contract)
        for kind in ("object", "fact", "rule", "constraint", "blocker", "decision", "relation"):
            self.assertIn(kind, contract)

    def test_run_cannot_replan_current(self) -> None:
        text = skill_text("pcw-run") + (RUN_REFERENCES / "state-machine.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Task lock", text)
        self.assertIn("plan remain fixed", text)
        for boundary in ("scope", "authority", "constraints", "plan"):
            self.assertIn(boundary, text)

    def test_no_transaction_or_acceptance_fields_remain_in_runtime(self) -> None:
        for path in SKILLS.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            for field in (
                "cycle_id:",
                "semantic_acceptance:",
                "current.before.md",
                "promotion.md",
                "manifest.md",
                "receipts/",
            ):
                self.assertNotIn(field, text, str(path))

    def test_checkpoint_keeps_external_write_authority_boundary(self) -> None:
        checkpoint = operation_text("pcw-checkpoint-memory")
        for boundary in ("explicit", "push", "source", "forbid"):
            self.assertIn(boundary, checkpoint.lower())
        self.assertNotIn("validated", checkpoint)
        self.assertNotIn("semantic acceptance", checkpoint.lower())

    def test_current_status_contract_uses_the_exact_enum(self) -> None:
        contract = (REFERENCES / "workspace-contract.md").read_text(encoding="utf-8")
        status_line = re.search(r"^Status:\s*(.+)$", contract, re.MULTILINE)
        self.assertIsNotNone(status_line)
        self.assertEqual(
            CURRENT_STATUSES,
            {item.strip() for item in status_line.group(1).split("|")},
        )

    def test_operational_contracts_use_pcw_memory_root(self) -> None:
        for text in (
            (REFERENCES / "workspace-contract.md").read_text(encoding="utf-8"),
            operation_text("pcw-resolve-workspace"),
        ):
            self.assertIn(".pcw", text)

    def test_routine_work_does_not_require_runtime_review_or_tests(self) -> None:
        pcw = skill_text("pcw")
        run = skill_text("pcw-run")
        contract = (REFERENCES / "workspace-contract.md").read_text(encoding="utf-8")
        self.assertIn("Do not add a validation, review, rereading, comparison, or test phase", pcw)
        self.assertIn("only when it is itself requested by the user", pcw)
        self.assertIn("Do not add validation, semantic acceptance, comparison, or tests", run)
        self.assertIn("only when it is part of the explicit user task", run)
        self.assertIn("Do not add automatic validation", contract)

    def test_both_modes_persist_without_temporary_process_documents(self) -> None:
        contract = (REFERENCES / "workspace-contract.md").read_text(encoding="utf-8")
        self.assertIn("Neither entrypoint creates or uses `tmp/`", contract)
        self.assertIn("do not introduce a replacement process journal elsewhere", contract)
        self.assertIn("Leave them untouched unless the user separately requests their removal", contract)
        for name in ENTRY_SKILLS:
            self.assertIn("Do not create temporary process documents", skill_text(name))

    def test_repository_text_is_english_only(self) -> None:
        cyrillic = re.compile(r"[\u0400-\u04FF]")
        text_suffixes = {".md", ".yaml", ".yml", ".json", ".py"}
        paths = [ROOT / "README.md", ROOT / "PLAN.md"]
        for directory in (PLUGIN, ROOT / "tests", ROOT / ".agents"):
            paths.extend(directory.rglob("*"))
        for path in paths:
            if path.is_file() and path.suffix in text_suffixes:
                self.assertIsNone(cyrillic.search(path.read_text(encoding="utf-8")), str(path))


class MemoryFixtureTests(unittest.TestCase):
    def test_fixture_has_only_durable_memory_files(self) -> None:
        self.assertEqual(
            {
                "current.md",
                "knowledge/index.md",
                "knowledge/architecture.md",
                "knowledge/current-contract.md",
            },
            {path.relative_to(FIXTURE).as_posix() for path in FIXTURE.rglob("*") if path.is_file()},
        )

    def test_fixture_current_has_required_shape_and_resolved_links(self) -> None:
        current = (FIXTURE / "current.md").read_text(encoding="utf-8")
        headings = re.findall(r"^# .+$", current, re.MULTILINE)
        self.assertEqual(["# Current", "# References"], headings)
        self.assertIn("Task:", current)
        for field in TASK_FIELDS:
            self.assertIn(field, current)
        status_match = re.search(r"^Status:\s*(\S+)\s*$", current, re.MULTILINE)
        self.assertIsNotNone(status_match)
        self.assertIn(status_match.group(1), CURRENT_STATUSES)
        links = re.findall(r"\[\[([^\]]+)\]\]", current)
        self.assertTrue(links)
        for link in links:
            self.assertTrue((FIXTURE / f"{link}.md").is_file(), link)

    def test_current_knowledge_links_form_a_retrievable_graph(self) -> None:
        pending = re.findall(
            r"\[\[([^\]]+)\]\]", (FIXTURE / "current.md").read_text(encoding="utf-8")
        )
        visited: set[str] = set()
        while pending:
            link = pending.pop()
            if link in visited:
                continue
            visited.add(link)
            target = FIXTURE / f"{link}.md"
            self.assertTrue(target.is_file(), link)
            for child in re.findall(r"\[\[([^\]]+)\]\]", target.read_text(encoding="utf-8")):
                pending.append(child if "/" in child else f"knowledge/{child}")
        self.assertEqual({"knowledge/architecture", "knowledge/current-contract"}, visited)

    def test_all_fixture_wiki_links_resolve(self) -> None:
        for markdown in FIXTURE.rglob("*.md"):
            text = markdown.read_text(encoding="utf-8")
            for link in re.findall(r"\[\[([^\]]+)\]\]", text):
                target = FIXTURE / f"{link}.md" if "/" in link else markdown.parent / f"{link}.md"
                self.assertTrue(target.is_file(), f"{markdown}: {link}")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "persistent-context-workspace"
SKILLS = PLUGIN / "skills"
PLUGIN_NAME = "persistent-context-workspace"
PUBLIC = "pcw"
INTERNAL = (
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
REQUIRED_INTERNAL_SECTIONS = (
    "## Preconditions",
    "## Inputs",
    "## Procedure",
    "## Output",
    "## Blockers",
    "## Idempotency",
)


def skill_text(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


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
        self.assertEqual("0.1.6", manifest["version"])
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
    def test_expected_skill_set_exists(self) -> None:
        expected = {PUBLIC, *INTERNAL}
        actual = {path.name for path in SKILLS.iterdir() if path.is_dir()}
        self.assertEqual(expected, actual)

    def test_skill_frontmatter_is_minimal_and_named(self) -> None:
        for name in (PUBLIC, *INTERNAL):
            with self.subTest(skill=name):
                metadata = frontmatter(skill_text(name))
                self.assertEqual({"name", "description"}, set(metadata))
                self.assertEqual(name, metadata["name"])
                self.assertGreater(len(metadata["description"]), 60)

    def test_templates_are_fully_replaced(self) -> None:
        for path in SKILLS.rglob("*"):
            if path.is_file():
                self.assertNotIn("TODO", path.read_text(encoding="utf-8"), str(path))

    def test_internal_skills_have_narrow_contract_sections(self) -> None:
        for name in INTERNAL:
            text = skill_text(name)
            with self.subTest(skill=name):
                for section in REQUIRED_INTERNAL_SECTIONS:
                    self.assertIn(section, text)

    def test_only_public_pcw_allows_host_discovery(self) -> None:
        public_yaml = (SKILLS / PUBLIC / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("allow_implicit_invocation: true", public_yaml)
        self.assertIn(f"${PUBLIC}", public_yaml)
        for name in INTERNAL:
            with self.subTest(skill=name):
                openai_yaml = (SKILLS / name / "agents" / "openai.yaml").read_text(
                    encoding="utf-8"
                )
                self.assertIn("allow_implicit_invocation: false", openai_yaml)
                self.assertIn(f"${name}", openai_yaml)

    def test_public_interface_defines_exact_commands(self) -> None:
        text = skill_text(PUBLIC)
        metadata = frontmatter(text)
        for command in ("$pcw ask", "$pcw remember", "$pcw do", "$pcw sync"):
            self.assertIn(command, text)
        self.assertIn("first non-whitespace token is literal $pcw", metadata["description"])
        self.assertIn("Return `command_required`", text)
        self.assertIn("references/workspace-contract.md", text)
        self.assertIn("<skills-root>/<pcw-skill-name>/SKILL.md", text)
        self.assertIn("Never activate this interface for an ordinary prompt", text)
        self.assertIn("If no evidenced difference exists, report a read-only no-op", text)

    def test_query_context_is_read_only_and_visible(self) -> None:
        text = skill_text("pcw-query-context")
        self.assertIn("Remain read-only", text)
        self.assertIn("Do not create or recover a cycle", text)
        self.assertIn("# PCW context packet", text)
        self.assertIn("output_state: context_returned", text)
        self.assertIn("cycle_id: null", text)

    def test_main_contract_routes_every_internal_skill_by_name(self) -> None:
        text = skill_text(PUBLIC)
        for name in INTERNAL:
            self.assertIn(name, text)

    def test_main_blocks_completion_until_final_state_is_in_memory(self) -> None:
        text = skill_text(PUBLIC)
        self.assertIn("## Completion gate", text)
        self.assertIn("direct work by the primary agent as Worker activity", text)
        self.assertIn("external evidence that materially affected the result", text)
        self.assertIn("Compare `current.md` and relevant knowledge", text)
        self.assertIn("never call the PCW cycle complete", text)

    def test_main_returns_to_unresolved_work_after_memory(self) -> None:
        text = skill_text(PUBLIC)
        self.assertIn("## Return to unresolved work", text)
        self.assertIn("memory work as infrastructure", text)
        self.assertIn("resume it without asking the user to repeat the request", text)
        self.assertIn("explicitly cancel, replace, pause, or narrow", text)
        self.assertIn("Never resume from an agent-generated next action", text)

    def test_authorized_unfinished_work_is_current_state_not_next_action(self) -> None:
        current_contract = (
            SKILLS / PUBLIC / "references" / "workspace-contract.md"
        ).read_text(encoding="utf-8")
        state_machine = (
            SKILLS / PUBLIC / "references" / "state-machine.md"
        ).read_text(encoding="utf-8")
        self.assertIn("authorized unfinished operation", current_contract)
        self.assertIn("active state, not a next action", current_contract)
        self.assertIn("Memory state completion does not complete the user task", state_machine)
        for name in ("pcw-promote-knowledge", "pcw-compact-current", "pcw-validate-memory"):
            with self.subTest(skill=name):
                self.assertIn("authorized unfinished", skill_text(name))

    def test_main_uses_verified_sibling_file_loader(self) -> None:
        text = skill_text(PUBLIC)
        self.assertIn("Do not rely on implicit skill matching", text)
        self.assertIn("<skills-root>/<pcw-skill-name>/SKILL.md", text)
        self.assertIn("Canonicalize both paths", text)
        self.assertIn("frontmatter `name` exactly matches", text)
        self.assertIn("internal_skill_unavailable", text)

    def test_main_references_exist(self) -> None:
        main_dir = SKILLS / PUBLIC
        text = skill_text(PUBLIC)
        for reference in ("workspace-contract.md", "state-machine.md", "agent-routing.md"):
            self.assertIn(f"references/{reference}", text)
            self.assertTrue((main_dir / "references" / reference).is_file())

    def test_state_machine_contains_every_internal_operation(self) -> None:
        state_machine = (SKILLS / PUBLIC / "references" / "state-machine.md").read_text(
            encoding="utf-8"
        )
        for name in INTERNAL:
            self.assertIn(name, state_machine)

    def test_fixture_current_has_required_shape_and_resolved_links(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "valid-memory"
        current = (fixture / "current.md").read_text(encoding="utf-8")
        headings = re.findall(r"^# .+$", current, re.MULTILINE)
        self.assertEqual(["# Current", "# Pinned", "# References"], headings)
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
        main = skill_text(PUBLIC)
        checkpoint = skill_text("pcw-checkpoint-memory")
        prune = skill_text("pcw-prune-tmp")
        state_machine = (SKILLS / PUBLIC / "references" / "state-machine.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("automatic internal transaction", main)
        self.assertNotIn("authorization_required", main + checkpoint + state_machine)
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
            SKILLS / PUBLIC / "SKILL.md",
            SKILLS / PUBLIC / "references" / "workspace-contract.md",
            SKILLS / "pcw-resolve-workspace" / "SKILL.md",
            SKILLS / "pcw-open-cycle" / "SKILL.md",
            ROOT / "tests" / "fixtures" / "valid-memory" / "tmp" / "cycle-001" / "manifest.md",
        )
        for path in paths:
            self.assertIn(".pcw", path.read_text(encoding="utf-8"), str(path))


if __name__ == "__main__":
    unittest.main()

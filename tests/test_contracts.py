from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "persistent-context-workspace"
SKILL = PLUGIN / "skills" / "pcw"
FIXTURE = ROOT / "tests" / "fixtures" / "valid-memory"
LAUNCHER = PLUGIN / "scripts" / "launch.py"


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        raise AssertionError(f"missing frontmatter: {path}")
    result = {}
    for line in match[1].splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            raise AssertionError(f"invalid frontmatter: {path}")
        try:
            result[key] = json.loads(value.strip())
        except json.JSONDecodeError:
            result[key] = value.strip()
    return result


def server_tools() -> set[str]:
    tree = ast.parse((PLUGIN / "pcw_runtime" / "server.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_DESCRIPTIONS"
            for target in node.targets
        ):
            return {"pcw_" + name for name in ast.literal_eval(node.value)}
    raise AssertionError("server tool registry not found")


class PluginContractTests(unittest.TestCase):
    def test_package_versions_and_components_agree(self):
        manifest = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())
        package = tomllib.loads((PLUGIN / "pyproject.toml").read_text())
        self.assertEqual(PLUGIN.name, manifest["name"])
        self.assertEqual(manifest["name"], package["project"]["name"])
        self.assertEqual(manifest["version"], package["project"]["version"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertEqual("./.mcp.json", manifest["mcpServers"])
        for document in ("README.md", "PLAN.md"):
            self.assertIn(f"Version {manifest['version']}", (ROOT / document).read_text())
        self.assertTrue((PLUGIN / "pcw_runtime" / "__main__.py").is_file())
        self.assertTrue(LAUNCHER.is_file())

    def test_existing_marketplace_resolves_same_plugin(self):
        marketplace = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text())
        entries = [entry for entry in marketplace["plugins"] if entry["name"] == PLUGIN.name]
        self.assertEqual(1, len(entries))
        self.assertEqual("local", entries[0]["source"]["source"])
        self.assertEqual(PLUGIN.resolve(), (ROOT / entries[0]["source"]["path"]).resolve())

    def test_only_one_explicit_skill_is_packaged(self):
        self.assertEqual([SKILL / "SKILL.md"], sorted((PLUGIN / "skills").glob("*/SKILL.md")))
        metadata = frontmatter(SKILL / "SKILL.md")
        self.assertEqual("pcw", metadata["name"])
        self.assertTrue(metadata["description"].strip())
        ui = (SKILL / "agents" / "openai.yaml").read_text()
        self.assertIn("allow_implicit_invocation: false", ui)
        self.assertIn("$pcw", ui)
        prompts = json.loads((PLUGIN / ".codex-plugin" / "plugin.json").read_text())["interface"]["defaultPrompt"]
        self.assertTrue(all("$pcw" in prompt and "$pcw-run" not in prompt for prompt in prompts))

    def test_all_skill_references_resolve_inside_plugin(self):
        reached = {SKILL / "SKILL.md"}
        pending = list(reached)
        while pending:
            document = pending.pop()
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", document.read_text()):
                if "://" in target:
                    continue
                resolved = (document.parent / target.split("#", 1)[0]).resolve()
                self.assertTrue(resolved.is_relative_to(PLUGIN.resolve()), target)
                self.assertTrue(resolved.is_file(), target)
                if resolved not in reached:
                    reached.add(resolved)
                    pending.append(resolved)
        self.assertTrue(set((SKILL / "references").glob("*.md")) <= reached)

    def test_documented_tools_exist_in_runtime(self):
        documented = set()
        for path in SKILL.rglob("*.md"):
            documented.update(re.findall(r"\bpcw_[a-z_]+\b", path.read_text()))
        self.assertTrue(documented)
        self.assertEqual(set(), documented - server_tools())

    def test_packaged_docs_have_no_legacy_entrypoints_or_scaffolds(self):
        paths = [ROOT / "README.md", ROOT / "PLAN.md", *SKILL.rglob("*.md")]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("$pcw-run", text, str(path))
            self.assertNotIn("[TODO:", text, str(path))
            self.assertIsNone(re.search(r"[\u0400-\u04FF]", text), str(path))


class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        specification = importlib.util.spec_from_file_location("pcw_launcher_contract", LAUNCHER)
        cls.launcher = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(cls.launcher)

    def test_interpreter_override_and_stable_environment(self):
        self.assertEqual(Path("/custom/python"), self.launcher.interpreter_path({"PCW_PYTHON": "/custom/python"}))
        expected = Path("/custom/data/persistent-context-workspace/venv/bin/python")
        self.assertEqual(expected, self.launcher.interpreter_path({"XDG_DATA_HOME": "/custom/data"}))

    def test_missing_interpreter_fails_without_creating_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "not-installed" / "bin" / "python"
            environment = {**os.environ, "PCW_PYTHON": str(missing)}
            result = subprocess.run(
                [sys.executable, str(LAUNCHER)], env=environment,
                text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("Install the plugin dependencies", result.stderr)
            self.assertEqual("", result.stdout)
            self.assertEqual([], list(Path(directory).iterdir()))

    def test_missing_bootstrap_root_is_actionable(self):
        config = json.loads((PLUGIN / ".mcp.json").read_text())["mcpServers"]["pcw"]
        self.assertEqual("stdio", config["type"])
        environment = dict(os.environ)
        environment.pop("PLUGIN_ROOT", None)
        environment.pop("CLAUDE_PLUGIN_ROOT", None)
        result = subprocess.run(
            [sys.executable, *config["args"]], env=environment,
            text=True, capture_output=True, timeout=10,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("PLUGIN_ROOT", result.stderr)
        self.assertEqual("", result.stdout)

    def test_missing_dependencies_fail_with_installation_guidance(self):
        with tempfile.TemporaryDirectory() as directory:
            isolated = Path(directory) / "isolated"
            venv.EnvBuilder(with_pip=False).create(isolated)
            environment = {**os.environ, "PCW_PYTHON": str(isolated / "bin" / "python")}
            result = subprocess.run(
                [sys.executable, str(LAUNCHER)], env=environment,
                text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("Install the plugin package", result.stderr)
            self.assertEqual("", result.stdout)

    @unittest.skipUnless(
        importlib.util.find_spec("mcp") and importlib.util.find_spec("lancedb"),
        "Run in the installed runtime environment for the real stdio integration check",
    )
    def test_actual_packaged_stdio_initializes_and_lists_tools(self):
        config = json.loads((PLUGIN / ".mcp.json").read_text())["mcpServers"]["pcw"]
        for root_variable in ("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT"):
            with self.subTest(root_variable=root_variable), tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as cache:
                environment = {
                    **os.environ,
                    "PCW_PYTHON": sys.executable,
                    "HF_HUB_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
                environment.pop("PLUGIN_ROOT", None)
                environment.pop("CLAUDE_PLUGIN_ROOT", None)
                if root_variable == "CLAUDE_PLUGIN_ROOT":
                    active_plugin = Path(cache) / "installed plugin"
                    shutil.copytree(PLUGIN, active_plugin, ignore=shutil.ignore_patterns("__pycache__", ".venv", "*.egg-info"))
                else:
                    active_plugin = PLUGIN
                environment[root_variable] = str(active_plugin)
                process = subprocess.Popen(
                    [sys.executable, *config["args"]], env=environment, cwd=directory,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, bufsize=1,
                )

                def send(message):
                    process.stdin.write(json.dumps(message) + "\n")
                    process.stdin.flush()

                def receive(request_id):
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        ready, _, _ = select.select([process.stdout], [], [], max(0, deadline - time.monotonic()))
                        self.assertTrue(ready, "stdio response timed out")
                        line = process.stdout.readline()
                        self.assertTrue(line, "stdio closed before returning a response")
                        message = json.loads(line)
                        if message.get("id") == request_id:
                            self.assertNotIn("error", message)
                            return message["result"]
                    self.fail("stdio response timed out")

                try:
                    send({
                        "jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "pcw-contract-test", "version": "1"},
                        },
                    })
                    initialized = receive(1)
                    self.assertIn("tools", initialized["capabilities"])
                    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
                    send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
                    tools = receive(2)["tools"]
                    self.assertEqual(server_tools(), {tool["name"] for tool in tools})
                    for tool in tools:
                        schema = tool["inputSchema"]
                        self.assertTrue({"work_root", "workspace"} <= set(schema["required"]))
                    self.assertEqual([], list(Path(directory).iterdir()))
                finally:
                    if process.stdin:
                        process.stdin.close()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        process.wait(timeout=5)
                    process.stdout.close()
                    process.stderr.close()


class MemoryFixtureTests(unittest.TestCase):
    def test_material_ids_resolve_independently_of_filenames(self):
        paths = list((FIXTURE / "knowledge").glob("*.md"))
        records = {frontmatter(path)["id"]: (path, frontmatter(path)) for path in paths}
        self.assertEqual(len(paths), len(records))
        for material_id, (path, metadata) in records.items():
            self.assertNotEqual(path.stem, material_id)
            self.assertIsInstance(metadata["links"], list)
            self.assertEqual(len(metadata["links"]), len(set(metadata["links"])))
            self.assertNotIn(material_id, metadata["links"])
            self.assertTrue(set(metadata["links"]) <= records.keys())

    def test_current_focus_and_working_step_are_separate(self):
        current = frontmatter(FIXTURE / "current.md")
        self.assertEqual(1, current["pcw_current"])
        self.assertEqual({"pcw_current", "goal", "constraints", "completion", "step", "blocker"}, set(current))
        for field in ("goal", "constraints", "completion", "step", "blocker"):
            self.assertIsInstance(current[field], str)
        material_ids = {frontmatter(path)["id"] for path in (FIXTURE / "knowledge").glob("*.md")}
        self.assertTrue(any(material_id in current["step"] for material_id in material_ids))


if __name__ == "__main__":
    unittest.main()

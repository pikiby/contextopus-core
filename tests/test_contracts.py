from __future__ import annotations

import ast
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
SHELL_LAUNCHER = PLUGIN / "scripts" / "launch.sh"


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
        portable = json.loads((PLUGIN / "plugin.json").read_text())
        package = tomllib.loads((PLUGIN / "pyproject.toml").read_text())
        self.assertEqual(PLUGIN.name, manifest["name"])
        self.assertEqual(manifest["name"], package["project"]["name"])
        self.assertEqual(manifest["version"], package["project"]["version"])
        self.assertEqual("./skills/", manifest["skills"])
        self.assertEqual(manifest["name"], portable["name"])
        self.assertEqual(manifest["version"], portable["version"])
        self.assertEqual(manifest["interface"], portable["extensions"]["com.openai"]["interface"])
        self.assertEqual(manifest["skills"], portable["extensions"]["com.openai"]["skills"])
        self.assertNotIn("mcpServers", manifest)
        self.assertNotIn("mcpServers", portable["extensions"]["com.openai"])
        self.assertFalse((PLUGIN / ".mcp.json").exists())
        for document in ("README.md", "PLAN.md"):
            self.assertIn(f"Version {manifest['version']}", (ROOT / document).read_text())
        self.assertTrue((PLUGIN / "pcw_runtime" / "__main__.py").is_file())
        self.assertTrue(LAUNCHER.is_file())
        self.assertTrue(SHELL_LAUNCHER.is_file())

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
    def test_missing_interpreter_fails_without_creating_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "not-installed" / "bin" / "python"
            environment = {**os.environ, "PCW_PYTHON": str(missing)}
            result = subprocess.run(
                ["/bin/sh", str(SHELL_LAUNCHER)], env=environment,
                text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn(str(missing), result.stderr)
            self.assertEqual("", result.stdout)
            self.assertEqual([], list(Path(directory).iterdir()))

    def test_portable_mcp_declares_a_host_resolved_script_argument(self):
        document = json.loads((PLUGIN / "mcp.json").read_text())
        self.assertEqual("https://agent-plugins.org/schemas/1.0.0/mcp.schema.json", document["$schema"])
        config = document["mcpServers"]["pcw"]
        self.assertEqual("stdio", config["type"])
        self.assertEqual("sh", config["command"])
        self.assertEqual(["${PLUGIN_ROOT}/scripts/launch.sh"], config["args"])
        self.assertNotIn("env", config)

    def test_missing_dependencies_fail_with_installation_guidance(self):
        with tempfile.TemporaryDirectory() as directory:
            isolated = Path(directory) / "isolated"
            venv.EnvBuilder(with_pip=False).create(isolated)
            environment = {**os.environ, "PCW_PYTHON": str(isolated / "bin" / "python")}
            environment["PCW_DEPENDENCIES"] = str(Path(directory) / "packages")
            result = subprocess.run(
                ["/bin/sh", str(SHELL_LAUNCHER)], env=environment,
                text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(3, result.returncode)
            self.assertIn("mcp", result.stderr)
            self.assertEqual("", result.stdout)
            self.assertFalse((Path(directory) / "packages").exists())

    def test_launcher_stdio_initializes_and_lists_tools(self):
        check = subprocess.run(
            ["/bin/sh", str(SHELL_LAUNCHER), "--check"],
            env={**os.environ, "PCW_PYTHON": sys.executable},
            text=True, capture_output=True, timeout=30,
        )
        if check.returncode == 3:
            self.skipTest("Selected runtime dependencies are unavailable; real stdio integration was not run")
        self.assertEqual(0, check.returncode, check.stdout + check.stderr)
        imports = subprocess.run(
            ["/bin/sh", str(SHELL_LAUNCHER), "--check-imports"],
            env={**os.environ, "PCW_PYTHON": sys.executable},
            text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(0, imports.returncode, imports.stdout + imports.stderr)
        for explicit in (False, True):
            with self.subTest(explicit_python=explicit), tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as cache:
                environment = {
                    **os.environ,
                    "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""),
                    "HF_HUB_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
                environment.pop("PLUGIN_ROOT", None)
                environment.pop("CLAUDE_PLUGIN_ROOT", None)
                if explicit:
                    environment["PCW_PYTHON"] = sys.executable
                else:
                    environment.pop("PCW_PYTHON", None)
                active_plugin = Path(cache) / "installed plugin with spaces"
                shutil.copytree(PLUGIN, active_plugin, ignore=shutil.ignore_patterns("__pycache__", ".venv", "*.egg-info", "build"))
                process = subprocess.Popen(
                    ["/bin/sh", str(active_plugin / "scripts" / "launch.sh")], env=environment, cwd=directory,
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
                    schemas = {tool["name"]: tool["inputSchema"] for tool in tools}
                    for removed in ("pcw_create", "pcw_update", "pcw_delete", "pcw_links", "pcw_merge", "pcw_restore"):
                        self.assertNotIn(removed, schemas)
                    self.assertIn("expected_revision", schemas["pcw_proposal_apply"]["required"])
                    self.assertIn("confirmation", schemas["pcw_proposal_apply"]["required"])
                    self.assertNotIn("confirmation", schemas["pcw_finish"]["properties"])
                    self.assertIn("no_changes_reason", schemas["pcw_proposal_prepare"]["properties"])
                    for name, schema in schemas.items():
                        if name != "pcw_startup":
                            self.assertIn("cycle_id", schema["required"])
                    self.assertNotIn("pcw_environment_check", schemas)
                    self.assertNotIn("pcw_assignment_prepare", schemas)
                    self.assertNotIn("pcw_submit_parts", schemas)
                    self.assertIn("chunking", schemas["pcw_switch_embeddings"]["properties"])
                    request_id = 2
                    cycle_id = None

                    def call(name, **arguments):
                        nonlocal request_id
                        request_id += 1
                        send({"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {
                            "name": "pcw_" + name, "arguments": {"work_root": directory, "workspace": "protocol",
                            **({"cycle_id": cycle_id} if cycle_id and name != "startup" else {}), **arguments}}})
                        response = receive(request_id)
                        self.assertFalse(response.get("isError"), response)
                        return json.loads(response["content"][0]["text"])

                    opened = call("startup", request_id="protocol-invocation")
                    cycle_id = opened["cycle_id"]
                    self.assertEqual(0, opened["materials"])
                    self.assertEqual("blocked", call("finish")["status"])
                    self.assertEqual("no_changes", call("proposal_prepare", changes=[],
                                     no_changes_reason="No results yet; this fixture has no permanent changes.")["status"])
                    pending = call("tmp_write", content="Protocol fixture content")
                    self.assertEqual("blocked", call("finish")["status"])
                    self.assertEqual(0, call("status")["materials"])
                    proposal = call("proposal_prepare", changes=[{"key": "fixture", "content": "Protocol fixture content"}])
                    self.assertEqual("Protocol fixture content", proposal["review_changes"][0]["body_changes"][0]["after"])
                    review = call("proposal_read", proposal_id=proposal["proposal_id"])
                    self.assertIn("Protocol fixture content", review["review"])
                    self.assertEqual(proposal["review_changes"], review["review_changes"])
                    applied = call("proposal_apply", proposal_id=proposal["proposal_id"],
                                   expected_revision=proposal["revision"], confirmation="Apply the displayed fixture")
                    item = applied["materials"][0]
                    self.assertRegex(item["id"], r"^[a-f0-9]{32}\.md$")
                    self.assertEqual("Protocol fixture content", call("read", material_id=item["id"])["content"])
                    second = call("proposal_prepare", changes=[{"key": "related", "content": "Related fact", "links": [item["id"]]}])
                    other = call("proposal_apply", proposal_id=second["proposal_id"], expected_revision=second["revision"],
                                 confirmation="Apply the displayed related fact")["materials"][0]
                    self.assertEqual([item["id"]], call("read", material_id=other["id"])["links"])
                    current = call("current_set", goal="Protocol memory", constraints="Temporary files", completion="Saved", step="Done", blocker="")
                    self.assertEqual("saved", current["status"])
                    self.assertEqual("Protocol memory", call("current_get")["goal"])
                    self.assertEqual("Protocol fixture content", call("tmp_read", material_id=pending["id"])["content"])
                    shutil.rmtree(Path(directory) / ".pcw/protocol/.pcw-runtime")
                    self.assertEqual("recovery_required", call("status")["status"])
                    self.assertEqual("recovered", call("recover_workspace")["status"])
                    self.assertEqual("Protocol fixture content", call("read", material_id=item["id"])["content"])
                    # Embeddings may be pending in this strictly offline protocol test.
                    closed = call("finish", cancel=True)
                    self.assertEqual("cancelled", closed["status"])
                    self.assertFalse((Path(directory) / ".pcw/protocol/tmp" / cycle_id).exists())
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
    def test_filename_ids_are_unique_and_links_are_filename_ids(self):
        paths = list((FIXTURE / "knowledge").glob("*.md"))
        records = {path.name: (path, frontmatter(path)) for path in paths}
        self.assertEqual(len(paths), len(records))
        for material_id, (path, metadata) in records.items():
            self.assertIsInstance(metadata["links"], list)
            self.assertEqual(len(metadata["links"]), len(set(metadata["links"])))
            self.assertNotIn(material_id, metadata["links"])
            self.assertTrue(set(metadata["links"]) <= records.keys())
            self.assertNotIn("id", metadata)
            self.assertEqual(material_id, path.name)

    def test_current_is_readable_five_section_markdown(self):
        current = (FIXTURE / "current.md").read_text(encoding="utf-8")
        self.assertFalse(current.startswith("---\n"))
        sections = re.findall(r"^# (.+)$", current, re.MULTILINE)
        self.assertEqual(["Goal", "Constraints", "Completion", "Current step", "Blocker"], sections)
        self.assertIn("current-contract.md", current)


if __name__ == "__main__":
    unittest.main()

"""Opt-in integration through Codex itself; no model turns or manual root env.

PCW_TEST_CODEX=1 requires a locally installed matching PCW candidate.
PCW_TEST_QWEN=1 additionally exercises the already provisioned local model.
Only temporary knowledge is changed. No plugin/config installation is done here.

Before the host starts, the installed candidate is compared with the source
package, including the skill and references. A working old cache is not
release evidence.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import tomllib
import unittest


PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "persistent-context-workspace"
PLUGIN_ID = "persistent-context-workspace@persistent-context-workspace"


class CodexHost:
    def __init__(self, environment, work, notification_sink=None, server_request_sink=None,
                 server_decision_sink=None, server_request_handler=None, notification_observer=None):
        settings_path = Path.home() / ".codex" / "config.toml"
        settings = tomllib.loads(settings_path.read_text()) if settings_path.exists() else {}
        names = set(settings.get("plugins", {})) | {PLUGIN_ID}
        plugin_policy = "{" + ",".join(
            json.dumps(name) + "={enabled=" + ("true" if name == PLUGIN_ID else "false") + "}"
            for name in sorted(names)
        ) + "}"
        self.messages = queue.Queue()
        self.notifications = []
        self.notification_sink = Path(notification_sink) if notification_sink else None
        self.server_request_sink = Path(server_request_sink) if server_request_sink else None
        self.server_decision_sink = Path(server_decision_sink) if server_decision_sink else None
        self.server_request_handler = server_request_handler
        self.notification_observer = notification_observer
        self.notification_observer_errors = []
        self._notifications_changed = threading.Condition()
        self._write_lock = threading.Lock()
        self.request_id = 0
        self.errors = tempfile.TemporaryFile(mode="w+")
        self.process = subprocess.Popen(
            ["codex", "-c", "mcp_servers={}", "-c", "plugins=" + plugin_policy,
             "-c", "features.apps=false", "app-server", "--stdio"],
            env=environment, cwd=work, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.errors, text=True, bufsize=1,
        )
        threading.Thread(target=self._read, daemon=True).start()

    @staticmethod
    def _append_jsonl(path, value):
        """Append one complete, synced trace record before handling the next event."""
        if not path:
            return
        with path.open("a", encoding="utf-8") as sink:
            sink.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
            sink.flush()
            os.fsync(sink.fileno())

    def _server_request_response(self, request):
        """Return a narrow response; callers must opt in to any approval."""
        if self.server_request_handler is None:
            return {"error": {"code": -32601, "message": "Unexpected server request in PCW host test"}}
        try:
            response = self.server_request_handler(request)
        except Exception as error:  # The app-server must not be left waiting on test code.
            return {"error": {"code": -32603, "message": "PCW request policy failed: " + str(error)}}
        if not isinstance(response, dict) or not ("result" in response or "error" in response):
            return {"error": {"code": -32603, "message": "PCW request policy returned no JSON-RPC response"}}
        return response

    def _handle_server_request(self, request):
        self._append_jsonl(self.server_request_sink, request)
        response = self._server_request_response(request)
        message = {"id": request["id"], **response}
        self._append_jsonl(self.server_decision_sink, message)
        self.send(message)

    def _read(self):
        try:
            for line in self.process.stdout:
                message = json.loads(line)
                if "method" in message and "id" not in message:
                    with self._notifications_changed:
                        self.notifications.append(message)
                        self._append_jsonl(self.notification_sink, message)
                        if self.notification_observer:
                            try:
                                # The notification is already durable in the
                                # raw trace before an observer can act on it.
                                self.notification_observer(message, len(self.notifications) - 1)
                            except Exception as error:
                                self.notification_observer_errors.append(str(error))
                        self._notifications_changed.notify_all()
                elif "method" in message and "id" in message:
                    self._handle_server_request(message)
                else:
                    self.messages.put(message)
        except Exception as error:
            self.messages.put(error)
        finally:
            self.messages.put(EOFError("Codex app-server closed stdout"))

    def send(self, message):
        with self._write_lock:
            self.process.stdin.write(json.dumps(message) + "\n")
            self.process.stdin.flush()

    def call(self, method, params, timeout=60):
        self.request_id += 1
        request_id = self.request_id
        self.send({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            try:
                message = self.messages.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty as error:
                raise TimeoutError("Codex did not answer " + method) from error
            if isinstance(message, Exception):
                self.errors.seek(0)
                raise RuntimeError(str(message) + "\n" + self.errors.read()[-4000:]) from message
            if message.get("id") == request_id and "method" not in message:
                if "error" in message:
                    raise AssertionError({"method": method, "error": message["error"]})
                return message["result"]

    def notification_snapshot(self):
        """Return observed server notifications without consuming trace evidence."""
        with self._notifications_changed:
            return list(self.notifications)

    def stderr_tail(self):
        """Read a diagnostic copy before close without exposing configuration."""
        self.errors.seek(0)
        return self.errors.read()[-8000:]

    def wait_notification(self, predicate, timeout=60):
        """Wait for a server notification while retaining it in the trace."""
        deadline = time.monotonic() + timeout
        with self._notifications_changed:
            while True:
                for notification in self.notifications:
                    if predicate(notification):
                        return notification
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Codex did not emit the expected notification")
                self._notifications_changed.wait(remaining)

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process.stdin.close()
        self.process.stdout.close()
        self.errors.close()


@unittest.skipUnless(os.environ.get("PCW_TEST_CODEX") == "1", "Set PCW_TEST_CODEX=1 for real Codex host integration")
class CodexHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("codex"):
            raise AssertionError("PCW_TEST_CODEX requires the actual Codex CLI")
        environment = dict(os.environ)
        for name in ("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "PCW_PYTHON", "PCW_DEPENDENCIES"):
            environment.pop(name, None)
        environment.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(["codex", "mcp", "get", "pcw", "--json"], env=environment,
                                text=True, capture_output=True, timeout=30, check=True)
        cls.configuration = json.loads(result.stdout)
        cls.transport = cls.configuration["transport"]
        assert cls.transport["command"] == "sh", cls.transport
        assert len(cls.transport["args"]) == 1, cls.transport
        cls.launcher = Path(cls.transport["args"][0])
        assert cls.launcher.is_absolute() and cls.launcher.is_file(), cls.transport
        assert "${" not in str(cls.launcher), cls.transport
        installed = json.loads((cls.launcher.parents[1] / "plugin.json").read_text())
        source = json.loads((PLUGIN / "plugin.json").read_text())
        assert installed["name"] == source["name"]
        assert installed["version"].split("+")[0] == source["version"].split("+")[0]
        cls.installed_root = cls.launcher.parents[1]
        cls._assert_candidate_parity()
        cls.temporary = tempfile.TemporaryDirectory(prefix="pcw actual codex ")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.work = cls.temporary.name
        cls.host = CodexHost(environment, cls.work)
        cls.addClassCleanup(cls.host.close)
        cls.host.call("initialize", {
            "clientInfo": {"name": "pcw_host_regression", "version": "1"},
            "capabilities": {"experimentalApi": True},
        })
        cls.host.send({"method": "initialized", "params": {}})
        thread = cls.host.call("thread/start", {
            "cwd": cls.work, "ephemeral": True, "approvalPolicy": "never", "sandbox": "workspace-write",
        })
        cls.thread_id = thread["thread"]["id"]

    def tool(self, name, **arguments):
        result = self.host.call("mcpServer/tool/call", {
            "threadId": self.thread_id, "server": "pcw", "tool": "pcw_" + name,
            "arguments": {"work_root": self.work, "workspace": "regression", **arguments},
        })
        self.assertFalse(result.get("isError"), result)
        if result.get("structuredContent") is not None:
            return result["structuredContent"]
        return json.loads(next(part["text"] for part in result["content"] if part["type"] == "text"))

    @classmethod
    def _candidate_files(cls):
        """All source files that determine PCW's host behavior or instructions."""
        fixed = [
            PLUGIN / "plugin.json",
            PLUGIN / ".codex-plugin" / "plugin.json",
            PLUGIN / "mcp.json",
            PLUGIN / "pyproject.toml",
        ]
        trees = (PLUGIN / "pcw_runtime", PLUGIN / "scripts", PLUGIN / "skills")
        return sorted(
            [path for path in fixed if path.is_file()] +
            [path for tree in trees if tree.is_dir() for path in tree.rglob("*")
             if path.is_file() and "__pycache__" not in path.parts],
            key=lambda path: path.relative_to(PLUGIN).as_posix(),
        )

    @classmethod
    def _assert_candidate_parity(cls):
        missing, different = [], []
        for path in cls._candidate_files():
            relative = path.relative_to(PLUGIN)
            candidate = cls.installed_root / relative
            if not candidate.is_file():
                missing.append(relative.as_posix())
            elif path.read_bytes() != candidate.read_bytes():
                different.append(relative.as_posix())
        assert not missing and not different, {
            "message": "Installed PCW candidate differs from source",
            "missing": missing,
            "different": different,
        }

    @staticmethod
    def _declared_tool_names():
        """Read server registrations statically, without importing MCP dependencies."""
        tree = ast.parse((PLUGIN / "pcw_runtime" / "server.py").read_text(encoding="utf-8"))
        descriptions = next(
            node.value for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "_DESCRIPTIONS" for target in node.targets)
        )
        assert isinstance(descriptions, ast.Dict)
        return {"pcw_" + key.value for key in descriptions.keys if isinstance(key, ast.Constant)}

    def test_tools_are_loaded_and_memory_works_through_codex(self):
        inventory = self.host.call("mcpServerStatus/list", {
            "threadId": self.thread_id, "detail": "toolsAndAuthOnly", "limit": 100,
        })
        server = next(item for item in inventory["data"] if item["name"] == "pcw")
        # Codex 0.154 returns a compact list of names while earlier hosts
        # returned descriptors. Both are host inventory, not a static proxy.
        actual_tools = {tool if isinstance(tool, str) else tool["name"] for tool in server["tools"]}
        self.assertEqual(self._declared_tool_names(), actual_tools, server)
        item = self.tool("create", content="Запись через настоящий Codex.")
        self.assertEqual("Запись через настоящий Codex.", self.tool("read", material_id=item["id"])["content"])
        changed = self.tool("update", material_id=item["id"], content="Обновлено через Codex.", expected_revision=item["revision"])
        self.assertEqual("Обновлено через Codex.", self.tool("read", material_id=changed["id"])["content"])
        self.tool("current_set", goal="Проверить запуск PCW", constraints="Временные данные",
                  completion="Инструменты работают через Codex", step="Готово", blocker="")
        self.assertEqual("Готово", self.tool("current_get")["step"])

    def test_native_pcw_skill_is_discoverable_for_explicit_turn_input(self):
        skills = self.host.call("skills/list", {"cwds": [self.work], "forceReload": True})
        matching = [
            skill for entry in skills["data"] for skill in entry["skills"]
            if skill["name"] == "persistent-context-workspace:pcw"
            and skill["pluginId"] == PLUGIN_ID
        ]
        self.assertEqual(1, len(matching), skills)
        self.assertTrue(matching[0]["enabled"])
        self.assertTrue(matching[0]["path"].endswith("/skills/pcw/SKILL.md"))

    def test_new_workflow_and_memory_apis_work_through_codex(self):
        """Exercise map, raw result, readable Current and migration APIs in a fresh workspace."""
        self.assertEqual("absent", self.tool("environment_get")["status"])
        snapshot = {
            "environment": "codex-host-regression",
            "version": "host-v1",
            "native": {"launch": {"supports_clean_context": True, "fork_turns": "none"}},
            "models": [{
                "id": "host-worker", "reasoning": {"effort": ["low"]},
                "launch_constraints": {"fork_turns": ["none"]},
            }],
        }
        checked = self.tool("environment_check", environment_snapshot=snapshot)
        self.assertEqual("updated", checked["status"])
        profile = [{
            "id": "prepared-host-work", "model": "host-worker", "reasoning": {"effort": "low"},
            "roles": ["investigation"], "suitable_when": ["bounded host regression"],
        }]
        published = self.tool("tools_map_publish", expected_environment_revision=checked["environment_revision"], profiles=profile)
        self.assertEqual("published", published["status"])
        self.assertEqual("current", self.tool("tools_map_get")["status"])

        refreshed = self.tool("environment_check", environment_snapshot={**snapshot, "version": "host-v2"})
        self.assertEqual("refresh_required", refreshed["tools_map_status"])
        stale = self.tool("tools_map_publish", expected_environment_revision=checked["environment_revision"], profiles=profile)
        self.assertEqual("rejected", stale["status"])
        self.assertEqual("published", self.tool("tools_map_publish", expected_environment_revision=refreshed["environment_revision"], profiles=profile)["status"])

        self.tool("task_begin", goal="Host workflow", constraints="Temporary only", completion="All host APIs are observable")
        prepared_assignment = self.tool("action_requirements", action="prepare_assignment", context={"assignment": {
            "goal": "Observe host fixture", "expected_result": "Return observations", "boundaries": "Temporary workspace",
            "context": {"summary": "API regression", "material_ids": []}, "constraints": [],
            "acceptance_criteria": ["Observe actual result"], "knowledge_to_return": "Facts and blocker",
            "profile": "prepared-host-work", "selection_reason": "Bounded API fixture"}})
        self.assertTrue(prepared_assignment["ready"], prepared_assignment)
        assignment_id = prepared_assignment["handoff"]["assignment_id"]
        self.tool("assignment_bind", assignment_id=assignment_id, executor_session_id="codex-native-child-host-test")
        self.tool("assignment_get", assignment_id=assignment_id, executor_session_id="codex-native-child-host-test")
        raw = "# Worker findings\n\n| fact | value |\n| --- | --- |\n| token | `host-sentinel` |\n"
        saved = self.tool("save_subagent_result", assignment_id=assignment_id, result=raw,
                          executor_session_id="codex-native-child-host-test")
        self.assertEqual("saved", saved["status"])
        reread = self.tool("read", material_id=saved["id"], assignment_id=assignment_id)
        self.assertEqual(raw, reread["content"])
        self.assertEqual("codex-native-child-host-test", reread["executor_session_id"])
        self.assertTrue(reread["saved_at"].endswith("Z"))
        repeated = self.tool("save_subagent_result", assignment_id=assignment_id, result=raw,
                             executor_session_id="codex-native-child-host-test")
        self.assertEqual("already_saved", repeated["status"])
        updated_raw = raw + "\nFollow-up completion for the same native worker.\n"
        revised = self.tool("save_subagent_result", assignment_id=assignment_id, result=updated_raw,
                            executor_session_id="codex-native-child-host-test",
                            expected_previous_revision=saved["revision"])
        self.assertEqual("updated", revised["status"])
        self.assertNotEqual(saved["saved_at"], revised["saved_at"])
        self.assertEqual(updated_raw, self.tool("read", material_id=saved["id"], assignment_id=assignment_id)["content"])
        stale_retry = self.tool("save_subagent_result", assignment_id=assignment_id, result=updated_raw,
                                executor_session_id="codex-native-child-host-test",
                                expected_previous_revision=saved["revision"])
        self.assertEqual("already_saved", stale_retry["status"])

        current = self.tool("current_set", goal="Host workflow", constraints="Temporary only",
                            completion="All host APIs are observable", step="Read back", blocker="")
        self.assertEqual(current, self.tool("current_get"))
        self.assertEqual("already_migrated", self.tool("migrate_legacy_ids")["status"])

    @unittest.skipUnless(os.environ.get("PCW_TEST_QWEN") == "1", "Set PCW_TEST_QWEN=1 after provisioning local Qwen")
    def test_local_qwen_index_search_and_links_through_codex(self):
        status = self.tool("status")
        self.assertEqual("Qwen/Qwen3-Embedding-0.6B", status["active"]["config"]["profile"]["model"])
        text = "Резервные копии PostgreSQL сохраняются ежедневно в три часа ночи."
        item = self.tool("create", content=text)
        prepared = self.tool("prepare", material_id=item["id"])
        self.tool("submit_parts", material_id=item["id"], revision=prepared["revision"], parts=[text])
        found = self.tool("search", query="Когда делают резервные копии PostgreSQL?")
        self.assertEqual(item["id"], found["results"][0]["id"], found)
        other = self.tool("create", content="Порядок восстановления данных.")
        self.tool("links", source_id=other["id"], add=[item["id"]])
        self.assertIn(item["id"], self.tool("read", material_id=other["id"])["links"])


if __name__ == "__main__":
    unittest.main()

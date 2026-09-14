"""Opt-in integration through Codex itself; no model turns or manual root env.

PCW_TEST_CODEX=1 requires a locally installed matching PCW candidate.
PCW_TEST_QWEN=1 additionally exercises the already provisioned local model.
Only temporary knowledge is changed. No plugin/config installation is done here.
"""

from __future__ import annotations

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
    def __init__(self, environment, work):
        settings_path = Path.home() / ".codex" / "config.toml"
        settings = tomllib.loads(settings_path.read_text()) if settings_path.exists() else {}
        names = set(settings.get("plugins", {})) | {PLUGIN_ID}
        plugin_policy = "{" + ",".join(
            json.dumps(name) + "={enabled=" + ("true" if name == PLUGIN_ID else "false") + "}"
            for name in sorted(names)
        ) + "}"
        self.messages = queue.Queue()
        self.request_id = 0
        self.errors = tempfile.TemporaryFile(mode="w+")
        self.process = subprocess.Popen(
            ["codex", "-c", "mcp_servers={}", "-c", "plugins=" + plugin_policy,
             "-c", "features.apps=false", "app-server", "--stdio"],
            env=environment, cwd=work, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.errors, text=True, bufsize=1,
        )
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for line in self.process.stdout:
                self.messages.put(json.loads(line))
        except Exception as error:
            self.messages.put(error)
        finally:
            self.messages.put(EOFError("Codex app-server closed stdout"))

    def send(self, message):
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
            if "id" in message and "method" in message:
                self.send({"id": message["id"], "error": {
                    "code": -32601, "message": "Unexpected server request in PCW host test",
                }})

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
        installed_root = cls.launcher.parents[1]
        checked = [PLUGIN / "mcp.json", *(PLUGIN / "scripts").glob("*.py"),
                   *(PLUGIN / "scripts").glob("*.sh"), *(PLUGIN / "pcw_runtime").rglob("*.py")]
        for path in checked:
            assert path.read_bytes() == (installed_root / path.relative_to(PLUGIN)).read_bytes(), (
                "Installed candidate differs from source", str(path)
            )
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

    def test_tools_are_loaded_and_memory_works_through_codex(self):
        inventory = self.host.call("mcpServerStatus/list", {
            "threadId": self.thread_id, "detail": "toolsAndAuthOnly", "limit": 100,
        })
        server = next(item for item in inventory["data"] if item["name"] == "pcw")
        self.assertEqual(20, len(server["tools"]), server)
        item = self.tool("create", path="host.md", content="Запись через настоящий Codex.")
        self.assertEqual("Запись через настоящий Codex.", self.tool("read", material_id=item["id"])["content"])
        changed = self.tool("update", material_id=item["id"], content="Обновлено через Codex.", expected_revision=item["revision"])
        self.assertEqual("Обновлено через Codex.", self.tool("read", material_id=changed["id"])["content"])
        self.tool("current_set", goal="Проверить запуск PCW", constraints="Временные данные",
                  completion="Инструменты работают через Codex", step="Готово", blocker="")
        self.assertEqual("Готово", self.tool("current_get")["step"])

    @unittest.skipUnless(os.environ.get("PCW_TEST_QWEN") == "1", "Set PCW_TEST_QWEN=1 after provisioning local Qwen")
    def test_local_qwen_index_search_and_links_through_codex(self):
        status = self.tool("status")
        self.assertEqual("Qwen/Qwen3-Embedding-0.6B", status["active"]["config"]["profile"]["model"])
        text = "Резервные копии PostgreSQL сохраняются ежедневно в три часа ночи."
        item = self.tool("create", path="backups.md", content=text)
        prepared = self.tool("prepare", material_id=item["id"])
        self.tool("submit_parts", material_id=item["id"], revision=prepared["revision"], parts=[text])
        found = self.tool("search", query="Когда делают резервные копии PostgreSQL?")
        self.assertEqual(item["id"], found["results"][0]["id"], found)
        other = self.tool("create", path="related.md", content="Порядок восстановления данных.")
        self.tool("links", source_id=other["id"], add=[item["id"]])
        self.assertIn(item["id"], self.tool("read", material_id=other["id"])["links"])


if __name__ == "__main__":
    unittest.main()

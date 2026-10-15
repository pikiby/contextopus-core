"""Fresh native Codex MCP verification without running a model turn.

Protocol fields are verified against `codex app-server generate-json-schema`
from the installed 0.162.1 CLI. Use only after the native integration gate.
The ephemeral thread performs two explicit Contextopus read operations.
"""

import argparse
import hashlib
import json
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time


def verify(cwd, expected_root, delivery="direct"):
    with tempfile.TemporaryFile(mode="w+") as error_log:
        process = subprocess.Popen(
            ["codex", "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=error_log,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        messages = queue.Queue()

        def read():
            for line in process.stdout:
                try:
                    messages.put(json.loads(line))
                except json.JSONDecodeError:
                    continue
            messages.put(None)

        threading.Thread(target=read, daemon=True).start()
        serial = 0

        def request(method, params):
            nonlocal serial
            serial += 1
            ident = serial
            process.stdin.write(
                json.dumps({"id": ident, "method": method, "params": params}) + "\n"
            )
            process.stdin.flush()
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    item = messages.get(timeout=max(0.1, deadline - time.monotonic()))
                except queue.Empty:
                    break
                if item is None:
                    raise RuntimeError(
                        "Fresh Codex app server exited before verification"
                    )
                if item.get("id") == ident:
                    if "error" in item:
                        raise RuntimeError(
                            f"Codex method failed: {method} (code {item['error'].get('code')})"
                        )
                    return item["result"]
                if "id" in item and "method" in item:
                    process.stdin.write(
                        json.dumps(
                            {
                                "id": item["id"],
                                "error": {
                                    "code": -32601,
                                    "message": "Verification does not approve external actions",
                                },
                            }
                        )
                        + "\n"
                    )
                    process.stdin.flush()
            raise RuntimeError(f"Fresh Codex timed out during {method}")

        def result_value(result):
            if result.get("isError"):
                raise RuntimeError("Contextopus read failed through fresh Codex")
            if result.get("structuredContent") is not None:
                return result["structuredContent"]
            return json.loads(
                "\n".join(
                    item["text"]
                    for item in result.get("content", [])
                    if item.get("type") == "text"
                )
            )

        try:
            request(
                "initialize",
                {
                    "clientInfo": {
                        "name": "contextopus-verification",
                        "version": "1.0.0",
                    },
                    "capabilities": {"experimentalApi": True},
                },
            )
            process.stdin.write('{"method":"initialized","params":{}}\n')
            process.stdin.flush()
            started = request(
                "thread/start",
                {
                    "cwd": str(Path(cwd).resolve()),
                    "ephemeral": True,
                    "sandbox": "read-only",
                    "approvalPolicy": "never",
                },
            )
            thread = started["thread"]["id"]
            skills_result = request(
                "skills/list", {"cwds": [str(Path(cwd).resolve())], "forceReload": True}
            )
            skills = [
                item
                for entry in skills_result["data"]
                for item in entry["skills"]
                if item.get("enabled")
                and (
                    item.get("pluginId") == "contextopus@contextopus"
                    if delivery == "plugin"
                    else item["name"] in {"w", "ws", "wi", "wc", "wu", "wa", "wr", "wx"}
                    and not item.get("pluginId")
                    and Path(item["path"]).parent.parent
                    == Path.home() / ".agents/skills"
                )
            ]
            expected_skills = {
                ("contextopus:" if delivery == "plugin" else "") + name
                for name in ("w", "ws", "wi", "wc", "wu", "wa", "wr", "wx")
            }
            if {item["name"] for item in skills} != expected_skills:
                raise RuntimeError(
                    "Fresh Codex did not discover all eight expected short skills"
                )
            if any(
                item.get("pluginId")
                in (
                    {
                        "persistent-context-workspace@persistent-context-workspace",
                        "contextopus@contextopus",
                    }
                    if delivery == "direct"
                    else {"persistent-context-workspace@persistent-context-workspace"}
                )
                and item.get("enabled")
                for entry in skills_result["data"]
                for item in entry["skills"]
            ):
                raise RuntimeError(
                    "Old plugin remains enabled in fresh Codex discovery"
                )
            deadline = time.monotonic() + 60
            while True:
                inventory = request(
                    "mcpServerStatus/list",
                    {"threadId": thread, "detail": "toolsAndAuthOnly", "limit": 100},
                )
                servers = [
                    item for item in inventory["data"] if "contextopus" in item["name"]
                ]
                if len(servers) == 1 and servers[0].get("tools"):
                    break
                if time.monotonic() >= deadline:
                    names = [item["name"] for item in inventory["data"]]
                    raise RuntimeError(
                        f"Expected one ready Contextopus MCP connection; observed {names}"
                    )
                time.sleep(1)
            server = servers[0]
            tool = next(
                (
                    name
                    for name in server["tools"]
                    if name.endswith("contextopus_query")
                ),
                None,
            )
            if tool is None:
                raise RuntimeError("Fresh Codex did not expose Contextopus query tool")
            base = {"threadId": thread, "server": server["name"], "tool": tool}
            status = result_value(
                request(
                    "mcpServer/tool/call",
                    {
                        **base,
                        "arguments": {
                            "operation": "core.status",
                            "work_root": str(Path(expected_root).resolve()),
                        },
                    },
                )
            )
            if Path(status["scope"]).resolve() != Path(expected_root).resolve():
                raise RuntimeError("Fresh Codex used an unexpected data root")
            procedure = result_value(
                request(
                    "mcpServer/tool/call",
                    {
                        **base,
                        "arguments": {
                            "operation": "procedure",
                            "arguments": {"name": "upgrade"},
                        },
                    },
                )
            )
            print(
                json.dumps(
                    {
                        "verified": True,
                        "client": "Codex",
                        "delivery": delivery,
                        "server": server["name"],
                        "plugin_id": server.get("pluginId"),
                        "runtime_status": server.get("runtimeStatus"),
                        "scope": status["scope"],
                        "tools": len(server["tools"]),
                        "skills": sorted(item["name"] for item in skills),
                        "upgrade_procedure_sha256": hashlib.sha256(
                            procedure["content"].encode()
                        ).hexdigest(),
                    },
                    indent=2,
                )
            )
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--expected-root", type=Path, required=True)
    parser.add_argument("--delivery", choices=("direct", "plugin"), default="direct")
    args = parser.parse_args()
    verify(args.cwd, args.expected_root, args.delivery)

"""Isolated native recovery checks; no model calls or user sessions/configuration.

Run with the installed Codex/OpenCode and the Contextopus package under test.
Temporary native data, MCP root and loopback ports are private to this check.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextopus.integrations.jsonrpc import WebSocketProxyRPC
from contextopus.integrations.reconnect import initialize, verify_codex_thread


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(url, data=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def start_mcp(root, number, log):
    child = subprocess.Popen([sys.executable, "-c",
        f"from contextopus.interfaces.mcp.server import create_server; create_server({str(root)!r},port={number}).run(transport='streamable-http')"], stdout=log, stderr=log)
    for _ in range(100):
        if child.poll() is not None:
            raise RuntimeError("Test MCP exited")
        try:
            request(f"http://127.0.0.1:{number}/health")
            return child
        except OSError:
            time.sleep(.1)
    child.terminate()
    child.wait(timeout=10)
    raise RuntimeError("Test MCP startup timed out")


def stop(child):
    child.terminate()
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)


@contextmanager
def codex_control(base, home, log):
    # Exercise the same WebSocket proxy used to attach to an existing desktop
    # daemon, rather than substituting its different JSON-lines stdio transport.
    path = base / "control.sock"
    env = {**os.environ, "CODEX_HOME": str(home)}
    native = subprocess.Popen(["codex", "app-server", "--listen", f"unix://{path}"],
                              env=env, cwd=base, stdout=log, stderr=log)
    try:
        for _ in range(100):
            if native.poll() is not None:
                raise RuntimeError("Isolated Codex app-server exited")
            if path.exists():
                break
            time.sleep(.1)
        # Socket creation may precede the listener becoming ready.
        deadline = time.monotonic() + 10
        while True:
            try:
                rpc = WebSocketProxyRPC(["codex", "app-server", "proxy", "--sock", str(path)],
                                        env=env, cwd=base, timeout=5)
                break
            except (RuntimeError, TimeoutError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.1)
        rpc.timeout = 40
        with rpc:
            yield rpc
    finally:
        stop(native)


def codex(base, root, number, log):
    home = base / "codex"
    home.mkdir()
    (home / "config.toml").write_text(f'[mcp_servers.contextopus]\nurl="http://127.0.0.1:{number}/mcp"\nstartup_timeout_sec=2\n')
    with codex_control(base, home, log) as rpc:
        initialize(rpc)
        threads = [rpc.request("thread/start", {"cwd": str(base), "ephemeral": False,
                   "sandbox": "read-only", "approvalPolicy": "never"})["thread"] for _ in range(2)]
        sentinel = "Contextopus recovery history sentinel"
        rpc.request("thread/inject_items", {"threadId": threads[0]["id"], "items": [
            {"type": "message", "role": "user", "content": [{"type": "input_text", "text": sentinel}]}]})
        history = Path(threads[0]["path"])
        for _ in range(100):
            before = history.read_bytes() if history.exists() else b""
            states = [rpc.request("mcpServerStatus/list", {"threadId": t["id"], "detail": "toolsAndAuthOnly", "limit": 100}) for t in threads]
            if sentinel.encode() in before and all(s["data"][0].get("runtimeStatus") == "failed" for s in states):
                break
            time.sleep(.1)
        else:
            raise AssertionError("Initial failure and persisted nonempty history were not established")
        child = start_mcp(root, number, log)
        try:
            rpc.request("config/mcpServer/reload")
            verified = [verify_codex_thread(rpc, t["id"], root) for t in threads]
            assert all(item["status"] == "verified" for item in verified), verified
            assert history.read_bytes().startswith(before)
            stop(child)
            child = start_mcp(root, number, log)
            # An already established connection may recover without reload.
            renewed = verify_codex_thread(rpc, threads[0]["id"], root, timeout=5)
            automatic = renewed["status"] == "verified"
            if not automatic:
                rpc.request("config/mcpServer/reload")
                renewed = verify_codex_thread(rpc, threads[0]["id"], root)
            assert renewed["status"] == "verified", renewed
            assert history.read_bytes().startswith(before)
            assert set(rpc.request("thread/loaded/list", {})["data"]) == {t["id"] for t in threads}
            return {"client": "codex", "transport": "websocket_proxy", "failed_initialization_recovered": True, "threads_verified": 2,
                    "same_threads": True, "nonempty_history_preserved": True, "restart_automatic": automatic}
        finally:
            stop(child)


def opencode(base, root, number, log):
    from contextopus.integrations.opencode import reconnect
    native_port = port()
    url = f"http://127.0.0.1:{native_port}"
    env = {**os.environ, **{f"XDG_{key}_HOME": str(base / key.lower()) for key in ("CONFIG", "DATA", "STATE", "CACHE")},
           "OPENCODE_CONFIG_CONTENT": json.dumps({"mcp": {"contextopus": {"type": "remote", "url": f"http://127.0.0.1:{number}/mcp", "timeout": 2000}}})}
    native = subprocess.Popen(["opencode", "serve", "--hostname", "127.0.0.1", "--port", str(native_port)],
                              cwd=str(base), env=env, stdout=log, stderr=log)
    child = None
    try:
        for _ in range(100):
            try:
                request(url + "/doc")
                break
            except OSError:
                time.sleep(.2)
        initial = request(url + "/mcp")
        assert initial["contextopus"]["status"] != "connected", initial
        session = request(url + "/session", {"title": "Contextopus recovery fixture"})
        path = url + "/session/" + session["id"] + "/message"
        request(path, {"noReply": True, "parts": [{"type": "text", "text": "Recovery history sentinel"}]})
        before = request(path)
        assert before
        child = start_mcp(root, number, log)
        result = reconnect(url, base)
        assert result["status"] == "connected", result
        assert request(path) == before
        stop(child)
        child = start_mcp(root, number, log)
        assert reconnect(url, base)["status"] == "connected"
        assert request(path) == before
        return {"client": "opencode", "failed_initialization_recovered": True,
                "server_restart_recovered": True, "nonempty_history_preserved": True,
                "tool_call_verified": False, "reason": "Native API verifies connection; no model turn or direct tool-call endpoint used"}
    finally:
        if child:
            stop(child)
        stop(native)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("client", choices=("codex", "opencode"))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="contextopus-client-recovery-") as directory:
        base = Path(directory)
        root = base / "memory"
        root.mkdir()
        with (base / "process.log").open("w") as log:
            result = {"codex": codex, "opencode": opencode}[args.client](base, root, port(), log)
        print(json.dumps(result, indent=2))

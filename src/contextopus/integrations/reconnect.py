"""Recover existing client connections through native client mechanisms."""

from pathlib import Path
import time

from .jsonrpc import WebSocketProxyRPC, tool_value


def initialize(rpc):
    rpc.request("initialize", {"clientInfo": {"name": "contextopus-control", "version": "1"},
                               "capabilities": {"experimentalApi": True}})
    rpc.send({"method": "initialized", "params": {}})


def select_read_tool(tool_names, *, legacy_tools=False):
    """Choose the deliberate protocol; never retry a failed mutation under an alias."""
    expected = 'contextopus_query' if legacy_tools else 'read'
    return next((name for name in tool_names if name == expected or name.endswith('__' + expected)), None)


def verify_codex_thread(rpc, thread_id, root, *, timeout=30, legacy_tools=False):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            result = rpc.request("mcpServerStatus/list", {"threadId": thread_id, "detail": "toolsAndAuthOnly", "limit": 100})
        except TimeoutError:
            return {"status": "not_verified", "thread_id": thread_id,
                    "reason": "The native MCP status request timed out. Reload was queued; verify Contextopus with a read call in that session."}
        matches = [s for s in result["data"] if s["name"] == "contextopus" or s["name"].endswith("__contextopus")]
        if len(matches) > 1:
            raise RuntimeError("Several Contextopus connections exist in the selected thread")
        for server in matches:
            tool = select_read_tool(server.get("tools", {}), legacy_tools=legacy_tools)
            if not tool:
                continue
            try:
                value = tool_value(rpc.request("mcpServer/tool/call", {
                    "threadId": thread_id, "server": server["name"], "tool": tool,
                    "arguments": {"operation": "core.status", "work_root": str(root)},
                }))
                if Path(value["scope"]).resolve() != Path(root).resolve():
                    raise RuntimeError("Client call reached an unexpected memory root")
                return {"status": "verified", "thread_id": thread_id, "server": server["name"], "root": value["scope"]}
            except RuntimeError as exc:
                last_error = str(exc)
        time.sleep(0.3)
    return {"status": "not_verified", "thread_id": thread_id,
            "reason": last_error or "The selected thread has not exposed the Contextopus tools after reload"}


def reconnect(client, root, *, socket=None, thread_id=None, client_url=None, directory=None):
    from .service import status
    state = status(root)
    if state["state"] != "running" or state.get("root") != str(Path(root).resolve()):
        raise RuntimeError("Start the selected root's MCP before reconnecting a client")
    if client == "codex":
        # Proxy attaches to the existing daemon. Never start a second app-server
        # and claim that it refreshed already-open conversations.
        argv = ["codex", "app-server", "proxy"]
        if socket is not None:
            argv.extend(["--sock", str(socket)])
        with WebSocketProxyRPC(argv) as rpc:
            initialize(rpc)
            rpc.request("config/mcpServer/reload")
            result = {"client": client, "status": "reload_queued", "scope": "all_loaded_threads",
                      "note": "Native Codex queues MCP configuration refresh; a queued reload is not proof of a successful tool call."}
            if thread_id:
                result["verification"] = verify_codex_thread(rpc, thread_id, root)
            return result
    if client == "claude-code":
        return {"client": client, "status": "native_action_required",
                "instruction": "In the existing Claude Code session, open /mcp, select Contextopus and Reconnect; then make a read call. Automatic retries are limited; this external command cannot control that session."}
    if client == "opencode":
        if client_url:
            from .opencode import reconnect as connect_opencode
            return connect_opencode(client_url, directory)
        return {"client": client, "status": "native_action_required",
                "instruction": "Supply --client-url for the running OpenCode server and --directory for its project. The adapter inspects /doc before disconnect/connect; starting another OpenCode server does not refresh existing sessions."}
    if client == "crush":
        return {"client": client, "status": "native_action_required",
                "instruction": "Crush 0.87.0 renews a previously established MCP connection on tool use. Failed initial connection is different: no verified external retry API is provided here. Restart the Crush workspace and resume its saved session; do not create a replacement conversation."}
    raise ValueError(f"Unknown client: {client}")

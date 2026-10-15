"""Reconnect an explicitly selected running OpenCode server using its OpenAPI."""

import base64
import json
import os
import urllib.parse
import urllib.request


def reconnect(url, directory=None):
    address = urllib.parse.urlsplit(url)
    if address.scheme not in {"http", "https"} or address.username or address.password:
        raise ValueError("Supply an HTTP(S) client URL without embedded credentials")
    if address.scheme == "http" and address.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Remote OpenCode control requires HTTPS")
    headers = {"Content-Type": "application/json"}
    password = os.environ.get("OPENCODE_SERVER_PASSWORD")
    if password:
        credentials = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode") + ":" + password
        headers["Authorization"] = "Basic " + base64.b64encode(credentials.encode()).decode()

    def request(path, method="GET"):
        target = url.rstrip("/") + path
        if directory:
            target += "?" + urllib.parse.urlencode({"directory": str(directory)})
        req = urllib.request.Request(target, headers=headers, method=method,
                                     data=b"{}" if method == "POST" else None)
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)

    paths = request("/doc")["paths"]
    required = {"/mcp": "get", "/mcp/{name}/connect": "post", "/mcp/{name}/disconnect": "post"}
    if any(method not in paths.get(path, {}) for path, method in required.items()):
        raise RuntimeError("This OpenCode version does not advertise the supported MCP control API")
    before = request("/mcp")
    if "contextopus" not in before:
        raise RuntimeError("The selected OpenCode instance has no Contextopus connection")
    request("/mcp/contextopus/disconnect", "POST")
    request("/mcp/contextopus/connect", "POST")
    state = request("/mcp")["contextopus"]
    return {"client": "opencode", "status": state["status"], "client_url": url,
            "directory": str(directory) if directory else None,
            "note": "Native MCP connection refreshed. Verify a Contextopus read in the existing session; connection status alone is not a tool-call check."}

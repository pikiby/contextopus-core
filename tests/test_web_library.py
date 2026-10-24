"""The web surface is a query-only projection of enabled module libraries."""
import http.client
import json
import threading

import pytest

from contextopus.core.documents.instructions import InstructionLibrary
from contextopus.core.documents.library import browse_instructions
from contextopus.core.storage import StorageLayout
from contextopus.interfaces.web.backend import LibraryBackend
from contextopus.interfaces.web.server import LibraryServer
from contextopus.interfaces.cli.main import parser


class FakeApp:
    def __init__(self):
        self.enabled = True
        self.kind = "query"
        self.calls = []

    def query(self, operation, arguments=None):
        self.calls.append((operation, arguments))
        if operation == "core.modules":
            return [{"id": "custom_notes", "state": "enabled" if self.enabled else "disabled",
                     "operations": ["custom_notes.library"]},
                    {"id": "legacy", "state": "enabled", "operations": []}]
        if operation == "describe":
            return {"kind": self.kind}
        if operation.endswith(".library"):
            if arguments["action"] == "record":
                return {"key": ["custom_notes", "notes", "note"], "content": "<script>unsafe()</script>"}
            return {"records": [], "total": 0, "has_more": False}
        raise AssertionError(operation)


def test_modules_are_contributions_not_a_fixed_list():
    app = FakeApp()
    backend = LibraryBackend(app)
    modules = backend.modules()["modules"]
    assert modules[0]["id"] == "custom_notes"
    assert not modules[1]["available"]
    assert modules[-1]["id"] == "core"
    assert backend.call("custom_notes", "records")["total"] == 0
    app.enabled = False
    with pytest.raises(ValueError, match="not enabled"):
        backend.call("custom_notes", "record", id="note")
    with pytest.raises(ValueError, match="does not provide"):
        backend.call("legacy", "records")
    app.enabled = True
    app.kind = "execute"
    with pytest.raises(ValueError, match="read-only"):
        backend.call("custom_notes", "records")


@pytest.fixture
def web_server():
    app = FakeApp()
    server = LibraryServer(app, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, app
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def request(server, path, *, method="GET", headers=None):
    client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    client.request(method, path, headers=headers or {})
    response = client.getresponse()
    body = response.read()
    result = response.status, dict(response.getheaders()), body
    client.close()
    return result


def test_http_assets_and_real_query_route(web_server):
    server, app = web_server
    for path in ("/", "/app.js", "/style.css"):
        code, headers, body = request(server, path)
        assert code == 200
        assert body
        assert headers["Cache-Control"] == "no-store"
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    code, _, body = request(server, "/api/record?module=custom_notes&collection=notes&id=note")
    assert code == 200
    assert json.loads(body)["content"] == "<script>unsafe()</script>"
    assert app.calls[-1] == ("custom_notes.library", {"action": "record", "collection": "notes", "id": "note"})


@pytest.mark.parametrize("path", [
    "/api/records?module=custom_notes&limit=1001",
    "/api/records?module=custom_notes&offset=-1",
    "/api/records?module=custom_notes&mode=execute",
    "/api/records?module=custom_notes&operation=workspace.finish",
    "/api/records?module=custom_notes&module=core",
    "/api/record?module=custom_notes",
    "/api/record?module=custom_notes&id=x&offset=-1",
    "/api/record?module=custom_notes&id=x&limit=101",
    "/api/records?module=..%2Fprivate",
])
def test_invalid_requests_do_not_dispatch(web_server, path):
    server, app = web_server
    code, _, _ = request(server, path)
    assert code == 400
    assert not any(op.endswith(".library") for op, _ in app.calls)


def test_no_cross_origin_arbitrary_files_or_mutations(web_server):
    server, app = web_server
    for headers in ({"Host": "attacker.example"}, {"Origin": "https://attacker.example"},
                    {"Sec-Fetch-Site": "cross-site"}):
        assert request(server, "/api/modules", headers=headers)[0] == 403
    for path in ("/../../etc/passwd", "/api/execute", "/server.py"):
        assert request(server, path)[0] == 404
    assert request(server, "/api/records", method="POST")[0] == 501
    assert app.calls == []


def test_instruction_catalog_filters_then_paginates_and_reads_links(tmp_path):
    lib = InstructionLibrary(StorageLayout(tmp_path))
    def save(ident, title, description, body, **extra):
        return lib.save(ident + ".md", {"id": ident, "type": "instruction", "title": title,
                                       "description": description, **extra}, body)
    save("alpha", "Alpha", "Unicode Привет", "Actual **body**")
    save("beta", "Beta", "Unicode привет", "[[alpha]] [[missing]]",
         instructions={"base": "[[core/instructions/alpha]]"})
    save("gamma", "Gamma", "Other", "body")
    response = browse_instructions(lib, "records", query="ПРИВЕТ", offset=1, limit=1)
    assert response["total"] == 2
    assert response["records"][0]["key"] == ["core", "instructions", "beta"]
    assert not response["has_more"]
    full = browse_instructions(lib, "record", id="beta")
    assert full["content"] == "[[alpha]] [[missing]]"
    assert any(link.get("key") == ["core", "instructions", "alpha"] for link in full["links"])
    assert any(link.get("unavailable") for link in full["links"])
    assert browse_instructions(lib, "records", type="task")["total"] == 0


def test_empty_instruction_catalog_is_not_created(tmp_path):
    root = tmp_path / "absent"
    lib = InstructionLibrary(StorageLayout(root))
    assert browse_instructions(lib, "records")["total"] == 0
    assert not root.exists()
    args = parser().parse_args(["web", "--port", "41861"])
    assert args.command == "web" and args.port == 41861


def test_core_library_registry_works_without_embeddings(tmp_path):
    from contextopus.startup import Application
    from contextopus.core.resources import ProcessResources
    def forbidden(_):
        raise AssertionError('Browsing must not load embeddings')
    with ProcessResources(forbidden) as resources:
        with Application(tmp_path, resources=resources, discover=False) as app:
            assert app.query('describe', {'operation': 'core.library'})['kind'] == 'query'
            assert app.query('core.library', {'action': 'records'})['total'] == 0
            app.execute('core.instructions_save', {'path': 'rules.md', 'metadata': {
                'id': 'rules', 'title': 'Rules', 'type': 'instruction', 'description': 'Working rules'},
                'content': 'Full rules'})
            assert app.query('core.library', {'action': 'record', 'id': 'rules'})['content'] == 'Full rules'
            assert not resources.providers._entries


def test_record_pagination_reaches_contribution(web_server):
    server, app = web_server
    code, _, _ = request(server, "/api/record?module=custom_notes&collection=notes&id=note&offset=40&limit=40")
    assert code == 200
    assert app.calls[-1][1] == {"action": "record", "collection": "notes", "id": "note", "offset": 40, "limit": 40}

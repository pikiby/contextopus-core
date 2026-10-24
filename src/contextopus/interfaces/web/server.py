"""Loopback-only HTTP interface; explicit read endpoints, no filesystem gateway."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
import threading
from urllib.parse import parse_qs, urlsplit

from .backend import LibraryBackend


class LibraryServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, application, port=41860):
        self.backend = LibraryBackend(application)
        self.requests = threading.BoundedSemaphore(8)
        super().__init__(("127.0.0.1", port), LibraryHandler)


class LibraryHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(90)

    def log_message(self, format, *args):
        # Search text and record ids may be private; don't put query strings in logs.
        pass

    def _trusted(self):
        port = self.server.server_port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in allowed:
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + host for host in allowed}:
            return False
        return self.headers.get("Sec-Fetch-Site") not in {"cross-site"}

    def reply(self, body, content_type="application/json; charset=utf-8", status=200):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._trusted():
            self.reply({"error": "Local same-origin requests only"}, status=403)
            return
        if len(self.path) > 10000:
            self.reply({"error": "Request too long"}, status=414)
            return
        url = urlsplit(self.path)
        assets = {"/": ("index.html", "text/html; charset=utf-8"),
                  "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                  "/style.css": ("style.css", "text/css; charset=utf-8")}
        if url.path in assets:
            name, kind = assets[url.path]
            self.reply(files("contextopus.interfaces.web").joinpath("static", name).read_bytes(), kind)
            return
        if url.path not in {"/api/modules", "/api/collections", "/api/records", "/api/record"}:
            self.reply({"error": "Unknown endpoint"}, status=404)
            return
        if not self.server.requests.acquire(blocking=False):
            self.reply({"error": "Library is busy; retry shortly"}, status=503)
            return
        try:
            values = parse_qs(url.query, keep_blank_values=True, max_num_fields=12)
            if any(len(value) != 1 for value in values.values()):
                raise ValueError("Duplicate parameters are not accepted")
            params = {key: value[0] for key, value in values.items()}
            allowed = {
                "/api/modules": set(), "/api/collections": {"module"},
                "/api/record": {"module", "collection", "id", "offset", "limit"},
                "/api/records": {"module", "collection", "query", "mode", "type", "offset", "limit"},
            }[url.path]
            if set(params) - allowed:
                raise ValueError("Unknown query parameter")
            backend = self.server.backend
            if url.path == "/api/modules":
                result = backend.modules()
            else:
                module = params.pop("module", "")
                action = url.path.rsplit("/", 1)[1]
                if action == "records" or (action == "record" and ({"offset", "limit"} & set(params))):
                    params["offset"] = int(params.get("offset", 0))
                    params["limit"] = int(params.get("limit", 40))
                    if not 0 <= params["offset"] <= 100000 or not 1 <= params["limit"] <= 100:
                        raise ValueError("Invalid pagination")
                    if params.get("mode", "text") not in {"text", "semantic"}:
                        raise ValueError("Invalid search mode")
                    if len(params.get("query", "")) > 2000:
                        raise ValueError("Search query exceeds 2000 characters")
                if action == "record" and not params.get("id"):
                    raise ValueError("Record id is required")
                result = backend.call(module, action, **params)
            self.reply(result)
        except (ValueError, KeyError) as exc:
            self.reply({"error": str(exc)}, status=400)
        except FileNotFoundError as exc:
            self.reply({"error": str(exc)}, status=404)
        except Exception as exc:
            self.reply({"error": "Core request failed: " + str(exc)}, status=502)
        finally:
            self.server.requests.release()


def run(application, port=41860):
    with LibraryServer(application, port) as server:
        print(f"Contextopus library: http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass

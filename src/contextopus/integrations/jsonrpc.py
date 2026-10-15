"""JSON-RPC control connections over native stdio and WebSocket proxies."""

import json
import queue
import subprocess
import tempfile
import threading
import time


class StdioRPC:
    binary = False

    def __init__(self, argv, *, env=None, cwd=None, timeout=30):
        self.timeout, self.serial = timeout, 0
        self.errors = tempfile.TemporaryFile(mode="w+")
        try:
            self.process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=self.errors, text=not self.binary,
                                            encoding=None if self.binary else "utf-8",
                                            bufsize=-1 if self.binary else 1, env=env, cwd=cwd)
        except BaseException:
            self.errors.close()
            raise
        self.messages = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                try:
                    self.messages.put(json.loads(line))
                except json.JSONDecodeError:
                    continue
        finally:
            self.messages.put(None)

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def request(self, method, params=None):
        self.serial += 1
        ident = self.serial
        self.send({"id": ident, "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                item = self.messages.get(timeout=max(0.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            if item is None:
                raise RuntimeError("Native host control connection closed")
            if isinstance(item, Exception):
                raise RuntimeError("Native host control transport failed") from item
            if item.get("id") == ident and "method" not in item:
                if "error" in item:
                    raise RuntimeError(f"Native method {method} failed: {item['error'].get('message', 'unknown error')}")
                return item.get("result")
            if "id" in item and "method" in item:
                self.send({"id": item["id"], "error": {"code": -32601, "message": "Control client cannot approve agent actions"}})
        raise TimeoutError(f"Native host timed out during {method}")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.reader.join(timeout=2)
        self.process.stdin.close()
        self.process.stdout.close()
        self.errors.close()


class WebSocketProxyRPC(StdioRPC):
    """Codex proxy bridges binary WebSocket bytes; it is not JSON-lines stdio."""

    binary = True

    def __init__(self, *args, **kwargs):
        from wsproto import ConnectionType, WSConnection
        from wsproto.events import Request
        self.ws = WSConnection(ConnectionType.CLIENT)
        self.lock = threading.RLock()
        self.connected = threading.Event()
        self.accepted = False
        super().__init__(*args, **kwargs)
        try:
            self._event(Request(host="localhost", target="/"))
            if not self.connected.wait(self.timeout):
                raise TimeoutError("Native host WebSocket handshake timed out")
            if not self.accepted:
                raise RuntimeError("Native host rejected or closed the WebSocket handshake")
        except BaseException:
            self.__exit__()
            raise

    def _event(self, event):
        with self.lock:
            self.process.stdin.write(self.ws.send(event))
            self.process.stdin.flush()

    def send(self, message):
        from wsproto.events import TextMessage
        self._event(TextMessage(data=json.dumps(message)))

    def _read(self):
        from wsproto.events import AcceptConnection, CloseConnection, Ping, RejectConnection, TextMessage
        fragments = []
        try:
            while data := self.process.stdout.read1(65536):
                with self.lock:
                    self.ws.receive_data(data)
                    for event in self.ws.events():
                        if isinstance(event, AcceptConnection):
                            self.accepted = True
                            self.connected.set()
                        elif isinstance(event, TextMessage):
                            fragments.append(event.data)
                            if event.message_finished:
                                self.messages.put(json.loads("".join(fragments)))
                                fragments.clear()
                        elif isinstance(event, Ping):
                            self._event(event.response())
                        elif isinstance(event, CloseConnection):
                            self._event(event.response())
                            return
                        elif isinstance(event, RejectConnection):
                            return
        except Exception as exc:
            self.messages.put(exc)
        finally:
            self.connected.set()
            self.messages.put(None)


def tool_value(value):
    if value.get("isError"):
        raise RuntimeError("The native client's MCP tool call failed")
    if value.get("structuredContent") is not None:
        return value["structuredContent"]
    return json.loads("\n".join(item["text"] for item in value.get("content", []) if item.get("type") == "text"))

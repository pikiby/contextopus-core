import sys

import pytest

from contextopus.integrations.jsonrpc import WebSocketProxyRPC


SERVER = '''
import json, sys
from wsproto import ConnectionType, WSConnection
from wsproto.events import Request, AcceptConnection, RejectConnection, TextMessage, Ping, Pong
ws = WSConnection(ConnectionType.SERVER)
def send(event):
    sys.stdout.buffer.write(ws.send(event))
    sys.stdout.buffer.flush()
pong = False
message = None
while data := sys.stdin.buffer.read1(65536):
    ws.receive_data(data)
    for event in ws.events():
        if isinstance(event, Request):
            if sys.argv[1] == "reject":
                send(RejectConnection(status_code=403))
                sys.exit(0)
            send(AcceptConnection())
            send(Ping(payload=b"alive"))
        elif isinstance(event, Pong):
            pong = True
        elif isinstance(event, TextMessage):
            message = json.loads(event.data)
        if message is not None and pong:
            response = json.dumps({"id": message["id"], "result": {"pong": pong, "text": "Unicode: \\u043f\\u0440\\u0438\\u0432\\u0435\\u0442"}})
            send(TextMessage(data=response[:15], message_finished=False))
            send(TextMessage(data=response[15:]))
            message = None
'''


def test_proxy_handles_websocket_upgrade_ping_and_fragmented_messages():
    with WebSocketProxyRPC([sys.executable, "-c", SERVER, "accept"], timeout=5) as rpc:
        assert rpc.request("fixture") == {"pong": True, "text": "Unicode: привет"}
    assert rpc.process.poll() is not None


def test_proxy_reports_rejected_handshake_promptly():
    with pytest.raises(RuntimeError, match="handshake"):
        WebSocketProxyRPC([sys.executable, "-c", SERVER, "reject"], timeout=5)

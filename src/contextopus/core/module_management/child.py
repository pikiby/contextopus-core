"""Standalone Python SDK; runs in a module venv without importing Core.

Stdout is reserved for UTF-8 line JSON. Background workers and dispatch may call
Core concurrently; the reader routes replies by ID and never runs module code.
"""
import contextlib
import json
import queue
import runpy
import sys
import threading
from pathlib import Path

# A module venv need not install/import Core. This sibling is stdlib-only and
# shares the exact wire encoder with both parent transports.
_protocol = runpy.run_path(str(Path(__file__).with_name('protocol.py')))
PROTOCOL = _protocol['PROTOCOL']
MAX_MESSAGE = _protocol['MAX_MESSAGE']
_encode_frame = _protocol['encode_frame']
_decode_frame = _protocol['decode_frame']


class NamespaceClient:
    def __init__(self, core, namespace):
        self.core, self.namespace = core, namespace

    def __getattr__(self, name):
        return lambda **arguments: self.core.call(self.namespace + '.' + name, arguments)


class StorageClient(NamespaceClient):
    def query(self, sql, parameters=(), *, transaction_id=None):
        return self._sql('query', sql, parameters, transaction_id)

    def execute(self, sql, parameters=(), *, transaction_id=None):
        return self._sql('execute', sql, parameters, transaction_id)

    def _sql(self, method, sql, parameters, transaction_id):
        arguments = {'sql': sql, 'parameters': parameters if isinstance(parameters, dict) else list(parameters)}
        if transaction_id is not None:
            arguments['transaction_id'] = transaction_id
        return self.core.call('storage.' + method, arguments)

    def begin(self, timeout_seconds=5):
        return self.core.call('storage.begin', {'timeout_seconds': timeout_seconds})

    @contextlib.contextmanager
    def transaction(self, timeout_seconds=5):
        ident = self.begin(timeout_seconds)['transaction_id']
        transaction = TransactionClient(self, ident)
        try:
            yield transaction
        except BaseException as primary:
            try:
                self.rollback(ident)
            except Exception as rollback_error:
                primary.add_note('Storage rollback failed: ' + str(rollback_error))
            raise
        else:
            self.commit(ident)

    def commit(self, transaction_id):
        return self.core.call('storage.commit', {'transaction_id': transaction_id})

    def rollback(self, transaction_id):
        return self.core.call('storage.rollback', {'transaction_id': transaction_id})


class TransactionClient:
    def __init__(self, storage, ident):
        self.storage, self.ident = storage, ident

    def query(self, sql, parameters=()):
        return self.storage.query(sql, parameters, transaction_id=self.ident)

    def execute(self, sql, parameters=()):
        return self.storage.execute(sql, parameters, transaction_id=self.ident)


class CoreClient:
    def __init__(self, source, destination):
        self.source, self.destination = source, destination
        self.storage = StorageClient(self, 'storage')
        self.embeddings = NamespaceClient(self, 'embeddings')
        self.rag = NamespaceClient(self, 'rag')
        self.documents = NamespaceClient(self, 'documents')
        self.instructions = NamespaceClient(self, 'instructions')
        self.messages = queue.Queue(maxsize=32)
        self._pending = {}
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._counter = 0
        self._closed = False
        self._local = threading.local()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def send(self, message):
        encoded = _encode_frame(message)
        with self._write_lock:
            target = getattr(self.destination, 'buffer', None)
            if target is not None:
                target.write(encoded)
                target.flush()
            else:
                self.destination.write(encoded.decode('utf-8'))
                self.destination.flush()

    def _read(self):
        try:
            while True:
                source = getattr(self.source, 'buffer', self.source)
                line = source.readline(MAX_MESSAGE + 1)
                if not line:
                    raise EOFError('Core disconnected')
                message = _decode_frame(line)
                if message.get('type') == 'return':
                    with self._lock:
                        target = self._pending.get(message.get('id'))
                    if target is None:
                        raise ValueError('Unexpected Core response')
                    target.put(message)
                else:
                    self.messages.put(message)
        except Exception as exc:
            with self._lock:
                self._closed = True
                pending = list(self._pending.values())
            for target in pending:
                target.put(exc)
            self.messages.put(exc)

    def receive(self):
        message = self.messages.get()
        if isinstance(message, Exception):
            raise message
        return message

    def call(self, method, arguments=None):
        with self._lock:
            if self._closed:
                raise EOFError('Core disconnected')
            self._counter += 1
            ident = str(self._counter)
            target = self._pending[ident] = queue.Queue()
        try:
            message = {'type': 'call', 'id': ident, 'method': method, 'arguments': arguments or {}}
            request_id = getattr(self._local, 'request_id', None)
            if request_id is not None:
                message['request_id'] = request_id
            self.send(message)
            response = target.get()
            if isinstance(response, Exception):
                raise response
            if 'error' in response:
                raise RuntimeError(response['error']['message'])
            return response['result']
        finally:
            with self._lock:
                self._pending.pop(ident, None)


def streams():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', newline='\n')
    return sys.stdin, sys.stdout


def main(filename, function):
    source, destination = streams()
    core = CoreClient(source, destination)
    try:
        request = core.receive()
        if request.get('protocol') != PROTOCOL or request.get('type') != 'request':
            raise ValueError('Unsupported Core protocol')
        with contextlib.redirect_stdout(sys.stderr):
            handler = runpy.run_path(filename)[function]
            result = handler(request['arguments'], core)
        response = {'type': 'result', 'result': result}
    except Exception as exc:
        response = {'type': 'error', 'error': {'type': type(exc).__name__, 'message': str(exc)}}
    core.send(response)

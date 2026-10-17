"""Standalone Python child adapter for the optional version-1 Core protocol.

This file runs under the module's interpreter, without importing Core or opening
its databases. Stdout belongs to the protocol; ordinary handler prints go to
stderr. Non-Python commands can implement the same newline-JSON messages.
"""
import contextlib
import json
import runpy
import sys

PROTOCOL = 'contextopus-core-v1'


class StorageClient:
    def __init__(self, source, destination):
        self.source, self.destination = source, destination
        self.counter = 0

    def _call(self, method, sql, parameters):
        self.counter += 1
        ident = str(self.counter)
        self.destination.write(json.dumps({'type': 'call', 'id': ident,
            'method': 'storage.' + method,
            'arguments': {'sql': sql, 'parameters': parameters if isinstance(parameters, dict) else list(parameters)}}, allow_nan=False) + '\n')
        self.destination.flush()
        response = json.loads(self.source.readline())
        if response.get('type') != 'return' or response.get('id') != ident:
            raise RuntimeError('Invalid Core response')
        if 'error' in response:
            raise RuntimeError(response['error']['message'])
        return response['result']

    def query(self, sql, parameters=()):
        return self._call('query', sql, parameters)

    def execute(self, sql, parameters=()):
        return self._call('execute', sql, parameters)


class CoreClient:
    def __init__(self, source, destination):
        self.storage = StorageClient(source, destination)


def main(filename, function):
    destination = sys.stdout
    try:
        request = json.loads(sys.stdin.readline())
        if request.get('protocol') != PROTOCOL or request.get('type') != 'request':
            raise ValueError('Unsupported Core protocol')
        with contextlib.redirect_stdout(sys.stderr):
            handler = runpy.run_path(filename)[function]
            result = handler(request['arguments'], CoreClient(sys.stdin, destination))
        response = {'type': 'result', 'result': result}
    except Exception as exc:
        response = {'type': 'error', 'error': {'type': type(exc).__name__, 'message': str(exc)}}
    destination.write(json.dumps(response, allow_nan=False) + '\n')
    destination.flush()

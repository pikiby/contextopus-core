"""Persistent module adapter using the standalone child SDK beside this file."""
import contextlib
from pathlib import Path
import runpy
import sys


def main(filename, factory):
    sdk = runpy.run_path(str(Path(__file__).with_name('child.py')))
    source, destination = sdk['streams']()
    core = sdk['CoreClient'](source, destination)
    # Worker threads continue after start()/dispatch() return. Redirect their
    # ordinary prints for the entire lifetime, retaining the protocol stream.
    sys.stdout = sys.stderr
    service = None
    try:
        initial = core.receive()
        if initial.get('protocol') != 'contextopus-service-v1' or initial.get('type') != 'init':
            raise ValueError('Unsupported service protocol')
        with contextlib.redirect_stdout(sys.stderr):
            service = runpy.run_path(filename)[factory](core)
            if hasattr(service, 'start'):
                service.start()
        core.send({'type': 'ready'})
        while True:
            request = core.receive()
            if request.get('type') == 'stop':
                break
            if request.get('type') != 'request' or not isinstance(request.get('id'), str):
                raise ValueError('Invalid service request')
            response = {'type': 'response', 'id': request['id']}
            try:
                core._local.request_id = request['id']
                with contextlib.redirect_stdout(sys.stderr):
                    response['result'] = service.dispatch(request['operation'], request['arguments'], request.get('context'))
            except Exception as exc:
                response['error'] = {'type': type(exc).__name__, 'message': str(exc)}
            finally:
                core._local.request_id = None
            core.send(response)
    except Exception as exc:
        core.send({'type': 'error', 'error': {'type': type(exc).__name__, 'message': str(exc)}})
    finally:
        if service is not None and hasattr(service, 'close'):
            with contextlib.redirect_stdout(sys.stderr):
                service.close()

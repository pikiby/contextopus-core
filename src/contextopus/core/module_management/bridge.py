"""Parent-side request-scoped Core RPC over a module child's existing stdio."""
import json
import logging
import os
import queue
import subprocess
import tempfile
import threading
import time

from .processes import terminate, windows_job

PROTOCOL = 'contextopus-core-v1'
MAX_MESSAGE = 1024 * 1024
logger = logging.getLogger(__name__)


def _terminate_preserving_error(process, job=None, primary=None):
    """Keep an operation failure primary while exposing failed child cleanup."""
    try:
        terminate(process, job)
    except BaseException as cleanup_error:
        # MCP serializes str(primary), dropping traceback notes and causes.
        # Report incomplete cleanup without logging handler arguments/messages.
        logger.error('Module child cleanup failed (%s, pid=%s); descendant termination is unverified',
                     type(cleanup_error).__name__, process.pid)
        if primary is not None:
            primary.add_note('Module child cleanup failed: ' + repr(cleanup_error))
            raise primary from cleanup_error
        raise


def invoke(command, *, arguments, module, kind, storage, declared_storage,
           cwd, env, timeout):
    """Dispatch only the invoking module's storage methods, within one deadline."""
    deadline = time.monotonic() + timeout
    incoming, outgoing = queue.Queue(maxsize=16), queue.Queue(maxsize=16)
    stopped = threading.Event()

    def put(target, message):
        while not stopped.is_set():
            if time.monotonic() >= deadline:
                return False
            try:
                target.put(message, timeout=.05)
                return True
            except queue.Full:
                pass

    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=errors, cwd=cwd, env=env,
            start_new_session=os.name != 'nt',
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
        try:
            job = windows_job(process)
        except BaseException as primary:
            try:
                _terminate_preserving_error(process, primary=primary)
            finally:
                process.stdin.close()
                process.stdout.close()
            raise

        def reader():
            try:
                while not stopped.is_set():
                    line = process.stdout.readline(MAX_MESSAGE + 1)
                    if len(line) > MAX_MESSAGE:
                        raise ValueError('Module protocol message exceeds 1 MiB')
                    if not line:
                        put(incoming, EOFError('Module exited without a final result'))
                        return
                    put(incoming, json.loads(line))
            except Exception as exc:
                put(incoming, exc)

        def writer():
            try:
                while not stopped.is_set():
                    try:
                        message = outgoing.get(timeout=.05)
                    except queue.Empty:
                        continue
                    encoded = (json.dumps(message, allow_nan=False) + '\n').encode()
                    if len(encoded) > MAX_MESSAGE:
                        raise ValueError('Core protocol message exceeds 1 MiB')
                    process.stdin.write(encoded)
                    process.stdin.flush()
            except Exception as exc:
                put(incoming, exc)

        readers = [threading.Thread(target=reader, daemon=True), threading.Thread(target=writer, daemon=True)]
        for thread in readers:
            thread.start()
        primary = None
        try:
            put(outgoing, {'protocol': PROTOCOL, 'type': 'request',
                'module': module, 'kind': kind, 'arguments': arguments})
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    message = incoming.get(timeout=remaining)
                except queue.Empty:
                    raise subprocess.TimeoutExpired(command, timeout) from None
                if isinstance(message, Exception):
                    raise message
                if not isinstance(message, dict):
                    raise ValueError('Invalid module protocol message')
                if message.get('type') == 'result' and set(message) == {'type', 'result'}:
                    process.wait(timeout=max(.001, deadline - time.monotonic()))
                    if process.returncode:
                        raise subprocess.CalledProcessError(process.returncode, command)
                    return message['result']
                if message.get('type') == 'error':
                    raise RuntimeError('Module handler failed: ' + str(message.get('error')))
                if message.get('type') != 'call' or set(message) != {'type', 'id', 'method', 'arguments'}:
                    raise ValueError('Invalid module Core call')
                ident = message['id']
                if not isinstance(ident, str):
                    raise ValueError('Core call ID must be text')
                response = {'type': 'return', 'id': ident}
                try:
                    if not declared_storage:
                        raise PermissionError('Module has no declared Core storage')
                    method = message['method']
                    if method not in {'storage.query', 'storage.execute'}:
                        raise ValueError('Unknown Core storage method')
                    if method == 'storage.execute' and kind != 'execute':
                        raise PermissionError('Query operations cannot write Core storage')
                    call = message['arguments']
                    if not isinstance(call, dict) or set(call) - {'sql', 'parameters'} or not isinstance(call.get('sql'), str):
                        raise ValueError('Storage calls require SQL and optional parameters')
                    parameters = call.get('parameters', [])
                    if not isinstance(parameters, (list, dict)):
                        raise ValueError('SQL parameters must be an array or object')
                    response['result'] = getattr(storage, method.split('.')[1])(
                        module, call['sql'], parameters, deadline=deadline)
                except Exception as exc:
                    response['error'] = {'type': type(exc).__name__, 'message': str(exc)}
                put(outgoing, response)
        except BaseException as error:
            primary = error
            raise
        finally:
            stopped.set()
            try:
                # Also terminate descendants when the direct child already exited.
                _terminate_preserving_error(process, job, primary=primary)
            finally:
                for stream in (process.stdin, process.stdout):
                    stream.close()
                for thread in readers:
                    thread.join(timeout=1)

"""Process-owned persistent folder module services, independent of context."""
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
import uuid

from .processes import terminate, windows_job
from .protocol import (MAX_MESSAGE, SERVICE_PROTOCOL, decode_frame, encode_call_response,
                       encode_error_response, encode_frame, validate_call)


class ModuleService:
    def __init__(self, app, module, manifest, fingerprint, command, cwd, env):
        self.app, self.module, self.manifest = app, module, manifest
        self.fingerprint, self.command, self.cwd, self.env = fingerprint, command, cwd, env
        self.state, self.error = 'stopped', None
        self.process = None
        self._lock = threading.RLock()
        self._outgoing = queue.Queue(maxsize=32)
        self._pending = {}
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._closing = threading.Event()
        self._finished = threading.Event()
        self._cleanup_lock = threading.Lock()
        self._cleanup_error = None
        self._accesses = {}
        self._rpc_slots = threading.BoundedSemaphore(16)

    def _access(self, kind='execute', *, provider_owner=None):
        from .core_access import ModuleCoreAccess
        return ModuleCoreAccess(self.app, self.module, kind=kind,
            storage_declared='storage' in self.manifest, rag_declared=self.manifest.get('rag', False),
            provider_owner=provider_owner)

    def status(self):
        with self._lock:
            return {'state': self.state, 'pid': self.process.pid if self.process and self.process.poll() is None else None,
                    **({'error': self.error} if self.error else {})}

    def _send(self, message):
        self._send_frame(encode_frame(message))

    def _send_frame(self, encoded):
        if self._stopped.is_set():
            raise RuntimeError('Module service is stopped')
        try:
            self._outgoing.put(encoded, timeout=.2)
        except queue.Full:
            raise RuntimeError('Module service input queue is full') from None

    def _write(self):
        try:
            while not self._stopped.is_set():
                try:
                    encoded = self._outgoing.get(timeout=.1)
                except queue.Empty:
                    continue
                self.process.stdin.write(encoded)
                self.process.stdin.flush()
        except Exception as exc:
            if not self._closing.is_set() and not self._stopped.is_set():
                self._fail(str(exc))

    def start(self):
        with self._lock:
            if self.state == 'running':
                return
            if self.state != 'stopped':
                raise RuntimeError(self.error or 'Module service cannot be started implicitly; explicitly enable it again')
            self.state = 'starting'
        try:
            self._background = self._access()
            self._errors = tempfile.TemporaryFile()
            self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=self._errors, cwd=self.cwd, env=self.env, start_new_session=os.name != 'nt',
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
            self._job = windows_job(self.process)
            self._reader = threading.Thread(target=self._read, daemon=True)
            self._writer = threading.Thread(target=self._write, daemon=True)
            self._monitor = threading.Thread(target=self._watch, daemon=True)
            self._reader.start()
            self._writer.start()
            self._monitor.start()
            self._send({'type': 'init', 'protocol': SERVICE_PROTOCOL, 'module': self.module})
            if not self._ready.wait(self.manifest['service'].get('ready_timeout', 30)):
                raise TimeoutError('Module service readiness timed out')
            if self.error:
                raise RuntimeError(self.error)
            with self._lock:
                if self._stopped.is_set():
                    raise RuntimeError('Module service stopped during startup')
                self.state = 'running'
        except Exception as exc:
            self._fail(str(exc))
            self.close(preserve_error=True)
            raise

    def _fail(self, error):
        with self._lock:
            self.error = self.error or error
            self.state = 'error'
            targets = list(self._pending.values())
        for target in targets:
            target.put(RuntimeError(self.error))
        self._ready.set()

    def _read(self):
        try:
            while not self._stopped.is_set():
                line = self.process.stdout.readline(MAX_MESSAGE + 1)
                if not line:
                    raise EOFError('Module service exited unexpectedly')
                message = decode_frame(line)
                if not isinstance(message, dict):
                    raise ValueError('Invalid service message')
                kind = message.get('type')
                if kind == 'ready' and set(message) == {'type'} and not self._ready.is_set():
                    self._ready.set()
                elif kind == 'response' and isinstance(message.get('id'), str):
                    with self._lock:
                        target = self._pending.get(message['id'])
                    if target is None:
                        raise ValueError('Unknown service request response')
                    target.put(message)
                elif kind == 'call':
                    validate_call({key: value for key, value in message.items() if key != 'request_id'})
                    if 'request_id' in message and not isinstance(message['request_id'], str):
                        raise ValueError('Service request ID must be text')
                    if not self._rpc_slots.acquire(blocking=False):
                        raise ValueError('Too many outstanding module Core calls')
                    threading.Thread(target=self._rpc, args=(message,), daemon=True).start()
                elif kind == 'error':
                    raise RuntimeError('Module service failed: ' + str(message.get('error')))
                else:
                    raise ValueError('Invalid service message')
        except Exception as exc:
            if not self._closing.is_set() and not self._stopped.is_set():
                self._fail(str(exc))
        finally:
            self._reader_done = True

    def _rpc(self, message):
        try:
            request_id = message.get('request_id')
            with self._lock:
                access = self._background if request_id is None else self._accesses.get(request_id)
            if access is None:
                raise PermissionError('Unknown or expired service request ID')
            request = {key: value for key, value in message.items() if key != 'request_id'}
            response = encode_call_response(access, request)
        except Exception as exc:
            response = encode_error_response(message.get('id'), exc)
        try:
            if not self._stopped.is_set():
                self._send_frame(response)
        except Exception as exc:
            if not self._stopped.is_set():
                self._fail(str(exc))
        finally:
            self._rpc_slots.release()

    def _watch(self):
        checked = 0
        while not self._stopped.wait(.1):
            if self._closing.is_set():
                continue
            # Expiry runs separately from model RPC; no root guard is retained.
            with self._lock:
                accesses = [self._background, *self._accesses.values()]
                failed = self.state == 'error'
            for access in accesses:
                access.expire()
            if time.monotonic() - checked >= .5:
                checked = time.monotonic()
                try:
                    from .manifest import ModuleManifestReader
                    reader = ModuleManifestReader(self.app.layout)
                    if reader._digest(self.module) != self.fingerprint:
                        raise ValueError('Module changed; prepare and explicitly enable it again')
                    if not reader.state.get(self.module, {}).get('enabled'):
                        self.close()
                        return
                except Exception as exc:
                    self._fail(str(exc))
                    failed = True
            if failed or self.process.poll() is not None:
                if not failed:
                    self._fail('Module service exited unexpectedly')
                self.close(preserve_error=True)
                return

    def request(self, operation, kind, arguments, context, timeout):
        ident, target = uuid.uuid4().hex, queue.Queue()
        access = self._access(kind, provider_owner=self._background)
        with self._lock:
            if self.state != 'running':
                access.close()
                raise RuntimeError(self.error or 'Module service is not running')
            if len(self._pending) >= 16:
                access.close()
                raise RuntimeError('Too many outstanding module service requests')
            self._pending[ident], self._accesses[ident] = target, access
        try:
            self._send({'type': 'request', 'id': ident, 'operation': operation,
                        'arguments': arguments, 'context': getattr(context, 'workspace', None)})
            try:
                response = target.get(timeout=timeout)
            except queue.Empty:
                self._fail('Module service request timed out')
                self.close(preserve_error=True)
                raise TimeoutError('Module service request timed out') from None
            if isinstance(response, Exception):
                raise response
            if 'error' in response:
                raise RuntimeError('Module service operation failed: ' + str(response['error']))
            return response['result']
        finally:
            with self._lock:
                self._pending.pop(ident, None)
                self._accesses.pop(ident, None)
            self._close_access(access)

    @staticmethod
    def _close_access(access, wait=.2):
        # A provider call cannot be interrupted safely. Disconnect immediately;
        # its daemon cleanup releases the lease as soon as the call returns.
        done = threading.Event()
        def cleanup():
            try:
                access.close()
            finally:
                done.set()
        threading.Thread(target=cleanup, daemon=True).start()
        done.wait(wait)
        return done

    def close(self, preserve_error=False):
        if not self._cleanup_lock.acquire(blocking=False):
            self._finished.wait(self.manifest['service'].get('stop_timeout', 5) + 6)
            return
        try:
            if self._finished.is_set():
                if self._cleanup_error is not None:
                    raise self._cleanup_error
                return
            self._closing.set()
            with self._lock:
                if not self.error:
                    self.state = 'stopping'
            process = self.process
            if process is not None and process.poll() is None:
                try:
                    self._send({'type': 'stop'})
                    process.wait(timeout=self.manifest['service'].get('stop_timeout', 5))
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
                    pass
            self._stopped.set()
            try:
                if process is not None:
                    terminate(process, getattr(self, '_job', None))
                    process.stdin.close()
                    process.stdout.close()
            finally:
                # Core capabilities must be revoked even when tree cleanup
                # fails; never leave an open transaction after disconnect.
                with self._lock:
                    accesses = [*self._accesses.values()]
                    if hasattr(self, '_background'):
                        accesses.append(self._background)
                    self.state = 'error' if preserve_error or self.error else 'stopped'
                    for target in self._pending.values():
                        target.put(RuntimeError(self.error or 'Module service stopped'))
                cleanups = [self._close_access(access, wait=0) for access in accesses]
                cleanup_deadline = time.monotonic() + .2
                for cleanup in cleanups:
                    cleanup.wait(max(0, cleanup_deadline - time.monotonic()))
                if hasattr(self, '_errors'):
                    self._errors.close()
        except Exception as exc:
            self._cleanup_error = exc
            self._fail('Module service cleanup failed: ' + str(exc))
            raise
        finally:
            self._finished.set()
            self._cleanup_lock.release()


class ModuleServiceRegistry:
    """Shared root lifecycle lock and service handles. Inspection is side effect free."""
    def __init__(self, root):
        self.root = root
        self.lock = threading.RLock()
        self.services = {}
        self.manager = None

    def start_if_enabled(self):
        if self.manager is not None:
            self.manager.start_services()

    def stop(self, module):
        service = self.services.get(module)
        if service is not None:
            service.close()
            self.services.pop(module, None)

    def close(self):
        failures = []
        with self.lock:
            for module in list(self.services):
                try:
                    self.stop(module)
                except Exception as exc:
                    failures.append(exc)
        if failures:
            raise ExceptionGroup('Module services failed to close', failures)

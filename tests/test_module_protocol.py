"""Exact JSON frame limits and recoverable Core replies through real children."""

import json
import io
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

from contextopus.core.module_management.protocol import (
    MAX_CALL_ID_BYTES, MAX_MESSAGE, FrameTooLarge, decode_frame, encode_call_response,
    encode_error_response, encode_frame, encoded_json_size, frame_size,
    response_result_budget, validate_call,
)
from contextopus.startup import Application


def call(ident='1'):
    return {'type': 'call', 'id': ident, 'method': 'test.payload', 'arguments': {}}


@pytest.mark.parametrize('symbol', ['x', 'я', '😀', '"', '\\', '\n'])
def test_full_utf8_return_frame_accepts_exact_limit_and_rejects_next_byte(symbol):
    ident = 'i' * (MAX_CALL_ID_BYTES - 2)
    budget = response_result_budget()
    unit = encoded_json_size(symbol) - 2
    count, remainder = divmod(budget - 2, unit)
    result = symbol * count + 'x' * remainder
    message = {'type': 'return', 'id': ident, 'result': result}
    encoded = encode_frame(message)
    assert len(encoded) == frame_size(message) == MAX_MESSAGE
    assert encoded.endswith(b'\n')
    assert json.loads(encoded) == message
    assert decode_frame(encoded) == message
    assert decode_frame(encoded.decode('utf-8')) == message
    assert encoded_json_size(result) == budget
    message['result'] += 'x'
    assert frame_size(message) == MAX_MESSAGE + 1
    with pytest.raises(FrameTooLarge, match='exceeds 1 MiB'):
        encode_frame(message)


def test_result_budget_reserves_actual_envelope_id_and_newline():
    small, maximum = 'a', '\0' * 21
    assert encoded_json_size(maximum) == MAX_CALL_ID_BYTES
    for ident in (small, maximum):
        available = response_result_budget(ident)
        assert available + frame_size({'type': 'return', 'id': ident, 'result': ''}) - 2 == MAX_MESSAGE
    assert response_result_budget(maximum) == response_result_budget()
    assert response_result_budget(small) > response_result_budget()


@pytest.mark.parametrize('ident', ['i' * 127, '\0' * 22, '😀' * 32])
def test_id_limit_counts_serialized_json_bytes_and_rejects_before_dispatch(ident):
    assert encoded_json_size(ident) > MAX_CALL_ID_BYTES
    with pytest.raises(ValueError, match='128 JSON bytes'):
        validate_call(call(ident))
    class Uncalled:
        def call(self, *args, **kwargs):
            pytest.fail('Invalid protocol call reached Core')
    with pytest.raises(ValueError):
        encode_call_response(Uncalled(), call(ident))


@pytest.mark.parametrize('message', [[], {}, {'type': 'call', 'id': 1, 'method': 'x', 'arguments': {}},
                                    {**call(), 'request_id': 'unexpected'}])
def test_invalid_call_shape_still_fails_protocol_validation(message):
    with pytest.raises(ValueError, match='Invalid module Core call'):
        validate_call(message)


def test_ordinary_error_is_preserved_exactly_and_oversized_error_is_explicit():
    text = 'Exact error: "я"\n\\tail'
    assert json.loads(encode_error_response('1', LookupError(text))) == {
        'type': 'return', 'id': '1', 'error': {'type': 'LookupError', 'message': text}}
    huge = 'PRIVATE_ERROR_TEXT' + '雪' * MAX_MESSAGE
    encoded = encode_error_response('1', LookupError(huge))
    response = json.loads(encoded)
    assert len(encoded) < 1024
    assert response['error']['type'] == 'LookupError'
    assert 'exceeds 1 MiB' in response['error']['message']
    assert 'original error text omitted' in response['error']['message']
    assert b'PRIVATE_ERROR_TEXT' not in encoded


def test_oversized_error_fallback_only_preserves_a_safe_type_name():
    error_class = type('E' * 1000, (Exception,), {})
    response = json.loads(encode_error_response('1', error_class('x' * MAX_MESSAGE)))
    assert response['error']['type'] == 'Exception'
    assert 'original error text omitted' in response['error']['message']


@pytest.mark.parametrize('value', [float('nan'), {'not-json'}, {'cycle': None}])
def test_unencodable_core_result_returns_a_bounded_error(value):
    if isinstance(value, dict):
        value['cycle'] = value
    class Access:
        def call(self, *args, **kwargs):
            return value
    encoded = encode_call_response(Access(), call())
    assert len(encoded) < 1024
    assert json.loads(encoded)['error']['message'] == 'Core result response is not JSON encodable.'


CHILD = '''
import os
def recover(arguments, core):
    pid = os.getpid()
    try:
        core.call('test.payload', {'mode': arguments['mode'], 'pid': pid})
    except RuntimeError as error:
        failure = str(error)
    else:
        raise RuntimeError('Oversized result was silently accepted')
    next_result = core.call('test.next', {'pid': pid})
    return {'error': failure, 'next': next_result, 'pid': pid}
class Service:
    def __init__(self, core):
        self.core = core
    def dispatch(self, operation, arguments, context):
        return recover(arguments, self.core)
    def close(self):
        pass
def create_service(core):
    return Service(core)
'''


def module(root, persistent):
    directory = root / 'modules/sample'
    package = directory / 'package'
    package.mkdir(parents=True)
    (package / 'handler.py').write_text(CHILD)
    operation = {'name': 'sample.recover', 'kind': 'query', 'arguments_schema': {
        'type': 'object', 'properties': {'mode': {'enum': ['result', 'error', 'invalid']}},
        'required': ['mode'], 'additionalProperties': False}}
    manifest = {'id': 'sample', 'version': '1.0', 'operations': [operation]}
    if persistent:
        manifest['service'] = {'factory': 'handler.py:create_service', 'ready_timeout': 3, 'stop_timeout': .2}
        operation['service'] = True
    else:
        operation.update(handler='handler.py:recover', protocol='contextopus-core-v1')
    (directory / 'module.json').write_text(json.dumps(manifest))


@pytest.mark.parametrize('persistent', [False, True], ids=['one-shot', 'persistent'])
@pytest.mark.parametrize('mode', ['result', 'error', 'invalid'])
def test_real_child_can_call_core_again_after_oversized_or_invalid_reply(tmp_path, monkeypatch, persistent, mode):
    from contextopus.core.module_management.core_access import ModuleCoreAccess
    original = ModuleCoreAccess.call
    observed = []
    def access(self, method, arguments, deadline=None):
        if method == 'test.payload':
            observed.append((method, arguments['pid']))
            if arguments['mode'] == 'error':
                raise LookupError('PRIVATE_OVERSIZED_ERROR' + 'я' * MAX_MESSAGE)
            if arguments['mode'] == 'invalid':
                return {float('nan')}
            return {'text': '😀' * MAX_MESSAGE}
        if method == 'test.next':
            observed.append((method, arguments['pid']))
            return {'ok': True, 'pid': arguments['pid']}
        return original(self, method, arguments, deadline)
    monkeypatch.setattr(ModuleCoreAccess, 'call', access)
    module(tmp_path, persistent)
    with Application(tmp_path, discover=False) as app:
        app.resources.start_services()
        app.execute('core.module_install', {'module': 'sample'})
        result = app.query('sample.recover', {'mode': mode})
        assert result['next'] == {'ok': True, 'pid': result['pid']}
        assert observed == [('test.payload', result['pid']), ('test.next', result['pid'])]
        assert 'JSON encodable' in result['error'] if mode == 'invalid' else 'exceeds 1 MiB' in result['error']
        assert 'PRIVATE_OVERSIZED_ERROR' not in result['error']
        if persistent:
            repeated = app.query('sample.recover', {'mode': mode})
            assert repeated['pid'] == result['pid']
            assert app.query('core.modules')[0]['service']['state'] == 'running'


@pytest.mark.parametrize('body', [b'{"type":"ready"}', b'{"type":"ready"}' + b' ' * (MAX_MESSAGE - 16)])
def test_decoder_rejects_complete_json_body_without_terminal_lf(body):
    assert len(body) <= MAX_MESSAGE
    with pytest.raises(ValueError, match='must end with a newline'):
        decode_frame(body)


@pytest.mark.parametrize('encoding', ['utf-16-be', 'utf-16-le', 'utf-32-be', 'utf-32-le'])
def test_decoder_rejects_non_utf8_json_even_when_json_loads_autodetects_it(encoding):
    body = json.dumps({'type': 'ready'}).encode(encoding) + '\n'.encode(encoding)
    assert json.loads(body) == {'type': 'ready'}
    with pytest.raises(ValueError):
        decode_frame(body)


RAW_CHILD = '''
import json, sys
sys.stdin.buffer.readline()
persistent, mode = sys.argv[1:]
value = {"type": "ready"} if persistent == "yes" else {"type": "result", "result": 1}
text = json.dumps(value, separators=(",", ":"))
body = text.encode("utf-8")
if mode == "max-no-lf":
    body += b" " * (1024 * 1024 - len(body))
elif mode == "utf16":
    body = text.encode("utf-16-be") + b"\\x00\\n"
sys.stdout.buffer.write(body)
sys.stdout.buffer.flush()
'''


@pytest.mark.parametrize('persistent', [False, True], ids=['one-shot', 'persistent'])
@pytest.mark.parametrize('mode', ['short-no-lf', 'max-no-lf', 'utf16'])
def test_parent_readers_reject_missing_lf_or_non_utf8_from_real_child(tmp_path, persistent, mode):
    package = tmp_path / 'modules/raw/package'
    package.mkdir(parents=True)
    (package / 'command.py').write_text(RAW_CHILD)
    command = [sys.executable, 'command.py', 'yes' if persistent else 'no', mode]
    operation = {'name': 'raw.check', 'kind': 'query'}
    manifest = {'id': 'raw', 'version': '1.0', 'operations': [operation]}
    if persistent:
        operation['service'] = True
        manifest['service'] = {'command': command, 'protocol': 'contextopus-service-v1',
                               'ready_timeout': 3, 'stop_timeout': .2}
    else:
        operation.update(command=command, protocol='contextopus-core-v1')
    (package.parent / 'module.json').write_text(json.dumps(manifest))
    with Application(tmp_path, discover=False) as app:
        app.resources.start_services()
        if persistent:
            with pytest.raises(RuntimeError):
                app.execute('core.module_install', {'module': 'raw'})
            assert app.query('core.modules')[0]['state'] == 'error'
        else:
            app.execute('core.module_install', {'module': 'raw'})
            with pytest.raises(ValueError):
                app.query('raw.check')


SDK_PATH = Path(__file__).resolve().parents[1] / 'src/contextopus/core/module_management/child.py'
SDK_READER = '''
import json, runpy, sys
sdk = runpy.run_path(sys.argv[1])
source, target = sdk['streams']()
client = sdk['CoreClient'](source, target)
try:
    value = client.receive()
except Exception as error:
    print(json.dumps({'error': type(error).__name__}))
else:
    print(json.dumps({'received': value['type'], 'length': len(value.get('padding', ''))}))
'''


@pytest.mark.parametrize('mode', ['short-no-lf', 'max-no-lf', 'utf16', 'exact-max'])
def test_standalone_sdk_reader_enforces_complete_utf8_frame(tmp_path, mode):
    message = {'type': 'request', 'padding': ''}
    body = encode_frame(message)
    if mode == 'exact-max':
        message['padding'] = 'x' * (MAX_MESSAGE - len(body))
        body = encode_frame(message)
        assert len(body) == MAX_MESSAGE
    elif mode == 'utf16':
        body = json.dumps(message).encode('utf-16-be') + b'\x00\n'
    else:
        body = body[:-1]
        if mode == 'max-no-lf':
            body += b' ' * (MAX_MESSAGE - len(body))
    result = subprocess.run([sys.executable, '-S', '-c', SDK_READER, str(SDK_PATH)],
                            input=body, capture_output=True, check=True, timeout=5)
    response = json.loads(result.stdout)
    if mode == 'exact-max':
        assert response == {'received': 'request', 'length': len(message['padding'])}
    else:
        assert 'error' in response


def test_sdk_binary_write_bypasses_windows_text_newline_translation_at_limit():
    sdk = runpy.run_path(str(SDK_PATH))
    buffer = io.BytesIO()
    destination = io.TextIOWrapper(buffer, encoding='utf-8', newline='\r\n')
    client = sdk['CoreClient'](io.StringIO(''), destination)
    message = {'type': 'result', 'result': ''}
    message['result'] = 'x' * (MAX_MESSAGE - frame_size(message))
    client.send(message)
    client._reader.join(timeout=1)
    actual = buffer.getvalue()
    assert actual == encode_frame(message)
    assert len(actual) == MAX_MESSAGE
    assert actual.endswith(b'\n') and not actual.endswith(b'\r\n')


def test_sdk_stream_configuration_uses_literal_lf(monkeypatch):
    sdk = runpy.run_path(str(SDK_PATH))
    class Stream:
        def __init__(self):
            self.calls = []
        def reconfigure(self, **arguments):
            self.calls.append(arguments)
    streams = [Stream() for _ in range(3)]
    with monkeypatch.context() as patch:
        for name, stream in zip(('stdin', 'stdout', 'stderr'), streams):
            patch.setattr(sys, name, stream)
        assert sdk['streams']() == tuple(streams[:2])
    assert all(stream.calls == [{'encoding': 'utf-8', 'newline': '\n'}] for stream in streams)

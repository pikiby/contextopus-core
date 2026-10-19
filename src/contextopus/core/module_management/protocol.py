"""Shared validation and dispatch for child-to-Core calls."""

import json

PROTOCOL = 'contextopus-core-v1'
SERVICE_PROTOCOL = 'contextopus-service-v1'
MAX_MESSAGE = 1024 * 1024
MAX_CALL_ID_BYTES = 128


class FrameTooLarge(ValueError):
    pass


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def encoded_json_size(value):
    """Exact canonical UTF-8 JSON bytes, excluding a frame's final newline."""
    return len(_json_bytes(value))


def frame_size(message):
    """Exact full frame size, including JSON envelope and final newline."""
    return encoded_json_size(message) + 1


def encode_frame(message):
    """Encode one complete frame or fail before emitting any of its bytes."""
    encoded = _json_bytes(message) + b'\n'
    if len(encoded) > MAX_MESSAGE:
        raise FrameTooLarge('Protocol message exceeds 1 MiB')
    return encoded


def decode_frame(encoded):
    """Accept only a complete, bounded UTF-8 JSON line, including its LF."""
    if isinstance(encoded, str):
        encoded = encoded.encode('utf-8')
    if not isinstance(encoded, bytes):
        raise ValueError('Protocol frame must be UTF-8 bytes or text')
    if len(encoded) > MAX_MESSAGE:
        raise FrameTooLarge('Protocol message exceeds 1 MiB')
    if not encoded.endswith(b'\n'):
        raise ValueError('Protocol frame must end with a newline')
    return json.loads(encoded.decode('utf-8'))


def _call_id_size(ident):
    if not isinstance(ident, str) or encoded_json_size(ident) > MAX_CALL_ID_BYTES:
        raise ValueError('Module Core call ID exceeds 128 JSON bytes or is not text')
    return encoded_json_size(ident)


def response_result_budget(call_id=None):
    """Available result JSON bytes; no ID reserves the largest accepted ID.

    A result measured with encoded_json_size fits the complete return frame
    when it does not exceed this budget. Envelope and newline count as bytes.
    """
    ident_size = MAX_CALL_ID_BYTES if call_id is None else _call_id_size(call_id)
    overhead = (frame_size({'type': 'return', 'id': '', 'result': None})
                - encoded_json_size('') - encoded_json_size(None))
    return MAX_MESSAGE - overhead - ident_size


def validate_call(message):
    if (not isinstance(message, dict) or message.get('type') != 'call'
            or set(message) != {'type', 'id', 'method', 'arguments'}
            or not isinstance(message['id'], str)):
        raise ValueError('Invalid module Core call')
    _call_id_size(message['id'])


def encode_error_response(call_id, error):
    """Preserve ordinary errors; explicitly replace oversized/unencodable text."""
    _call_id_size(call_id)
    try:
        return encode_frame({'type': 'return', 'id': call_id,
                             'error': {'type': type(error).__name__, 'message': str(error)}})
    except FrameTooLarge:
        description = 'Core error response exceeds 1 MiB; original error text omitted.'
    except (TypeError, ValueError, OverflowError, RecursionError):
        description = 'Core error response is not JSON encodable; original error text omitted.'
    name = type(error).__name__
    safe_name = name if name.isascii() and name.isidentifier() and len(name) <= 128 else 'Exception'
    return encode_frame({'type': 'return', 'id': call_id,
                         'error': {'type': safe_name, 'message': description}})


def encode_call_response(access, message, deadline=None):
    """Return an encoded result/error frame; valid calls remain recoverable."""
    validate_call(message)
    try:
        result = access.call(message['method'], message['arguments'], deadline=deadline)
    except Exception as exc:
        return encode_error_response(message['id'], exc)
    try:
        return encode_frame({'type': 'return', 'id': message['id'], 'result': result})
    except FrameTooLarge:
        error = FrameTooLarge('Core result response exceeds 1 MiB; request fewer items or a smaller page.')
    except (TypeError, ValueError, OverflowError, RecursionError):
        error = ValueError('Core result response is not JSON encodable.')
    return encode_error_response(message['id'], error)

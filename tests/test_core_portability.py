"""Portable lock contracts and simultaneous independent journal initialization."""

import multiprocessing
import os
from types import SimpleNamespace

import pytest

from contextopus.core import locking


def fake_windows_api(calls, error=None):
    def lock(fd, mode, length):
        calls.append((fd, mode, length, os.lseek(fd, 0, os.SEEK_CUR)))
        if error:
            raise error

    return SimpleNamespace(LK_LOCK=1, LK_NBLCK=2, LK_UNLCK=3, locking=lock)


def test_windows_backend_normalizes_stream_and_locks_byte_zero_on_first_acquire(
    tmp_path,
):
    calls = []
    api = fake_windows_api(calls)
    with (tmp_path / "lock").open("w+b") as stream:
        locking._windows_flock(stream, locking.LOCK_EX, api=api)
        assert calls == [(stream.fileno(), api.LK_LOCK, 1, 0)]
        assert stream.tell() == 0
        assert os.fstat(stream.fileno()).st_size == 0
        locking._windows_flock(stream.fileno(), locking.LOCK_UN, api=api)
        assert calls[-1] == (stream.fileno(), api.LK_UNLCK, 1, 0)
        assert stream.tell() == 0



@pytest.mark.parametrize("content", [b"", b"\0"], ids=["empty", "legacy-seed"])
def test_windows_backend_never_modifies_readonly_lock_file(tmp_path, content):
    path = tmp_path / "lock"
    path.write_bytes(content)
    before = path.stat()
    calls = []
    api = fake_windows_api(calls)
    # A read-only descriptor cannot be seeded even if its owner can write the path.
    with path.open("rb") as stream:
        stream.seek(13)
        for operation, mode in [(locking.LOCK_EX, api.LK_LOCK),
                                (locking.LOCK_UN, api.LK_UNLCK),
                                (locking.LOCK_EX | locking.LOCK_NB, api.LK_NBLCK),
                                (locking.LOCK_UN, api.LK_UNLCK)]:
            locking._windows_flock(stream, operation, api=api)
            assert calls[-1] == (stream.fileno(), mode, 1, 0)
            assert stream.tell() == 13
    assert path.read_bytes() == content
    assert path.stat().st_mtime_ns == before.st_mtime_ns


def test_windows_backend_propagates_permission_error_and_restores_cursor(tmp_path):
    path = tmp_path / "lock"
    path.touch()
    error = PermissionError("busy lock")
    calls = []
    api = fake_windows_api(calls, error)
    with path.open("rb") as stream:
        stream.seek(9)
        with pytest.raises(PermissionError) as caught:
            locking._windows_flock(stream, locking.LOCK_EX | locking.LOCK_NB,
                                   api=api)
        assert caught.value is error
        assert calls == [(stream.fileno(), api.LK_NBLCK, 1, 0)]
        assert stream.tell() == 9
    assert path.read_bytes() == b""


def test_windows_backend_restores_cursor_for_fd_nonblocking_and_failed_lock(tmp_path):
    calls = []
    path = tmp_path / "lock"
    path.write_bytes(b"abcdef")
    with path.open("r+b") as stream:
        stream.seek(3)
        api = fake_windows_api(calls)
        locking._windows_flock(
            stream.fileno(), locking.LOCK_EX | locking.LOCK_NB, api=api
        )
        assert calls[-1] == (stream.fileno(), api.LK_NBLCK, 1, 0)
        assert stream.tell() == 3
        with pytest.raises(OSError, match="busy"):
            locking._windows_flock(
                stream, locking.LOCK_EX, api=fake_windows_api(calls, OSError("busy"))
            )
        assert stream.tell() == 3


def test_public_lock_accepts_stream_and_descriptor(tmp_path):
    with (tmp_path / "lock").open("a+b") as stream:
        locking.flock(stream, locking.LOCK_EX)
        locking.flock(stream.fileno(), locking.LOCK_UN)
        locking.flock(stream.fileno(), locking.LOCK_EX | locking.LOCK_NB)
        locking.flock(stream, locking.LOCK_UN)






def native_windows_contender(path, connection):
    """Separate CRT handle/process; never emulate the native lock call."""
    locked = False
    with open(path, "a+b") as stream:
        stream.seek(11)
        connection.send("ready")
        try:
            while (command := connection.recv()) != "stop":
                if command == "acquire":
                    try:
                        locking.flock(stream, locking.LOCK_EX | locking.LOCK_NB)
                    except OSError:
                        connection.send(("busy", stream.tell()))
                    else:
                        locked = True
                        connection.send(("acquired", stream.tell()))
                elif command == "release":
                    locking.flock(stream, locking.LOCK_UN)
                    locked = False
                    connection.send(("released", stream.tell()))
        finally:
            if locked:
                locking.flock(stream, locking.LOCK_UN)
            connection.close()


@pytest.mark.skipif(os.name != "nt", reason="Requires native Windows CRT locking")
@pytest.mark.parametrize("content", [b"", b"\0"], ids=["empty", "legacy-seed"])
def test_windows_native_lock_exclusion_and_reacquisition(tmp_path, content):
    path = tmp_path / "lock"
    path.write_bytes(content)
    context = multiprocessing.get_context("spawn")
    connection, child = context.Pipe()
    process = context.Process(target=native_windows_contender, args=(str(path), child))
    started = False
    locked = False

    def receive():
        assert connection.poll(15), "Windows lock contender did not respond"
        return connection.recv()

    with path.open("a+b") as stream:
        stream.seek(7)
        try:
            locking.flock(stream, locking.LOCK_EX)
            locked = True
            assert stream.tell() == 7
            assert path.stat().st_size == len(content)
            process.start()
            started = True
            child.close()
            assert receive() == "ready"
            connection.send("acquire")
            assert receive() == ("busy", 11)
            locking.flock(stream, locking.LOCK_UN)
            locked = False
            assert stream.tell() == 7
            connection.send("acquire")
            assert receive() == ("acquired", 11)
            with pytest.raises(OSError):
                locking.flock(stream.fileno(), locking.LOCK_EX | locking.LOCK_NB)
            assert stream.tell() == 7
            connection.send("release")
            assert receive() == ("released", 11)
            locking.flock(stream.fileno(), locking.LOCK_EX | locking.LOCK_NB)
            locked = True
            assert stream.tell() == 7
            locking.flock(stream, locking.LOCK_UN)
            locked = False
        finally:
            if locked:
                locking.flock(stream, locking.LOCK_UN)
            if started:
                try:
                    connection.send("stop")
                except (BrokenPipeError, EOFError, OSError):
                    pass
                process.join(timeout=5)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
            child.close()
            connection.close()
    assert process.exitcode == 0
    assert path.read_bytes() == content

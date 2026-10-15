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
        assert os.fstat(stream.fileno()).st_size == 1
        locking._windows_flock(stream.fileno(), locking.LOCK_UN, api=api)
        assert calls[-1] == (stream.fileno(), api.LK_UNLCK, 1, 0)
        assert stream.tell() == 0


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


def record_simultaneously(root, barrier, worker):
    from contextopus.modules.workspace.analytics import EventStore
    import time

    barrier.wait(timeout=20)
    store = EventStore(root)
    for number in range(3):
        started = time.monotonic()
        event = store.begin("p", "read", {"worker": worker, "number": number})
        store.end(event, "p", started, {}, {}, result={"number": number})


def test_simultaneous_processes_bootstrap_wal_without_lost_events(tmp_path):
    from contextopus.modules.workspace.analytics import EventStore

    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(4)
    processes = [
        context.Process(target=record_simultaneously, args=(tmp_path, barrier, worker))
        for worker in range(4)
    ]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=40)
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
    report = EventStore(tmp_path).query()
    assert report["totals"]["calls"] == 12
    assert report["totals"]["unknown_outcomes"] == 0
    assert report["totals"]["errors"] == 0

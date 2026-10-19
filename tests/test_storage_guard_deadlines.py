"""Root admission observes absolute deadlines across threads and processes."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from contextopus.core.storage import StorageLayout


def test_guard_deadline_bounds_thread_contention_and_releases_mutex(tmp_path):
    layout = StorageLayout(tmp_path)
    held, release = threading.Event(), threading.Event()

    def holder():
        with layout.guard():
            held.set()
            assert release.wait(3)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(holder)
        try:
            assert held.wait(1)
            with pytest.raises(TimeoutError, match="deadline"):
                with layout.guard(deadline=time.monotonic() + .05):
                    pytest.fail("Entered a root held by another thread")
        finally:
            release.set()
        future.result(timeout=2)
    with layout.guard(deadline=time.monotonic() + .5):
        pass


def test_guard_deadline_bounds_cross_process_advisory_contention(tmp_path):
    ready, release = tmp_path / "ready", tmp_path / "release"
    root = tmp_path / "root"
    code = '''
import sys, time
from pathlib import Path
from contextopus.core.storage import StorageLayout
root, ready, release = map(Path, sys.argv[1:])
with StorageLayout(root).guard():
    ready.touch()
    deadline = time.monotonic() + 5
    while not release.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("Missing test release")
        time.sleep(.01)
'''
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(root), str(ready), str(release)],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 3
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.01)
        assert ready.exists()
        with pytest.raises(TimeoutError, match="deadline"):
            with StorageLayout(root).guard(deadline=time.monotonic() + .05):
                pytest.fail("Entered root held by another process")
        release.touch()
        stdout, stderr = process.communicate(timeout=3)
        assert process.returncode == 0, (stdout, stderr)
        with StorageLayout(root).guard(deadline=time.monotonic() + .5):
            pass
    finally:
        release.touch()
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=3)


def test_deadline_guard_preserves_nested_and_frozen_revision_rules(tmp_path):
    layout = StorageLayout(tmp_path)
    freeze = tmp_path / ".contextopus-freeze.json"
    with layout.guard(deadline=time.monotonic() + .5):
        freeze.write_text(json.dumps({"revision": "reviewed"}))
        # Existing admitted operations may nest after publishing their freeze.
        with layout.guard(deadline=time.monotonic() + .5):
            pass
    with pytest.raises(RuntimeError, match="frozen"):
        with layout.guard(deadline=time.monotonic() + .5):
            pass
    with layout.guard(frozen_revision="reviewed", deadline=time.monotonic() + .5):
        pass

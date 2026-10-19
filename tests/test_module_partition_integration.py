"""Installed folder modules write independently through their actual child SDK."""

from concurrent.futures import ThreadPoolExecutor
import errno
import json
import hashlib
import os
import sqlite3
import time
from types import SimpleNamespace

import pytest

from contextopus.core import relocation
from contextopus.core.module_storage import legacy
from contextopus.startup import Application


@pytest.mark.parametrize('platform', ['nt', 'posix'])
def test_partition_file_sync_uses_commit_compatible_descriptor(tmp_path, monkeypatch, platform):
    path = tmp_path / 'backup.sqlite3'
    original = b'unchanged backup bytes'
    path.write_bytes(original)
    descriptors, closed, synced = {}, [], []

    def open_file(filename, flags):
        descriptor = os.open(filename, flags)
        descriptors[descriptor] = flags
        return descriptor

    def commit(descriptor):
        writable = descriptors[descriptor] & (os.O_WRONLY | os.O_RDWR)
        if platform == 'nt' and not writable:
            raise OSError(errno.EBADF, 'Windows commit requires a writable descriptor')
        # Model the API rule independently of the host: a simulated POSIX
        # descriptor must not be passed to the Windows CRT's real fsync.
        synced.append(descriptor)

    def close_file(descriptor):
        os.close(descriptor)
        closed.append(descriptor)

    monkeypatch.setattr(legacy, 'os', SimpleNamespace(
        name=platform, O_RDONLY=os.O_RDONLY, O_RDWR=os.O_RDWR,
        open=open_file, fsync=commit, close=close_file,
    ))
    legacy._sync(path)
    assert synced == closed and len(synced) == 1
    expected = os.O_RDWR if platform == 'nt' else os.O_RDONLY
    assert list(descriptors.values()) == [expected]
    assert path.read_bytes() == original


def test_partition_file_sync_commits_with_the_native_api(tmp_path, monkeypatch):
    path = tmp_path / 'backup.sqlite3'
    original = b'backup bytes for native commit'
    path.write_bytes(original)
    committed = []

    def commit(descriptor):
        os.fsync(descriptor)
        committed.append(descriptor)

    monkeypatch.setattr(legacy, 'os', SimpleNamespace(
        name=os.name, O_RDONLY=os.O_RDONLY, O_RDWR=os.O_RDWR,
        open=os.open, fsync=commit, close=os.close,
    ))
    legacy._sync(path)
    assert len(committed) == 1
    assert path.read_bytes() == original


def test_partition_file_sync_preserves_io_errors_and_closes_descriptor(tmp_path, monkeypatch):
    path = tmp_path / 'backup.sqlite3'
    path.touch()
    opened, closed = [], []
    real_open, real_close = legacy.os.open, legacy.os.close

    def open_file(filename, flags):
        descriptor = real_open(filename, flags)
        opened.append(descriptor)
        return descriptor

    def close_file(descriptor):
        real_close(descriptor)
        closed.append(descriptor)

    def failed_commit(descriptor):
        raise OSError(errno.EIO, 'storage failure')

    monkeypatch.setattr(legacy, 'os', SimpleNamespace(
        name='nt', O_RDONLY=os.O_RDONLY, O_RDWR=os.O_RDWR,
        open=open_file, fsync=failed_commit, close=close_file,
    ))
    with pytest.raises(OSError, match='storage failure'):
        legacy._sync(path)
    assert opened == closed and len(opened) == 1


ADAPTER = '''
from pathlib import Path
import time

def save(arguments, core):
    if "ready" not in arguments:
        return core.storage.execute(
            'INSERT INTO "{{module}}::items" VALUES (?)', [arguments["value"]])
    with core.storage.transaction(timeout_seconds=5) as transaction:
        transaction.execute('INSERT INTO "{{module}}::items" VALUES (?)',
                            [arguments["value"]])
        Path(arguments["ready"]).touch()
        deadline = time.monotonic() + 4
        while not Path(arguments["release"]).exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("Test release signal did not arrive")
            time.sleep(.01)
    return {"committed": True}

def read(arguments, core):
    return core.storage.query('SELECT value FROM "{{module}}::items" ORDER BY value')
'''


def installable(root, module):
    folder = root / "modules" / module
    package = folder / "package"
    (package / "migrations").mkdir(parents=True)
    (package / "migrations/001-schema.sql").write_text(
        'CREATE TABLE "{{module}}::items" (value TEXT PRIMARY KEY);'
    )
    (package / "adapter.py").write_text(ADAPTER)
    manifest = {
        "id": module,
        "version": "1.0",
        "storage": {
            "engine": "sqlite", "schema_version": 1, "migrations": "migrations",
            "compatible_versions": {"min": 1, "max": 1},
        },
        "operations": [
            {"name": module + "." + name, "kind": kind,
             "handler": "adapter.py:" + name, "protocol": "contextopus-core-v1"}
            for name, kind in (("save", "execute"), ("read", "query"))
        ],
    }
    (folder / "module.json").write_text(json.dumps(manifest))


def test_real_alpha_transaction_does_not_block_installed_beta_child(tmp_path):
    for module in ("alpha", "beta"):
        installable(tmp_path, module)
    ready, release = tmp_path / "alpha-ready", tmp_path / "release-alpha"
    with Application(tmp_path, discover=False) as app:
        for module in ("alpha", "beta"):
            assert app.execute("core.module_install", {"module": module})["state"] == "enabled"
            assert app.module_storage.for_module(module).path.is_file()
        with ThreadPoolExecutor(max_workers=2) as executor:
            alpha = executor.submit(app.execute, "alpha.save", {
                "value": "alpha committed", "ready": str(ready), "release": str(release),
            })
            try:
                deadline = time.monotonic() + 3
                while not ready.exists() and not alpha.done() and time.monotonic() < deadline:
                    time.sleep(.01)
                if alpha.done():
                    alpha.result()
                assert ready.exists(), "Alpha never acknowledged its active SQL transaction"
                beta = executor.submit(app.execute, "beta.save", {"value": "beta committed"})
                assert beta.result(timeout=2)["rowcount"] == 1
                assert app.query("beta.read")["rows"] == [{"value": "beta committed"}]
                assert not alpha.done()
                assert not release.exists()
                with app.layout.guard(deadline=time.monotonic() + .5):
                    pass
            finally:
                release.touch()
            assert alpha.result(timeout=3) == {"committed": True}
        assert app.query("alpha.read")["rows"] == [{"value": "alpha committed"}]
        assert not app.module_storage.legacy_path.exists()


@pytest.mark.parametrize("interrupted", [True, False], ids=["pending", "complete"])
def test_install_partition_relocates_reads_and_retries_through_application(tmp_path, monkeypatch, interrupted):
    root = tmp_path / "source"
    for module in ("alpha", "beta"):
        installable(root, module)
    source = root / "core/storage/modules.sqlite3"
    source.parent.mkdir(parents=True)
    with sqlite3.connect(source) as database:
        database.execute('CREATE TABLE "_contextopus_module_migrations" '
                         '(module TEXT, version INTEGER, name TEXT, checksum TEXT, '
                         'PRIMARY KEY(module,version))')
        for module in ("alpha", "beta"):
            migration = root / "modules" / module / "package/migrations/001-schema.sql"
            sql = migration.read_text()
            database.execute(sql.replace("{{module}}", module))
            database.execute(f'INSERT INTO "{module}::items" VALUES (?)', [module + " original"])
            database.execute('INSERT INTO "_contextopus_module_migrations" VALUES (?,1,?,?)',
                             [module, migration.name, hashlib.sha256(sql.encode()).hexdigest()])
    real_link = legacy.os.link
    calls = 0

    def interrupted_link(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Interrupted between module publications")
        return real_link(*args, **kwargs)

    with Application(root, discover=False) as app:
        if interrupted:
            with monkeypatch.context() as patch:
                patch.setattr(legacy.os, "link", interrupted_link)
                with pytest.raises(OSError, match="between module"):
                    app.execute("core.module_install", {"module": "alpha"})
            assert app.module_storage.for_module("alpha").path.is_file()
            assert not app.module_storage.for_module("beta").path.exists()
        else:
            for module in ("alpha", "beta"):
                app.execute("core.module_install", {"module": module})
                # Completed routing must tolerate ordinary post-cutover writes;
                # the initial publication checksums are no longer current data.
                app.execute(module + ".save", {"value": module + " before relocation"})
    destination = tmp_path / "destination"
    temporary = root / "core/storage/.module-partitions-abandoned.tmp"
    temporary.write_text("discardable incomplete receipt")
    proposal = relocation.plan(root, destination)
    assert temporary.relative_to(root).as_posix() not in {entry["path"] for entry in proposal["files"]}
    assert relocation.apply(proposal)["status"] == "complete"
    assert source.is_file()
    with Application(destination, discover=False) as app:
        assert legacy.legacy_pending(destination) is interrupted
        expected_state = "storage_pending" if interrupted else "enabled"
        assert {item["state"] for item in app.query("core.modules")} == {expected_state}
        for module in ("alpha", "beta"):
            expected = [{"value": module + " original"}]
            if not interrupted:
                expected.insert(0, {"value": module + " before relocation"})
            assert app.module_storage.query(module, 'SELECT value FROM "{{module}}::items" ORDER BY value')["rows"] == expected
        assert app.module_storage.for_module("beta").path.exists() is not interrupted
        for module in ("alpha", "beta"):
            assert app.execute("core.module_install", {"module": module})["state"] == "enabled"
            expected = [{"value": module + " original"}]
            if not interrupted:
                expected.insert(0, {"value": module + " before relocation"})
            assert app.query(module + ".read")["rows"] == expected
            assert app.execute(module + ".save", {"value": module + " after retry"})["rowcount"] == 1
        assert not legacy.legacy_pending(destination)
        assert (destination / "core/storage/.module-partitions.json").is_file()
        assert len(list((destination / "core/storage/.backups").iterdir())) == 1

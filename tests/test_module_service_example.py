"""Exercise the shipped service example through a real Core and child process."""

from pathlib import Path
import shutil
import time

from contextopus.startup import Application


EXAMPLE = Path(__file__).resolve().parents[1] / "examples/modules/service-demo"


def wait_completed(app, expected):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        status = app.query("service-demo.status")
        assert status["error"] is None
        if status["completed"] == expected:
            return status
        time.sleep(0.03)
    raise AssertionError(f"Worker did not complete: {status}")


def test_example_durable_queue_shared_dispatch_and_lifecycle(tmp_path):
    shutil.copytree(EXAMPLE, tmp_path / "modules/service-demo")
    with Application(tmp_path, discover=False) as app:
        assert app.query("core.modules")[0]["state"] == "storage_pending"
        assert not app.module_storage.path.exists()
        app.execute("core.module_install", {"module": "service-demo"})
        database = app.module_storage.for_module("service-demo").path
        assert database == tmp_path / "core/storage/modules/service-demo.sqlite3"
        assert database.is_file()
        assert not app.module_storage.legacy_path.exists()
        # The root owner invokes this hook; direct source tests own the lifetime.
        app.module_manager.start_services()
        service = app.module_manager.runtime.services["service-demo"]
        first_pid = service.process.pid
        app.execute("service-demo.enqueue", {"id": "one", "amount": 2})
        assert wait_completed(app, 2)["jobs"] == [
            {"id": "one", "amount": 2, "state": "done"}
        ]
        # Repeating a submission is idempotent, even after disable/restart.
        app.execute("core.module_disable", {"module": "service-demo"})
        assert service.process.poll() is not None
        app.execute("core.module_enable", {"module": "service-demo"})
        app.module_manager.start_services()
        assert app.module_manager.runtime.services["service-demo"].process.pid != first_pid
        app.execute("service-demo.enqueue", {"id": "one", "amount": 2})
        app.execute("service-demo.enqueue", {"id": "two", "amount": 3})
        assert len(wait_completed(app, 5)["jobs"]) == 2
        active = app.module_manager.runtime.services["service-demo"]
    assert active.process.poll() is not None
    with Application(tmp_path, discover=False) as restored:
        assert restored.module_storage.for_module("service-demo").path == database
        restored.module_manager.start_services()
        status = restored.query("service-demo.status")
        assert status["completed"] == 5
        assert all(job["state"] == "done" for job in status["jobs"])

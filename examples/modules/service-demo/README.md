# Core-hosted counter service

Local source example for the unreleased service extension. It uses only the
Python standard library, Core's child SDK and packaged SQL migrations. A
background thread applies pending jobs to a counter in one short transaction.
Repeated job IDs are idempotent. Disable/restart retains jobs and totals.
`service-demo.status` exposes job health through the common query registry/MCP.

Run the actual integration test from the Core checkout without replacing an
installed Core or selecting a live root:

```console
PYTHONPATH=src .venv/bin/python -m pytest tests/test_module_service_example.py
```

For a small source-only experiment, this script creates a temporary root, copies
the package, runs it through Application and closes the worker on exit:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil
import time
from contextopus.startup import Application

with TemporaryDirectory(prefix="contextopus-service-demo-") as directory:
    root = Path(directory)
    shutil.copytree("examples/modules/service-demo", root / "modules/service-demo")
    with Application(root, discover=False) as app:
        app.execute("core.module_install", {"module": "service-demo"})
        # Direct Application use supplies the lifecycle hook normally called by
        # the root owner. No independent daemon is created.
        app.module_manager.start_services()
        app.execute("service-demo.enqueue", {"id": "one", "amount": 2})
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            status = app.query("service-demo.status")
            if status["error"] or status["completed"] == 2:
                break
            time.sleep(0.05)
        print(status)
        assert status["completed"] == 2 and status["error"] is None
```

Run saved Python with `PYTHONPATH=src .venv/bin/python PATH_TO_SCRIPT` from the
checkout. Installation, enablement and operation dispatch use the same Core
registry as MCP's `write` and `read` tools. This example has no embeddings or RAG
dependency; the exact shared-resource SDK and session-search adaptation handoff
are in `docs/implementation/module-services-local.md`.

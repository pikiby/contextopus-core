"""Real child capability boundaries and derived-file reconciliation."""

from pathlib import Path
from types import SimpleNamespace
import threading

import pytest

from contextopus.core.module_management.core_access import ModuleCoreAccess
from contextopus.core.module_storage import ModuleStorage
from contextopus.core.storage import StorageLayout


def access(root, kind="execute", module="example"):
    layout = StorageLayout(root)
    app = SimpleNamespace(layout=layout, module_storage=ModuleStorage(layout))
    return ModuleCoreAccess(app, module, kind=kind)


def put(client, **overrides):
    arguments = dict(directory="profiles", path="runner.md", metadata={"id": "runner", "type": "profile", "model": "test"}, text="Run assigned tests.")
    arguments.update(overrides)
    return client.call("documents.write", arguments)


def test_child_file_lifecycle_and_shared_plan(tmp_path):
    with_client = access(tmp_path)
    try:
        item = put(with_client)
        snapshot = with_client.call("documents.scan", {"directory": "profiles"})
        assert snapshot["complete"] and snapshot["documents"][0] == item
        assert item["text"] == "Run assigned tests."
        assert item["metadata"]["model"] == "test"
        path = Path(item["path"])
        path.rename(path.with_name("renamed.md"))
        moved = with_client.call("documents.scan", {"directory": "profiles"})
        delta = with_client.call("documents.plan", {"collection": "profiles", "documents": moved["documents"], "previous": [item], "complete": True})
        assert len(delta["refresh"]) == 1 and not delta["delete"]
        with pytest.raises(ValueError, match="changed"):
            put(with_client, path="renamed.md", expected_revision="wrong")
        with_client.call("documents.delete", {"directory": "profiles", "path": "renamed.md", "expected_revision": item["file_revision"]})
        assert with_client.call("documents.plan", {"collection": "profiles", "documents": [], "previous": [item]})["delete"] == []
        assert len(with_client.call("documents.plan", {"collection": "profiles", "documents": [], "previous": [item], "complete": True})["delete"]) == 1
    finally:
        with_client.close()


def test_query_and_path_escape_rejected(tmp_path):
    query = access(tmp_path, "query")
    try:
        with pytest.raises(PermissionError):
            put(query)
        with pytest.raises(ValueError):
            query.call("documents.scan", {"directory": "../other"})
        with pytest.raises(ValueError, match="missing"):
            query.call("documents.scan", {"directory": "absent"})
        assert not (tmp_path / "modules").exists()
    finally:
        query.close()
    writer = access(tmp_path)
    try:
        for value in ("../other", "/tmp/other", "a/../../other", "a\\other"):
            with pytest.raises(ValueError):
                put(writer, directory=value)
        writer.call("documents.prepare", {"directory": "profiles"})
        assert writer.call("documents.scan", {"directory": "profiles"}) == {"documents": [], "complete": True}
    finally:
        writer.close()


def test_two_writers_cannot_replace_same_revision(tmp_path):
    a, b = access(tmp_path), access(tmp_path)
    try:
        item = put(a)
        outcomes = []
        def write(client, text):
            try:
                put(client, text=text, expected_revision=item["file_revision"])
                outcomes.append("saved")
            except ValueError:
                outcomes.append("stale")
        threads = [threading.Thread(target=write, args=(client, text)) for client, text in ((a, "first"), (b, "second"))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        assert sorted(outcomes) == ["saved", "stale"]
    finally:
        a.close()
        b.close()

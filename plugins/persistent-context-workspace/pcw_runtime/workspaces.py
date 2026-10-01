"""Explicit workspace creation and versioned, recoverable format migration."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import uuid

from .runtime import PCWError, _id, _revision, _parse
from .policies import policies


FORMAT_VERSION = 1  # Workspace format, deliberately independent of plugin releases.
EMPTY_PROJECT = "# Project\n\nPurpose, goals, requirements and boundaries have not been specified.\n"


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


class WorkspaceMixin:
    def _format_path(self):
        path = self.control.root / "format.json"
        self.control.safe(path)
        return path

    def _existing(self):
        self.engine._assert_safe(self.engine.root)
        if not self.engine.root.is_dir():
            raise PCWError("Workspace does not exist. Select an existing context or explicitly use pcw-create.")

    def _format(self):
        self._existing()
        path = self._format_path()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if type(data.get("format_version")) is not int:
                raise PCWError("Invalid workspace format metadata")
            return data["format_version"]
        # Recognize the actual 0.8–0.10 structure, not the directory's name.
        for path in (self.engine.knowledge, self.engine.state / "active.json", self.engine.root / "INSTRUCTIONS.md"):
            self.engine._assert_safe(path)
        if (self.engine.knowledge.is_dir() and (self.engine.state / "active.json").is_file()
                and (self.engine.root / "INSTRUCTIONS.md").is_file()):
            active = json.loads((self.engine.state / "active.json").read_text(encoding="utf-8"))
            if type(active.get("index_format", 1)) is int and active.get("index_format", 1) in (1, 2) and {"config", "table"} <= active.keys():
                return 0
        raise PCWError("Unrecognized legacy workspace structure; inspect or restore it before migration")

    def _require_format(self, *, storage=True):
        version = self._format()
        if version != FORMAT_VERSION:
            raise PCWError(f"Workspace format {version}; required {FORMAT_VERSION}. Use pcw-upgrade; opening does not migrate.")
        required = ["INSTRUCTIONS.md", "PROJECT.md", "current"]
        if storage:
            required += ["knowledge", ".pcw-runtime/active.json"]
        for relative in required:
            path = self.engine.root / relative
            self.engine._assert_safe(path)
            if not path.exists():
                raise PCWError(f"Workspace file missing: {relative}; restore it, do not initialize defaults")

    def workspace_inspect(self):
        """No creation, indexing, embedding load or migration."""
        version = self._format()
        return {"workspace": str(self.engine.root), "format_version": version,
                "required_format": FORMAT_VERSION, "compatible": version == FORMAT_VERSION,
                "next_action": "open" if version == FORMAT_VERSION else "pcw-upgrade"}

    def workspace_create(self, request_id: str, instructions_content: str, project_content: str,
                         user_request: str):
        _id(request_id)
        if not isinstance(user_request, str) or not user_request.strip():
            raise PCWError("An explicit user request to create this context is required")
        if not isinstance(project_content, str) or not project_content.strip():
            raise PCWError("Supply the project description agreed with the user")
        settings = policies(instructions_content, creation=True)
        signature = _revision(encode([request_id, instructions_content, project_content, user_request]))
        with self.control.guard():
            record = self.control.root / "creation.json"
            self.control.safe(record)
            previous = json.loads(record.read_text()) if record.exists() else None
            if previous:
                if previous["signature"] != signature:
                    raise PCWError("Workspace already has a different creation request")
                if previous["status"] == "created":
                    self._require_format()
                    return {"status": "created", "workspace": str(self.engine.root), "replayed": True}
            elif self.engine.root.exists():
                raise PCWError("Workspace already exists; opening or migration never replaces it")
            else:
                previous = {"signature": signature, "status": "creating"}
                self.control.write(record, encode(previous))
            self.engine._assert_safe(self.engine.knowledge)
            self.engine.knowledge.mkdir(parents=True, exist_ok=True)
            self.engine.state.mkdir(exist_ok=True)
            for relative, content in {"INSTRUCTIONS.md": instructions_content, "PROJECT.md": project_content}.items():
                path = self.engine.root / relative
                self.engine._assert_safe(path)
                if path.exists() and path.read_bytes().decode("utf-8") != content:
                    raise PCWError(f"Interrupted creation conflicts with {relative}; inspect before continuing")
                if not path.exists():
                    self.engine._write(path, content)
            self.engine._assert_safe(self.engine.root / "current")
            (self.engine.root / "current").mkdir(exist_ok=True)
            with self.engine._guard():
                self._instructions(initialize=True)
            self.control.write(self._format_path(), encode({"format_version": FORMAT_VERSION}))
            self._require_format()
            history = self._history_record("initial-" + _revision(request_id))
            previous["status"] = "created"
            self.control.write(record, encode(previous))
            return {"status": "created", "workspace": str(self.engine.root), "format_version": FORMAT_VERSION,
                    "settings": settings, "instructions": self._instructions(), "project": self.project_read(), "history": history}

    def _source_files(self):
        """Literal source fingerprint excludes rebuildable indexes and pending work."""
        result = {}
        for path in sorted(self.engine.root.rglob("*")):
            relative = path.relative_to(self.engine.root)
            if relative.parts[0] in {".git", ".pcw-runtime", "tmp"}:
                continue
            self.engine._assert_safe(path)
            if path.is_file():
                result[relative.as_posix()] = _revision(path.read_bytes().decode("utf-8"))
        active = self.engine.state / "active.json"
        self.engine._assert_safe(active)
        if active.is_file():
            result[".pcw-runtime/active.json"] = _revision(active.read_text())
        return result

    def upgrade_plan(self):
        version = self._format()
        if version not in (0, FORMAT_VERSION):
            raise PCWError("No supported migration path for this workspace format")
        state = {"from_version": version, "to_version": FORMAT_VERSION, "sources": self._source_files()}
        return {**state, "revision": _revision(encode(state)),
                "changes": [] if version == FORMAT_VERSION else [
                    "Create PROJECT.md only if absent; do not infer goals from old notes",
                    "Create current/ only if absent; retain legacy Current verbatim",
                    "Upgrade the derived index format if necessary",
                    "Record workspace format after verification"],
                "instructions_preserved": True, "next_action": "none" if version == FORMAT_VERSION else "upgrade_apply"}

    def upgrade_apply(self, expected_revision: str, user_request: str):
        if not isinstance(user_request, str) or not user_request.strip():
            raise PCWError("Explicit migration request required")
        self._existing()
        with self.control.guard():
            record_path = self.control.root / "migration.json"
            self.control.safe(record_path)
            operation = json.loads(record_path.read_text()) if record_path.exists() else None
            if operation and operation["revision"] == expected_revision and operation["status"] == "complete":
                self._require_format()
                return {**operation, "replayed": True}
            if operation and operation["status"] not in {"complete", "snapshotting"}:
                if operation["revision"] != expected_revision:
                    raise PCWError("Resume the pending migration revision before starting another")
            else:
                plan = self.upgrade_plan()
                if plan["revision"] != expected_revision:
                    raise PCWError("Workspace changed since migration review; inspect a fresh plan")
                if not plan["changes"]:
                    return {"status": "current", "format_version": FORMAT_VERSION}
                if any(c["state"] in {"active", "starting", "closing", "restarting"} for c in self._records()["cycles"].values()):
                    raise PCWError("Finish or cancel existing cycles before migration")
                operation = {"revision": expected_revision, "status": "snapshotting", "sources": plan["sources"],
                             "backup": str(self.control.root / "backups" / uuid.uuid4().hex / "workspace")}
                self.control.write(record_path, encode(operation))
                backup = Path(operation["backup"])
                self.control.safe(backup)
                for path in self.engine.root.rglob("*"):
                    self.engine._assert_safe(path)
                shutil.copytree(self.engine.root, backup)
                operation["status"] = "applying"
                self.control.write(record_path, encode(operation))
            for relative, digest in operation["sources"].items():
                if relative == ".pcw-runtime/active.json":
                    continue  # A completed index transition may already have changed this pointer.
                path = self.engine.root / relative
                self.engine._assert_safe(path)
                if not path.is_file() or _revision(path.read_bytes().decode("utf-8")) != digest:
                    raise PCWError("Source changed during interrupted migration; inspect the retained backup")
            project = self.engine.root / "PROJECT.md"
            self.engine._assert_safe(project)
            if not project.exists():
                self.engine._write(project, EMPTY_PROJECT)
            self.engine._assert_safe(self.engine.root / "current")
            (self.engine.root / "current").mkdir(exist_ok=True)
            with self.engine._guard():
                self._instructions()
                # Validate preserved source files and links without rewriting them.
                for material in self.engine.materials.values():
                    _parse((self.engine.root / material.path).read_text())
            self.control.write(self._format_path(), encode({"format_version": FORMAT_VERSION}))
            self._require_format()
            history = self._history_record("migration-" + expected_revision)
            operation["status"] = "complete"
            self.control.write(record_path, encode(operation))
            return {**operation, "format_version": FORMAT_VERSION, "semantic_rework": "not_performed", "history": history}

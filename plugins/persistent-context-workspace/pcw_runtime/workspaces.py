"""Explicit workspace creation and versioned, recoverable format migration."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid

from .runtime import PCWError, _id, _revision, _parse
from .policies import policies


FORMAT_VERSION = 1  # Workspace format, deliberately independent of plugin releases.
EMPTY_PROJECT = "# Project\n\nPurpose, goals, requirements and boundaries have not been specified.\n"


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


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
        """Bind review to permanent sources AND temporary work, excluding derived files."""
        result = {}
        for path in sorted(self.engine.root.rglob("*")):
            relative = path.relative_to(self.engine.root)
            if relative.parts[0] in {".git", ".pcw-runtime"}:
                continue
            self.engine._assert_safe(path)
            if path.is_file():
                result[relative.as_posix()] = file_hash(path)
        active = self.engine.state / "active.json"
        self.engine._assert_safe(active)
        if active.is_file():
            result[".pcw-runtime/active.json"] = _revision(active.read_text())
        return result

    def _migration_tree(self, root, *, control=False):
        """Binary-safe snapshot manifest; never recurse into previous backups."""
        result = {}
        check = self.control.safe if control else self.engine._assert_safe
        check(root)
        for directory, dirs, names in os.walk(root):
            if control and Path(directory) == root:
                dirs[:] = [name for name in dirs if name != "backups"]
                names = [name for name in names if name not in {"lock", "migration.json"}]
            for name in sorted(dirs + names):
                path = Path(directory) / name
                relative = path.relative_to(root)
                check(path)
                if path.is_file():
                    result[relative.as_posix()] = file_hash(path)
                elif path.is_dir():
                    result[relative.as_posix() + "/"] = None
                else:
                    raise PCWError(f"Unsupported migration source: {path}")
        return result

    @staticmethod
    def _migration_title(text):
        return next((line.lstrip("# ").strip() for line in text.splitlines()
                     if line.startswith("# ")), "")

    def _migration_work(self):
        """Report saved work, not guessed live-agent activity. Never apply or close it."""
        records = self._records()
        if not isinstance(records.get("cycles"), dict) or not isinstance(records.get("starts"), dict):
            raise PCWError("Unrecognized cycle registry; inspect it before migration")
        work, blockers = [], []
        for cycle_id, cycle in sorted(records["cycles"].items()):
            _id(cycle_id)
            if cycle.get("state") in {"closed", "cancelled", "replaced"}:
                continue
            item = {"cycle_id": cycle_id, "state": cycle.get("state"),
                    "request_ids": [key for key, value in records["starts"].items() if value == cycle_id],
                    "task_id": cycle.get("task_id"), "temporary_materials": [], "proposals": []}
            work.append(item)
            # Interrupted state transitions require their own recovery, not cancellation.
            if cycle.get("state") != "active":
                blockers.append({"cycle_id": cycle_id, "reason": "Recover the interrupted or unsupported cycle state: " + str(cycle.get("state"))})
            if cycle.get("purpose", "work") not in {"work", "instructions", "audit", "rework"}:
                blockers.append({"cycle_id": cycle_id, "reason": "Unsupported cycle purpose"})
            for path in sorted((self._tmp(cycle_id) / "materials").glob("*.md")):
                self.engine._assert_safe(path)
                item["temporary_materials"].append({"path": str(path.relative_to(self.engine.root)),
                    "title": self._migration_title(path.read_text(encoding="utf-8"))})
            for proposal_id, entry in sorted(cycle.get("proposals", {}).items()):
                summary = {"proposal_id": proposal_id, "state": entry.get("state"), "changes": []}
                item["proposals"].append(summary)
                try:
                    if entry.get("state") not in {"prepared", "applied", "discarded", "no_changes", "applying", "partial", "index_pending"}:
                        raise PCWError("Unsupported proposal state")
                    plan = self._load_plan(cycle_id, proposal_id, entry)
                    if (plan.get("cycle_id") != cycle_id or plan.get("proposal_id") != proposal_id
                            or plan.get("kind", "knowledge") not in {"knowledge", "instructions", "project"}):
                        raise PCWError("Unsupported proposal identity or kind")
                    for material_id, change in plan["entries"].items():
                        before, after = change["before"], change["after"]
                        for snapshot in (before, after):
                            if snapshot is not None and _revision(snapshot["text"]) != snapshot["fingerprint"]:
                                raise PCWError("Proposal snapshot fingerprint mismatch")
                        snapshot = after or before
                        summary["changes"].append({"id": material_id, "path": snapshot["path"],
                            "title": self._migration_title(snapshot["text"]),
                            "action": "delete" if after is None else "create" if before is None else "update"})
                except (PCWError, OSError, ValueError, KeyError, TypeError) as exc:
                    blockers.append({"cycle_id": cycle_id, "proposal_id": proposal_id, "reason": str(exc)})
        return work, blockers

    def upgrade_plan(self):
        with self.control.guard():
            return self._upgrade_plan()

    def _project_description_status(self):
        path = self.engine.root / "PROJECT.md"
        self.engine._assert_safe(path)
        if not path.exists():
            status = "missing"
        else:
            text = path.read_text(encoding="utf-8").strip()
            status = "empty" if not text else "placeholder" if text == EMPTY_PROJECT.strip() else "present"
        # Presence is a structural observation, not a review of accuracy or completeness.
        return {"path": "PROJECT.md", "status": status, "content_reviewed": False}

    def _upgrade_plan(self):
        version = self._format()
        if version not in (0, FORMAT_VERSION):
            raise PCWError("No supported migration path for this workspace format")
        state = {"from_version": version, "to_version": FORMAT_VERSION, "sources": self._source_files(),
                 "control_sources": self._migration_tree(self.control.root, control=True)}
        work, blockers = self._migration_work()
        operation_path = self.control.root / "migration.json"
        self.control.safe(operation_path)
        operation = json.loads(operation_path.read_text()) if operation_path.exists() else None
        pending = operation if operation and operation["status"] != "complete" else None
        if pending:
            try:
                if "workspace_snapshot" not in pending:
                    raise PCWError("Pending migration uses an older recovery format; inspect its retained backup")
                if pending["status"] == "snapshotting":
                    if (self._migration_tree(self.engine.root) != pending["workspace_snapshot"]
                            or state["control_sources"] != pending["control_sources"]):
                        raise PCWError("Source changed during snapshot; inspect the retained backup")
                else:
                    self._migration_verify_sources(pending)
                    self._migration_verify_backup(pending)
            except (PCWError, OSError, ValueError, KeyError, TypeError) as exc:
                blockers.append({"revision": pending["revision"], "reason": str(exc)})
        return {**state, "workspace": str(self.engine.root), "revision": _revision(encode(state)),
                "compatible": version == FORMAT_VERSION, "ready": not blockers,
                "pending_work": work, "blockers": blockers,
                "project_description": self._project_description_status(),
                "resume_revision": pending["revision"] if pending else None,
                "backup": pending["backup"] if pending else None,
                "backup_scope": ["entire workspace including tmp and index", "control state excluding locks, migration receipt and older backups"],
                "changes": [] if version == FORMAT_VERSION else [
                    "Create PROJECT.md only if absent; do not infer goals from old notes",
                    "Create current/ only if absent; retain legacy Current verbatim",
                    "Upgrade the derived index format if necessary",
                    "Record workspace format after verification"],
                "instructions_preserved": True, "pending_work_preserved": True,
                "next_action": "inspect_blockers" if blockers else "upgrade_apply" if pending or version != FORMAT_VERSION else "none"}

    def _migration_copy(self, source, destination, manifest):
        """Resume one immutable snapshot; never overwrite a completed snapshot file."""
        self.control.safe(destination)
        destination.mkdir(parents=True, exist_ok=True)
        for relative, digest in manifest.items():
            target = destination / relative
            self.control.safe(target)
            if digest is None:
                target.mkdir(parents=True, exist_ok=True)
                continue
            if target.exists():
                if not target.is_file() or file_hash(target) != digest:
                    raise PCWError(f"Retained backup changed: {target}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".snapshot-", delete=False) as stream:
                    temporary = Path(stream.name)
                shutil.copy2(source / relative, temporary)
                if file_hash(temporary) != digest:
                    raise PCWError(f"Source changed while taking backup: {source / relative}")
                with temporary.open("rb") as stream:
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

    def _migration_verify_backup(self, operation):
        for field, manifest_key in (("backup", "workspace_snapshot"), ("control_backup", "control_sources")):
            root = Path(operation[field])
            self.control.safe(root)
            for relative, digest in operation[manifest_key].items():
                path = root / relative
                self.control.safe(path)
                if (not path.is_dir() if digest is None else not path.is_file() or file_hash(path) != digest):
                    raise PCWError(f"Migration backup verification failed: {path}")

    def _migration_verify_sources(self, operation):
        current = self._source_files()
        expected = operation["sources"]
        # The only new source allowed during this transition is the empty PROJECT.
        if "PROJECT.md" not in expected and "PROJECT.md" in current:
            if current.pop("PROJECT.md") != _revision(EMPTY_PROJECT):
                raise PCWError("New PROJECT changed during migration; inspect before retrying")
        current.pop(".pcw-runtime/active.json", None)  # The derived index may have transitioned.
        if current != {key: value for key, value in expected.items() if key != ".pcw-runtime/active.json"}:
            raise PCWError("Source changed during interrupted migration; inspect the retained backup")
        control = self._migration_tree(self.control.root, control=True)
        # A lost acknowledgement after the format marker is retryable.
        if "format.json" not in operation["control_sources"]:
            control.pop("format.json", None)
        # Opening an older runtime may establish this technical marker.
        if "workspace-opened.json" not in operation["control_sources"]:
            control.pop("workspace-opened.json", None)
        if control != operation["control_sources"]:
            raise PCWError("Cycle or control state changed during migration; inspect the retained backup")

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
                return {**operation, "replayed": True,
                        "project_description": self._project_description_status()}
            if operation and operation["status"] != "complete":
                if operation["revision"] != expected_revision:
                    raise PCWError("Resume the pending migration revision before starting another")
                if "workspace_snapshot" not in operation:
                    raise PCWError("Pending migration uses an older recovery format; inspect its retained backup before continuing")
            else:
                plan = self.upgrade_plan()
                if plan["revision"] != expected_revision:
                    raise PCWError("Workspace changed since migration review; inspect a fresh plan")
                if not plan["changes"]:
                    return {"status": "current", "format_version": FORMAT_VERSION,
                            "pending_work": plan["pending_work"], "blockers": plan["blockers"],
                            "project_description": plan["project_description"]}
                if not plan["ready"]:
                    raise PCWError("Migration preflight blocked: " + encode(plan["blockers"]))
                backup_root = self.control.root / "backups" / uuid.uuid4().hex
                operation = {"revision": expected_revision, "status": "snapshotting", "sources": plan["sources"],
                             "control_sources": plan["control_sources"], "pending_work": plan["pending_work"],
                             "workspace_snapshot": self._migration_tree(self.engine.root),
                             "backup": str(backup_root / "workspace"), "control_backup": str(backup_root / "control")}
                self.control.write(record_path, encode(operation))
            if operation["status"] == "snapshotting":
                # All sources must still match the reviewed snapshot, even on retry.
                if (self._migration_tree(self.engine.root) != operation["workspace_snapshot"]
                        or self._migration_tree(self.control.root, control=True) != operation["control_sources"]):
                    raise PCWError("Source changed during snapshot; inspect the retained backup")
                self._migration_copy(self.engine.root, Path(operation["backup"]), operation["workspace_snapshot"])
                self._migration_copy(self.control.root, Path(operation["control_backup"]), operation["control_sources"])
                self._migration_verify_backup(operation)
                operation["status"] = "applying"
                self.control.write(record_path, encode(operation))
            self._migration_verify_backup(operation)
            self._migration_verify_sources(operation)
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
                index_status = self.engine.status()
            self._migration_verify_sources(operation)
            self.control.write(self._format_path(), encode({"format_version": FORMAT_VERSION}))
            self._require_format()
            history = self._history_record("migration-" + expected_revision)
            operation["status"] = "complete"
            operation["pending_preparation"] = index_status["pending_preparation"]
            operation["pending_work_preserved"] = True
            self.control.write(record_path, encode(operation))
            return {**operation, "format_version": FORMAT_VERSION, "semantic_rework": "not_performed",
                    "project_description": self._project_description_status(), "history": history}

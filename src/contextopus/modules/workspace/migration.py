"""Recoverable file-and-index migration. Approval records remain immutable."""

from .text_io import read_utf8

import copy
import json
import os
from pathlib import Path
import uuid

import lancedb
import yaml

from .runtime import PCWError, _parse, _id, _revision
from .sources import migrate_sources, needs_source_upgrade, declarations
from .shared import topic_name
from .workspaces import EMPTY_PROJECT, FORMAT_VERSION, encode, file_hash
from .records import project_record, task_record, document_id, validate_metadata


class FormatMigrationMixin:
    def _format_problems(self):
        problems = []
        active = self.engine.state / "active.json"
        self.engine._assert_safe(active)
        if not active.is_file():
            problems.append("Shared index is missing")
        elif not (self.engine.state / "lancedb").is_dir():
            problems.append("Shared vector database is missing")
        found_ids = set()
        for path in sorted(self.engine.knowledge.rglob("*.md")):
            if any(
                p.startswith(".") for p in path.relative_to(self.engine.knowledge).parts
            ):
                continue
            self.engine._assert_safe(path)
            metadata, body = _parse(path.read_bytes().decode("utf-8"))
            if "id" not in metadata:
                problems.append(f"Missing YAML ID in {path.name}")
            else:
                _id(metadata["id"])
                if metadata["id"] in found_ids:
                    problems.append(f"Duplicate YAML ID: {metadata['id']}")
                found_ids.add(metadata["id"])
            try:
                validate_metadata(metadata)
            except PCWError as exc:
                problems.append(f"{path.name}: {exc}")
            if needs_source_upgrade(body):
                problems.append(f"Legacy sources in {path.name}")
        if (self.engine.root / "PROJECT.md").exists() or (self.engine.root / "current").exists():
            problems.append("Legacy project/task storage remains")
        return problems

    def _migration_receipt_path(self):
        path = self.control.root / "migration-v3.json"
        self.control.safe(path)
        return path

    def _check_previous_migration(self):
        """Continue a 0.11-era interrupted transition only from its verified state."""
        path = self.control.root / "migration.json"
        self.control.safe(path)
        if not path.exists():
            return
        previous = json.loads(read_utf8(path))
        if previous.get("status") == "complete":
            return
        if not {"workspace_snapshot", "control_sources", "sources"} <= previous.keys():
            raise PCWError(
                "Older interrupted migration needs recovery from its retained backup"
            )
        if previous["status"] == "snapshotting":
            if (
                self._migration_tree(self.engine.root) != previous["workspace_snapshot"]
                or self._v2_control() != previous["control_sources"]
            ):
                raise PCWError("Source changed during previous migration snapshot")
            return
        self._migration_verify_backup(previous)
        actual = self._v2_sources()
        expected = {
            k: v
            for k, v in previous["sources"].items()
            if k != ".pcw-runtime/active.json"
        }
        if "PROJECT.md" not in expected and actual.get("PROJECT.md") == _revision(
            EMPTY_PROJECT
        ):
            actual.pop("PROJECT.md")
        if actual != expected:
            raise PCWError(
                "Source changed during previous migration; inspect its backup"
            )
        ignored = {"format.json", "workspace-opened.json"}
        if {k: v for k, v in self._v2_control().items() if k not in ignored} != {
            k: v for k, v in previous["control_sources"].items() if k not in ignored
        }:
            raise PCWError("Control state changed during previous migration")

    def _v2_sources(self):
        result = self._source_files()
        # A shared pointer may change while another context is being migrated.
        result.pop(".pcw-runtime/active.json", None)
        return result

    def _v2_control(self):
        return {
            k: v
            for k, v in self._migration_tree(self.control.root, control=True).items()
            if k != "migration-v3.json"
        }

    def _v2_transforms(self, version):
        files, ids, aliases = {}, {}, {}
        indexed_paths = None
        for path in sorted(self.engine.knowledge.rglob("*.md")):
            if any(
                p.startswith(".") for p in path.relative_to(self.engine.knowledge).parts
            ):
                continue
            self.engine._assert_safe(path)
            text = path.read_bytes().decode("utf-8")
            metadata, body = _parse(text)
            relative = path.relative_to(self.engine.root).as_posix()
            if version >= 2 and "id" not in metadata:
                if indexed_paths is None:
                    indexed_paths = {}
                    active_path = self.engine.state / "active.json"
                    if (
                        active_path.is_file()
                        and (self.engine.state / "lancedb").is_dir()
                    ):
                        active = json.loads(read_utf8(active_path))
                        table = lancedb.connect(
                            str(self.engine.state / "lancedb")
                        ).open_table(active["table"])
                        for row in (
                            table.search()
                            .where(f"workspace = '{_id(self.engine.workspace)}'")
                            .select(["material_id", "path"])
                            .limit(None)
                            .to_list()
                        ):
                            indexed_paths.setdefault(row["path"], set()).add(
                                row["material_id"]
                            )
                candidates = indexed_paths.get(relative, set())
                if len(candidates) != 1:
                    raise PCWError(
                        f"Cannot recover an unambiguous YAML ID for {relative}; restore it from history"
                    )
                ident = _id(next(iter(candidates)))
            else:
                ident = _id(metadata["id"] if version >= 2 else path.name)
            if ident in ids:
                raise PCWError(f"Duplicate material ID: {ident}")
            ids[ident] = relative
            if version < 2 and metadata.get("id"):
                alias = _id(metadata["id"])
                if alias in aliases and aliases[alias] != ident:
                    raise PCWError(f"Duplicate legacy ID: {alias}")
                aliases[alias] = ident
            files[relative] = {
                "id": ident,
                "metadata": metadata,
                "content": body,
                "before": text,
            }
        extra = []
        project_path = self.engine.root / "PROJECT.md"
        if project_path.is_file():
            text = read_utf8(project_path)
            ident, converted = project_record(self.engine.workspace, text)
            extra.append((project_path, ident, text, converted))
        for path in (self.engine.root / "current").rglob("*"):
            self.engine._assert_safe(path)
            if path.is_file() and (path.parent != self.engine.root / "current" or path.suffix != ".md"):
                raise PCWError(f"Unrecognized Current source: {path.name}; classify it before migration")
        for path in sorted((self.engine.root / "current").glob("*.md")):
            self.engine._assert_safe(path)
            text = read_utf8(path)
            metadata, _ = _parse(text)
            ident = _id(metadata.get("id", path.stem))
            extra.append((path, ident, text, task_record(ident, text)))
        # Enumerate physical entries: constructed uppercase/lowercase aliases can
        # both resolve to one file on case-insensitive filesystems.
        for path in sorted(self.engine.root.iterdir()):
            if path.name.casefold() == "current.md" and path.is_file():
                self.engine._assert_safe(path)
                text = read_utf8(path)
                metadata, _ = _parse(text)
                ident = _id(metadata.get("id", document_id(self.engine.workspace, path.name)))
                extra.append((path, ident, text, task_record(ident, text)))
        for path, ident, before, converted in extra:
            if ident in ids:
                raise PCWError(f"Duplicate migrated record ID: {ident}")
            relative = path.relative_to(self.engine.root).as_posix()
            metadata, body = _parse(converted)
            ids[ident] = relative
            files[relative] = {"id": ident, "metadata": metadata, "content": body,
                               "before": before, "converted": converted}
        # Reject global identity collisions before changing any source file.
        for root in self.engine.root.parent.iterdir():
            if root.name.startswith(".") or root == self.engine.root:
                continue
            self.engine._assert_safe(root)
            if not root.is_dir():
                continue
            for path in (root / "knowledge").rglob("*.md"):
                self.engine._assert_safe(path)
                metadata, _ = _parse(path.read_bytes().decode("utf-8"))
                other = metadata.get("id", path.name)
                if other in ids:
                    raise PCWError(
                        f"Duplicate ID {other} in {root.name}; resolve before migration"
                    )
        occupied, transforms = set(), {}
        for relative, item in files.items():
            ident = item["id"]
            after_path = relative
            if "converted" in item:
                after_path = "knowledge/" + topic_name(item["content"], ident)
            elif version < 2 or Path(relative).name == ident:
                after_path = (
                    Path(relative).parent / topic_name(item["content"], ident)
                ).as_posix()
            if after_path in occupied or (
                after_path != relative and after_path in files
            ):
                after_path = (
                    Path(after_path).with_suffix("").as_posix()
                    + "-"
                    + ident.removesuffix(".md")
                    + ".md"
                )
            if after_path in occupied or (
                after_path != relative and after_path in files
            ):
                raise PCWError(f"Migration filename collision: {after_path}")
            occupied.add(after_path)
            text = self._normalize_snapshot(item.get("converted", item["before"]), ident, aliases)
            transforms[relative] = {
                "id": ident,
                "before": item["before"],
                "path": after_path,
                "text": text,
            }
        return transforms, aliases

    @staticmethod
    def _normalize_snapshot(text, ident, aliases):
        metadata, body = _parse(text)
        metadata["id"] = ident
        metadata.setdefault("type", "knowledge")
        validate_metadata(metadata)
        links = metadata.get("links", [])
        if not isinstance(links, list):
            raise PCWError("links must be a list")
        metadata["links"] = list(
            dict.fromkeys(aliases.get(_id(i), i) for i in links if i != ident)
        )
        return (
            "---\n"
            + yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True)
            + "---\n"
            + migrate_sources(body)
        )

    def _proposal_overlays(self, transforms, aliases):
        result = {}
        mapped = {i["id"]: i["path"] for i in transforms.values()}
        for cycle_id, cycle in self._records()["cycles"].items():
            for proposal_id, entry in cycle.get("proposals", {}).items():
                if entry["state"] not in {
                    "prepared",
                    "applying",
                    "partial",
                    "index_pending",
                }:
                    continue
                plan = self._load_plan(cycle_id, proposal_id, entry)
                if plan.get("kind") == "instructions":
                    continue
                plan = self._execution_plan(plan)
                plan = copy.deepcopy(plan)
                if plan.get("kind") == "project":
                    project = transforms.get("PROJECT.md")
                    if project is None:
                        raise PCWError("Pending legacy PROJECT proposal has no migration target")
                    change = plan["entries"].pop("PROJECT.md")
                    for snapshot in change.values():
                        if snapshot:
                            _, snapshot["text"] = project_record(self.engine.workspace, snapshot["text"])
                    plan["entries"][project["id"]] = change
                    plan["kind"] = "knowledge"
                for ident, change in plan["entries"].items():
                    for key in ("before", "after"):
                        snapshot = change[key]
                        if snapshot is None:
                            continue
                        old_path = snapshot["path"]
                        if ident in mapped:
                            new_name = Path(mapped[ident]).name
                        else:
                            new_name = topic_name(_parse(snapshot["text"])[1], ident)
                        snapshot["path"] = mapped[ident] if old_path == "PROJECT.md" and ident in mapped else str(Path(old_path).parent / new_name)
                        snapshot["text"] = self._normalize_snapshot(
                            snapshot["text"], ident, aliases
                        )
                        snapshot["fingerprint"] = _revision(snapshot["text"])
                result[cycle_id + "/" + proposal_id] = {
                    "revision": entry["revision"],
                    "plan": plan,
                }
        return result

    def _execution_plan(self, plan):
        # Immutable approvals keep their original digest. Technical overlays adapt
        # paths/metadata only; they never apply a proposal during migration.
        for name in ("migration-v3.json", "migration-v2.json"):
            receipt = self.control.root / name
            self.control.safe(receipt)
            if not receipt.exists():
                continue
            operation = json.loads(read_utf8(receipt))
            item = operation.get("overlays", {}).get(plan["cycle_id"] + "/" + plan["proposal_id"])
            if item and item["revision"] == _revision(encode(plan)):
                return copy.deepcopy(item["plan"])
        return plan

    def _verify_transition(self, operation, *, ignored_receipts=()):
        current = self._v2_sources()
        expected = operation["sources"]
        managed = set(operation["transforms"]) | {
            i["path"] for i in operation["transforms"].values()
        }
        managed.add("PROJECT.md")
        initialization = operation.get("instruction_initialization", {})
        if initialization.get("required"):
            managed.add("INSTRUCTIONS.md")
            rules = self.engine.root / "INSTRUCTIONS.md"
            if rules.exists() and read_utf8(rules) != initialization["content"]:
                raise PCWError("Reviewed instructions changed during migration")
        if {k: v for k, v in current.items() if k not in managed} != {
            k: v for k, v in expected.items() if k not in managed
        }:
            raise PCWError("Source changed during migration; inspect retained backup")
        for old_path, item in operation["transforms"].items():
            old = self.engine.root / old_path
            new = self.engine.root / item["path"]
            self.engine._assert_safe(old)
            self.engine._assert_safe(new)
            old_text = old.read_bytes().decode("utf-8") if old.is_file() else None
            new_text = new.read_bytes().decode("utf-8") if new.is_file() else None
            if old == new:
                valid = old_text in (item["before"], item["text"])
            else:
                valid = (
                    old_text in (None, item["before"])
                    and new_text in (None, item["text"])
                    and (old_text is not None or new_text is not None)
                )
            if not valid:
                raise PCWError(f"Material changed during migration: {old_path}")
        ignored = {"format.json", "workspace-opened.json", *ignored_receipts}
        if {k: v for k, v in self._v2_control().items() if k not in ignored} != {
            k: v for k, v in operation["control_sources"].items() if k not in ignored
        }:
            raise PCWError("Cycle or control state changed during migration")

    def _pending_format_two(self):
        path = self.control.root / "migration-v2.json"
        self.control.safe(path)
        operation = json.loads(read_utf8(path)) if path.exists() else None
        if not operation or operation["status"] == "complete":
            return None
        if operation["status"] == "snapshotting":
            control = {k: v for k, v in self._v2_control().items() if k != "migration-v2.json"}
            if self._migration_tree(self.engine.root) != operation["workspace_snapshot"] or control != operation["control_sources"]:
                raise PCWError("Source changed during format-2 snapshot")
        else:
            self._migration_verify_backup(operation)
            self._verify_transition(operation, ignored_receipts=("migration-v2.json",))
        return operation

    def _resume_format_two(self, operation):
        """Complete recorded v2 transformations before interpreting any filenames.

        The retained receipt supplies identities and approval overlays. Guessing
        IDs from a half-renamed tree would silently change links and approvals.
        """
        receipt = self.control.root / "migration-v2.json"
        if operation["status"] == "snapshotting":
            self._migration_copy(self.engine.root, self._relocation_alias(operation["backup"]), operation["workspace_snapshot"])
            self._migration_copy(self.control.root, self._relocation_alias(operation["control_backup"]), operation["control_sources"])
            self._migration_verify_backup(operation)
            operation["status"] = "applying"
            self.control.write(receipt, encode(operation))
        self._verify_transition(operation, ignored_receipts=("migration-v2.json",))
        from contextopus.core import locking
        self.engine.state.mkdir(parents=True, exist_ok=True)
        with (self.engine.state / "lock").open("a") as lock:
            locking.flock(lock, locking.LOCK_EX)
            for old_path, item in operation["transforms"].items():
                old, new = self.engine.root / old_path, self.engine.root / item["path"]
                self.engine._assert_safe(old)
                self.engine._assert_safe(new)
                if not new.is_file() or read_utf8(new) != item["text"]:
                    self.engine._write(new, item["text"])
                if old != new and old.exists():
                    old.unlink()
                    from contextopus.core.storage import sync_directory
                    sync_directory(old.parent)
            initialization = operation.get("instruction_initialization", {})
            if initialization.get("required") and not (self.engine.root / "INSTRUCTIONS.md").exists():
                self.engine._write(self.engine.root / "INSTRUCTIONS.md", initialization["content"])
        result = self.engine.reconcile()
        if result["pending_count"]:
            return {"status": "index_pending", "recovering_format": 2, "index": result}
        self._verify_transition(operation, ignored_receipts=("migration-v2.json",))
        self.control.write(self._format_path(), encode({"format_version": 2}))
        operation["status"] = "complete"
        self.control.write(receipt, encode(operation))
        return None

    def upgrade_plan(self, instructions_content: str | None = None):
        with self.control.guard():
            version = self._format()
            if version not in (0, 1, 2, 3):
                raise PCWError("Unsupported future workspace format")
            previous = self._migration_receipt_path()
            operation = json.loads(read_utf8(previous)) if previous.exists() else None
            pending = (
                operation if operation and operation["status"] != "complete" else None
            )
            work, blockers = self._migration_work()
            initialization = self._instruction_initialization(instructions_content)
            if initialization.get("blocked"):
                blockers.append(
                    {
                        "reason": initialization["reason"],
                        "required": "instructions_initialization",
                    }
                )
            problems = (
                self._format_problems() if version == FORMAT_VERSION else ["Old workspace format"]
            )
            if version == FORMAT_VERSION and not problems:
                try:
                    with self.engine.read_guard():
                        if self.engine.pending:
                            problems.append(
                                "Shared index does not match current knowledge"
                            )
                except (PCWError, OSError, ValueError) as exc:
                    problems.append(str(exc))
            state = {
                "from_version": version,
                "to_version": FORMAT_VERSION,
                "sources": self._v2_sources(),
                "control_sources": self._v2_control(),
                "instruction_initialization": initialization,
            }
            transforms, aliases = ({}, {})
            predecessor = None
            try:
                if pending:
                    self._verify_transition(pending)
                    self._migration_verify_backup(pending) if pending[
                        "status"
                    ] != "snapshotting" else None
                else:
                    predecessor = self._pending_format_two()
                    if operation is None and not predecessor:
                        self._check_previous_migration()
                    if not predecessor:
                        transforms, aliases = self._v2_transforms(version)
            except (PCWError, OSError, ValueError) as exc:
                blockers.append({"reason": str(exc)})
            return {
                **state,
                "revision": _revision(encode(state)),
                "workspace": str(self.engine.root),
                "compatible": not problems and not pending,
                "ready": not blockers,
                "problems": problems,
                "pending_work": work,
                "blockers": blockers,
                "resume_revision": pending["revision"] if pending else None,
                "recover_format_two_first": predecessor["revision"] if predecessor else None,
                "backup": pending["backup"] if pending else None,
                "changes": []
                if not problems and not pending
                else [
                    "Preserve source/control snapshots",
                    "Migrate YAML IDs, descriptive paths and sources",
                    "Reconcile and verify the shared category index",
                    "Move Current and PROJECT into typed records; record format 3",
                ],
                "renames": [
                    {"id": t["id"], "before": p, "after": t["path"]}
                    for p, t in transforms.items()
                    if p != t["path"]
                ],
                "instructions_preserved": True,
                "pending_work_preserved": True,
                "project_description": self._project_description_status(),
                "next_action": "inspect_blockers"
                if blockers
                else "upgrade_apply"
                if problems or pending
                else "none",
            }

    def upgrade_apply(
        self,
        expected_revision: str,
        user_request: str = "",
        automatic: bool = False,
        instructions_content: str | None = None,
        instructions_confirmation: str | None = None,
    ):
        if not automatic and (
            not isinstance(user_request, str) or not user_request.strip()
        ):
            raise PCWError(
                "Explicit migration request or automatic format-upgrade procedure required"
            )
        with self.control.guard():
            receipt = self._migration_receipt_path()
            operation = json.loads(read_utf8(receipt)) if receipt.exists() else None
            if (
                operation
                and operation["revision"] == expected_revision
                and operation["status"] == "complete"
            ):
                self._require_format()
                return {
                    "status": "complete",
                    "format_version": FORMAT_VERSION,
                    "replayed": True,
                    "backup": operation["backup"],
                    "control_backup": operation["control_backup"],
                    "pending_work_preserved": True,
                    "project_description": self._project_description_status(),
                }
            if operation and operation["status"] != "complete":
                if operation["revision"] != expected_revision:
                    raise PCWError("Resume the pending migration revision")
            else:
                plan = self.upgrade_plan(instructions_content)
                if plan["revision"] != expected_revision:
                    raise PCWError(
                        "Workspace changed since migration review; inspect a fresh plan"
                    )
                if not plan["ready"]:
                    raise PCWError(
                        "Migration preflight blocked: " + encode(plan["blockers"])
                    )
                if plan.get("recover_format_two_first"):
                    recovered = self._resume_format_two(self._pending_format_two())
                    if recovered:
                        return recovered
                    fresh = self.upgrade_plan(instructions_content)
                    return self.upgrade_apply(fresh["revision"], user_request, automatic,
                                              instructions_content, instructions_confirmation)
                if not plan["changes"]:
                    return {
                        "status": "current",
                        "format_version": FORMAT_VERSION,
                        "project_description": plan["project_description"],
                        "pending_work": plan["pending_work"],
                        "blockers": plan["blockers"],
                    }
                initialization = plan["instruction_initialization"]
                if initialization.get("required") and (
                    not isinstance(instructions_confirmation, str)
                    or not instructions_confirmation.strip()
                ):
                    raise PCWError(
                        "Actual human confirmation of the reviewed complete instructions is required, including automatic upgrades"
                    )
                transforms, aliases = self._v2_transforms(plan["from_version"])
                backup = self.control.root / "backups" / uuid.uuid4().hex
                operation = {
                    "revision": expected_revision,
                    "status": "snapshotting",
                    "sources": plan["sources"],
                    "control_sources": plan["control_sources"],
                    "workspace_snapshot": self._migration_tree(self.engine.root),
                    "backup": str(backup / "workspace"),
                    "control_backup": str(backup / "control"),
                    "transforms": transforms,
                    "overlays": self._proposal_overlays(transforms, aliases),
                    "pending_work": plan["pending_work"],
                    "instruction_initialization": initialization,
                    "instructions_confirmation": instructions_confirmation
                    if initialization.get("required")
                    else None,
                }
                self.control.write(receipt, encode(operation))
            if operation["status"] == "snapshotting":
                if (
                    self._migration_tree(self.engine.root)
                    != operation["workspace_snapshot"]
                    or self._v2_control() != operation["control_sources"]
                ):
                    raise PCWError("Source changed during snapshot")
                self._migration_copy(
                    self.engine.root,
                    self._relocation_alias(operation["backup"]),
                    operation["workspace_snapshot"],
                )
                self._migration_copy(
                    self.control.root,
                    self._relocation_alias(operation["control_backup"]),
                    operation["control_sources"],
                )
                self._migration_verify_backup(operation)
                operation["status"] = "applying"
                self.control.write(receipt, encode(operation))
            self._migration_verify_backup(operation)
            self._verify_transition(operation)
            # Use the same root-wide lock as all index writers during the file
            # transition, before exposing the new category in the shared table.
            self.engine._assert_safe(self.engine.state)
            self.engine.state.mkdir(parents=True, exist_ok=True)
            from contextopus.core import locking as fcntl

            with (self.engine.state / "lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                for old_path, item in operation["transforms"].items():
                    old, new = (
                        self.engine.root / old_path,
                        self.engine.root / item["path"],
                    )
                    if (
                        not new.exists()
                        or new.read_bytes().decode("utf-8") != item["text"]
                    ):
                        self.engine._write(new, item["text"])
                    if old != new and old.exists():
                        old.unlink()
                        from contextopus.core.storage import sync_directory

                        sync_directory(old.parent)
                initialization = operation.get("instruction_initialization", {})
                if initialization.get("required"):
                    rules = self.engine.root / "INSTRUCTIONS.md"
                    if not rules.exists():
                        self.engine._write(rules, initialization["content"])
                current = self.engine.root / "current"
                if current.is_dir() and not any(current.iterdir()):
                    current.rmdir()
                fcntl.flock(lock, fcntl.LOCK_UN)
            with self.engine._guard():
                result = self.engine.reconcile()
                if result["pending_count"]:
                    operation["status"] = "index_pending"
                    self.control.write(receipt, encode(operation))
                    return {
                        "status": "index_pending",
                        "resume_revision": expected_revision,
                        "backup": operation["backup"],
                        "index": result,
                    }
            self._verify_transition(operation)
            self.control.write(self._format_path(), encode({"format_version": FORMAT_VERSION}))
            self._require_format()
            if operation.get("instruction_initialization", {}).get("required"):
                self.control.write(
                    self.control.root / "instructions-initialized.json",
                    encode(
                        {"initialized": True, "migration_revision": expected_revision}
                    ),
                )
            history = self._history_record("migration-" + expected_revision)
            operation["status"] = "complete"
            operation["pending_work_preserved"] = True
            self.control.write(receipt, encode(operation))
            return {
                "status": "complete",
                "format_version": FORMAT_VERSION,
                "backup": operation["backup"],
                "control_backup": operation["control_backup"],
                "pending_work_preserved": True,
                "project_description": self._project_description_status(),
                "history": history,
            }

"""Explicit, host-independent PCW cycles over the existing knowledge engine.

Human approval follows workspace policy for knowledge and is always required
for instructions. This module binds application to an
exact prepared revision; it cannot authenticate the origin of a chat message.
Only cycle metadata survives cleanup. Drafts, returns and proposal bodies do not.
"""
from __future__ import annotations

import contextlib
import copy
import difflib
from importlib.resources import files
import json
import os
from pathlib import Path
import shutil
import uuid

import yaml

from .runtime import PCWRuntime, PCWError, _id, _revision, _parse
from .control import RecoveryRequired
from .policies import policies
from .workspaces import WorkspaceMixin
from .documents import DocumentsMixin
from .history import HistoryMixin
from .analytics import AnalyticsMixin
from .audit import AuditMixin


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise PCWError(f"{field} must be nonempty text")
    return value


def _sync_directory(path):
    fd = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _knowledge_approval_required(content):
    """Read only the explicit setting, never infer permission from prose.

    Older/custom instructions without the setting retain manual approval.
    """
    return policies(content)["knowledge_approval_required"]


class CycleRuntime(WorkspaceMixin, DocumentsMixin, HistoryMixin, AnalyticsMixin, AuditMixin):
    """MCP facade. Direct permanent mutations are deliberately not exposed."""

    def __init__(self, work_root, workspace, **kwargs):
        self.engine = PCWRuntime(work_root, workspace, initialize=False, allow_create=False, **kwargs)
        self.control = self.engine.control
        self.record_path = self.control.root / "cycles.json"

    def close(self):
        self.engine.close()

    def _records(self):
        self.control.safe(self.record_path)
        return json.loads(self.record_path.read_text()) if self.record_path.exists() else {"starts": {}, "cycles": {}}

    def _persist(self, records):
        self.control.write(self.record_path, _json(records))

    def _tmp(self, cycle_id):
        path = self.engine.root / "tmp" / _id(cycle_id)
        self.engine._assert_safe(path)
        return path

    def _purge(self, cycle_id):
        path = self._tmp(cycle_id)
        if path.exists():
            # Never follow a link, including a link injected below tmp.
            for entry in path.rglob("*"):
                self.engine._assert_safe(entry)
            shutil.rmtree(path)
            _sync_directory(path.parent)

    def _tmp_revision(self, cycle_id):
        """Bind knowledge review to the temporary work results."""
        materials = {}
        for path in sorted((self._tmp(cycle_id) / "materials").glob("*.md")):
            self.engine._assert_safe(path)
            materials[path.name] = _revision(path.read_bytes().decode("utf-8"))
        return _revision(_json(materials))

    @contextlib.contextmanager
    def _cycle(self, cycle_id, states=("active",)):
        _id(cycle_id)
        self.control.safe(self.record_path)
        if not self.record_path.exists():
            raise PCWError("No PCW cycle. Only an explicit user invocation authorizes pcw_startup.")
        with self.control.guard():
            records = self._records()
            cycle = records["cycles"].get(cycle_id)
            if cycle is None or cycle["state"] not in states:
                raise PCWError("Unknown or inactive cycle; do not reuse authorization from an earlier cycle")
            yield records, cycle

    def _instructions(self, initialize=False):
        path = self.engine.root / "INSTRUCTIONS.md"
        self.engine._assert_safe(path)
        marker = self.control.root / "instructions-initialized.json"
        self.control.safe(marker)
        if not path.exists():
            if not initialize or marker.exists():
                raise PCWError("INSTRUCTIONS.md is missing; restore the user's instructions, do not reset them to defaults")
            content = files("pcw_runtime").joinpath("default_instructions.md").read_text(encoding="utf-8")
            self.engine._write(path, content)
        content = path.read_bytes().decode("utf-8")
        if initialize and not marker.exists():
            self.control.write(marker, _json({"initialized": True}))
        return {"path": "INSTRUCTIONS.md", "content": content, "revision": _revision(content)}

    def _require_work(self, cycle):
        if cycle.get("purpose", "work") not in {"work", "rework"}:
            raise PCWError("This cycle is only for instructions; start a work cycle for knowledge operations")
        if cycle.get("invocation") == "implicit" and not policies(self._instructions()["content"])["allow_implicit_updates"]:
            raise PCWError("Implicit updates are disabled by current instructions")

    def startup(self, request_id: str, purpose: str = "work", restart_cycle_id: str | None = None,
                invocation: str = "explicit", task_id: str | None = None):
        """One fresh request_id per human invocation; retries reuse that ID."""
        _id(request_id)
        self._require_format(storage=False)
        if purpose not in {"work", "instructions", "audit", "rework"}:
            raise PCWError("purpose must be work, instructions, audit or rework")
        if invocation not in {"explicit", "implicit"}:
            raise PCWError("invocation must be explicit or implicit")
        if invocation == "implicit" and (purpose != "work" or not policies(self._instructions()["content"])["allow_implicit_updates"]):
            raise PCWError("This procedure requires an explicit user invocation")
        if task_id is not None:
            if purpose not in {"work", "rework"}:
                raise PCWError("Only work and rework cycles bind a task")
            self.current_read(task_id)
        signature = _revision(_json([purpose, restart_cycle_id, invocation, task_id]))
        with self.control.guard():
            records = self._records()
            cycle_id = records["starts"].get(request_id)
            if cycle_id:
                cycle = records["cycles"][cycle_id]
                if cycle["start_signature"] != signature:
                    raise PCWError("request_id already identifies a different invocation")
                if cycle["state"] != "starting":
                    return {"cycle_id": cycle_id, "status": cycle["state"], "replayed": True,
                            "tmp_cleared": False, "purpose": cycle.get("purpose", "work"),
                            **({"instructions": self._instructions()} if cycle["state"] == "active" else {})}
            else:
                if restart_cycle_id is not None:
                    old = records["cycles"].get(_id(restart_cycle_id))
                    if old is None or old["state"] not in {"active", "closing", "cancelled", "closed"}:
                        raise PCWError("restart_cycle_id must identify the explicitly restarted work")
                    old["state"] = "restarting"
                cycle_id = uuid.uuid4().hex
                cycle = {"state": "starting", "start_signature": signature, "proposals": {},
                         "restart_cycle_id": restart_cycle_id, "purpose": purpose,
                         "invocation": invocation, "task_id": task_id}
                records["starts"][request_id] = cycle_id
                records["cycles"][cycle_id] = cycle
                self._persist(records)
            try:
                self.engine._ensure_storage()
            except RecoveryRequired as exc:
                return {**exc.details, "cycle_id": cycle_id}
            with self.engine.read_guard() if purpose == "audit" else self.engine._guard():
                instructions = self._instructions()
                if restart_cycle_id is not None:
                    self._purge(restart_cycle_id)
                    records["cycles"][restart_cycle_id] = {"state": "replaced", "proposals": {},
                        "start_signature": records["cycles"][restart_cycle_id]["start_signature"]}
                self._purge(cycle_id)
                self._tmp(cycle_id).mkdir(parents=True, exist_ok=True)
                cycle["state"] = "active"
                self._persist(records)
                status = self.engine.status()
                status.pop("active")
                return {"cycle_id": cycle_id, "status": "active", "tmp_cleared": True,
                        "purpose": purpose, "task_id": task_id, "instructions": instructions,
                        "project": self.project_read(), **status}

    def _call(self, cycle_id, method, **kwargs):
        with self._cycle(cycle_id) as (_, cycle):
            self._require_work(cycle)
            return getattr(self.engine, method)(**kwargs)

    def status(self, cycle_id: str):
        with self._cycle(cycle_id) as (_, cycle):
            outstanding = [{"id": key, **value} for key, value in cycle["proposals"].items()
                           if value["state"] not in {"applied", "discarded", "no_changes"}]
            return {"cycle_id": cycle_id, "cycle_status": cycle["state"],
                    "proposals": outstanding[:50], "outstanding_proposal_count": len(outstanding),
                    **self.engine.status()}

    def _read_call(self, cycle_id, method, **kwargs):
        self._require_format()
        with self._cycle(cycle_id) if cycle_id else contextlib.nullcontext():
            with self.engine.read_guard():
                return getattr(self.engine, method)(**kwargs)

    def list(self, cycle_id: str | None = None, offset: int = 0, limit: int = 50):
        return self._read_call(cycle_id, "list", offset=offset, limit=limit)

    def read(self, cycle_id: str | None = None, material_id: str = "", from_id: str | None = None):
        self._require_format()
        with self.engine.read_guard():
            if from_id is not None and material_id not in self.engine._material(from_id).links:
                raise PCWError("from_id must have an existing link to the requested material")
            return self._read_call(cycle_id, "read", material_id=material_id)

    def read_many(self, cycle_id: str | None = None, material_ids: list[str] | None = None):
        return self._read_call(cycle_id, "read_many", material_ids=material_ids)

    def search(self, cycle_id: str | None = None, query: str = "", N: int | None = None,
               d_max: float | None = None, min_jump: float | None = None, multiplier: float | None = None):
        return self._read_call(cycle_id, "search", query=query, N=N, d_max=d_max,
                          min_jump=min_jump, multiplier=multiplier)

    def instructions_read(self, cycle_id: str | None = None):
        self._require_format()
        with self._cycle(cycle_id) if cycle_id else self.control.guard():
            return self._instructions()

    def tmp_write(self, cycle_id: str, content: str, material_id: str | None = None,
                  expected_revision: str | None = None):
        with self._cycle(cycle_id) as (_, cycle):
            self._require_work(cycle)
            if not isinstance(content, str):
                raise PCWError("content must be ordinary Markdown text")
            ident = _id(material_id) if material_id else uuid.uuid4().hex + ".md"
            if not ident.endswith(".md"):
                raise PCWError("Temporary material IDs end with .md")
            path = self._tmp(cycle_id) / "materials" / ident
            self.engine._assert_safe(path)
            if material_id is not None:
                if not path.is_file() or expected_revision != _revision(path.read_bytes().decode("utf-8")):
                    raise PCWError("Temporary material changed or is missing; read its current revision")
            self.engine._write(path, content)
            if path.read_bytes().decode("utf-8") != content:
                raise PCWError("Temporary write verification failed")
            return {"id": ident, "path": path.relative_to(self.engine.root).as_posix(),
                    "revision": _revision(content), "status": "temporary"}

    def tmp_read(self, cycle_id: str, material_id: str):
        with self._cycle(cycle_id):
            path = self._tmp(cycle_id) / "materials" / _id(material_id)
            self.engine._assert_safe(path)
            content = path.read_bytes().decode("utf-8")
            return {"id": material_id, "content": content, "revision": _revision(content), "status": "temporary"}

    def tmp_list(self, cycle_id: str, offset: int = 0, limit: int = 50):
        with self._cycle(cycle_id):
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
                raise PCWError("Use a nonnegative offset and limit between 1 and 100")
            paths = sorted((self._tmp(cycle_id) / "materials").glob("*.md"))
            items = []
            for path in paths[offset:offset + limit]:
                self.engine._assert_safe(path)
                items.append({"id": path.name, "revision": _revision(path.read_bytes().decode("utf-8"))})
            return {"materials": items, "total": len(paths), "status": "temporary"}

    def _snapshot(self, material):
        path = self.engine.root / material.path
        self.engine._assert_safe(path)
        text = path.read_bytes().decode("utf-8")
        return {"path": material.path, "text": text, "fingerprint": _revision(text)}

    def _plan_path(self, cycle_id, proposal_id):
        path = self._tmp(cycle_id) / "proposals" / (_id(proposal_id) + ".json")
        self.engine._assert_safe(path)
        return path

    def _load_plan(self, cycle_id, proposal_id, entry):
        plan = json.loads(self._plan_path(cycle_id, proposal_id).read_text())
        if _revision(_json(plan)) != entry["revision"]:
            raise PCWError("Prepared proposal was changed; prepare and present it again")
        review = self._plan_path(cycle_id, proposal_id).with_suffix(".md")
        self.engine._assert_safe(review)
        if review.read_text() != self._review(plan):
            raise PCWError("Prepared review was changed; prepare and present it again")
        return plan

    def _proposal_id(self, cycle_id, cycle, proposal_id, kind):
        if proposal_id is None:
            return uuid.uuid4().hex
        previous = cycle["proposals"].get(_id(proposal_id))
        if previous is None or previous["state"] not in {"prepared", "discarded", "no_changes"}:
            raise PCWError("Only an unapplied proposal may be replaced")
        plan = self._load_plan(cycle_id, proposal_id, previous)
        if plan.get("kind", "knowledge") != kind:
            raise PCWError("Cannot change a proposal's kind")
        return proposal_id

    def _save_plan(self, records, cycle, plan, state):
        revision = _revision(_json(plan))
        review = self._review(plan)
        path = self._plan_path(plan["cycle_id"], plan["proposal_id"])
        self.engine._write(path, _json(plan))
        self.engine._write(path.with_suffix(".md"), review)
        if json.loads(path.read_text()) != plan or path.with_suffix(".md").read_text() != review:
            raise PCWError("Proposal write verification failed")
        cycle["proposals"][plan["proposal_id"]] = {"revision": revision, "state": state}
        self._persist(records)
        effects = self._effects(plan)
        return {"proposal_id": plan["proposal_id"], "revision": revision, "status": state,
                "kind": plan.get("kind", "knowledge"), "created_ids": plan["created_ids"],
                "review_path": path.with_suffix(".md").relative_to(self.engine.root).as_posix(),
                "effects": effects[:50], "effects_count": len(effects),
                "review_changes": self._review_changes(plan),
                **({"no_changes_reason": plan["no_changes_reason"]} if state == "no_changes" else {}),
                **self._review_policy(plan, state)}

    @staticmethod
    def _review_policy(plan, state):
        required = plan.get("kind") == "instructions" or plan.get("knowledge_approval_required", True)
        return {"approval_required": required,
                "next_action": "report_no_changes" if state == "no_changes" else
                    "present_changes_in_chat_for_approval" if required else "present_changes_in_chat_then_apply"}

    def instructions_prepare(self, cycle_id: str, content: str, expected_revision: str,
                             user_request: str, proposal_id: str | None = None):
        """Only a direct user request starts an instructions edit; preparation is temporary."""
        _text(user_request, "user's direct request to change instructions")
        if not isinstance(content, str):
            raise PCWError("content must be ordinary Markdown text")
        _knowledge_approval_required(content)
        with self._cycle(cycle_id) as (records, cycle):
            if cycle.get("purpose") == "audit":
                raise PCWError("Audit cannot change instructions")
            current = self._instructions()
            if current["revision"] != expected_revision:
                raise PCWError("Instructions changed since they were read; read them again")
            ident = self._proposal_id(cycle_id, cycle, proposal_id, "instructions")
            before = {"path": current["path"], "text": current["content"], "fingerprint": current["revision"]}
            after = {"path": current["path"], "text": content, "fingerprint": _revision(content)}
            plan = {"cycle_id": cycle_id, "proposal_id": ident, "kind": "instructions",
                    "user_request": user_request, "created_ids": {},
                    "entries": {"INSTRUCTIONS.md": {"before": before, "after": after}}}
            state = "prepared"
            if content == current["content"]:
                state = "no_changes"
                plan["no_changes_reason"] = "The proposed instructions match the existing file."
            return self._save_plan(records, cycle, plan, state)

    def instructions_apply(self, cycle_id: str, proposal_id: str, expected_revision: str, confirmation: str):
        _text(confirmation, "current user's explicit confirmation")
        with self._cycle(cycle_id) as (records, cycle):
            if cycle.get("purpose") == "audit":
                raise PCWError("Audit cannot apply instructions")
            entry = cycle["proposals"].get(_id(proposal_id))
            if entry is None or entry["revision"] != expected_revision or entry["state"] in {"discarded", "no_changes"}:
                raise PCWError("Apply only the exact presented and confirmed proposal revision")
            plan = self._load_plan(cycle_id, proposal_id, entry)
            if plan.get("kind") != "instructions":
                raise PCWError("Use proposal_apply for knowledge changes")
            if entry["state"] == "applied":
                return {"proposal_id": proposal_id, "status": "applied", "replayed": True}
            change = plan["entries"]["INSTRUCTIONS.md"]
            retry = entry["state"] != "prepared"
            if not (retry and self._matches(change["after"])) and not self._matches(change["before"]):
                raise PCWError("Instructions conflict: read, prepare and approve again")
            entry["state"] = "applying"
            self._persist(records)
            try:
                self.engine._write(self.engine.root / "INSTRUCTIONS.md", change["after"]["text"])
                if not self._matches(change["after"]):
                    raise PCWError("Instructions write verification failed")
                history = self._history_record(proposal_id, force=policies(change["before"]["text"])["git_history_enabled"])
                entry["state"] = "applied"
                self._persist(records)
                return {"proposal_id": proposal_id, "revision": expected_revision, "status": "applied",
                        "path": "INSTRUCTIONS.md", "instructions_revision": change["after"]["fingerprint"],
                        "tmp_preserved": True, "history": history}
            except Exception as exc:
                entry["state"] = "partial"
                self._persist(records)
                return {"proposal_id": proposal_id, "status": "partial", "error": str(exc),
                        "tmp_preserved": True, "next_action": "instructions_apply"}

    def proposal_prepare(self, cycle_id: str, changes: list[dict],
                         replacements: dict[str, str] | None = None, proposal_id: str | None = None,
                         no_changes_reason: str | None = None):
        """Prepare a complete, reviewed set without changing permanent files.

        Creates use key/content/links; @key addresses a new material in this set.
        Existing entries use material_id/expected_revision plus content, links,
        path (relative to knowledge) or delete:true. A replacement redirects all
        incoming links and requires the old entry to be explicitly deleted.
        """
        with self._cycle(cycle_id) as (records, cycle), self.engine._guard():
            self._require_work(cycle)
            instructions = self._instructions()
            approval_required = _knowledge_approval_required(instructions["content"])
            if not isinstance(changes, list) or len(changes) > 100:
                raise PCWError("changes must contain 0 to 100 final material changes")
            if not changes:
                _text(no_changes_reason, "no_changes_reason after comparing results with permanent knowledge")
            elif no_changes_reason is not None:
                raise PCWError("no_changes_reason is only valid for an empty changes list")
            ident = self._proposal_id(cycle_id, cycle, proposal_id, "knowledge")
            aliases, entries, touched = {}, {}, set()
            for change in changes:
                if not isinstance(change, dict) or set(change) - {"key", "material_id", "expected_revision", "content", "description", "links", "path", "delete"}:
                    raise PCWError("Unknown change fields")
                existing = change.get("material_id")
                if existing is not None:
                    if "key" in change:
                        raise PCWError("Use material_id or a new key, not both")
                    material = self.engine._material(existing)
                    if change.get("expected_revision") != material.revision:
                        raise PCWError("Material changed since it was read; read it again")
                    before = self._snapshot(material)
                    metadata, content, path = copy.deepcopy(material.metadata), material.content, material.path
                    target_id = material.id
                else:
                    key = _id(_text(change.get("key"), "key"))
                    if key in aliases or change.get("delete") or "expected_revision" in change or "path" in change:
                        raise PCWError("Invalid or duplicate new-material key")
                    target_id = self.engine._allocate_material_id()
                    aliases[key] = target_id
                    before, metadata, content, path = None, {"links": []}, None, "knowledge/" + target_id
                if target_id in touched:
                    raise PCWError("One final change per material is required")
                touched.add(target_id)
                if "delete" in change and type(change["delete"]) is not bool:
                    raise PCWError("delete must be a boolean")
                if change.get("delete"):
                    if set(change) - {"material_id", "expected_revision", "delete"}:
                        raise PCWError("Deletion cannot include a new body, links or path")
                    entries[target_id] = {"before": before, "after": None}
                    continue
                if "content" in change:
                    content = change["content"]
                if not isinstance(content, str):
                    raise PCWError("Supply ordinary Markdown content for a new material")
                if "links" in change:
                    metadata["links"] = change["links"]
                if "description" in change:
                    if not isinstance(change["description"], str):
                        raise PCWError("description must be text")
                    metadata["description"] = change["description"]
                if "path" in change:
                    destination = self.engine._knowledge_path(change["path"])
                    if destination.name != target_id:
                        raise PCWError("Move must preserve the filename ID")
                    path = destination.relative_to(self.engine.root).as_posix()
                    if path != before["path"] and destination.exists():
                        raise PCWError("Move destination already exists")
                entries[target_id] = {"before": before, "after": {"path": path, "content": content, "metadata": metadata}}

            limit = policies(instructions["content"])["material_max_tokens"]
            if limit is not None:
                exceeded = []
                for target_id, entry in entries.items():
                    if entry["after"] is not None:
                        count = self.engine._get_chunker().count(entry["after"]["content"])
                        if count > limit:
                            exceeded.append({"id": target_id, "key": next((key for key, value in aliases.items() if value == target_id), None),
                                             "tokens": count, "limit": limit})
                if exceeded:
                    return {"status": "needs_split", "materials": exceeded, "next_action": "revise_semantic_materials",
                            "knowledge_changed": False}

            def resolve(value):
                if not isinstance(value, str):
                    raise PCWError("Links must be exact IDs or @keys")
                if value.startswith("@"):
                    if value[1:] not in aliases:
                        raise PCWError("Unknown new-material link key")
                    return aliases[value[1:]]
                return _id(value)

            if replacements is not None and not isinstance(replacements, dict):
                raise PCWError("replacements must map deleted IDs to surviving IDs or @keys")
            mapping = {_id(k): resolve(v) for k, v in (replacements or {}).items()}
            deleted = {key for key, entry in entries.items() if entry["after"] is None}
            survivors = (set(self.engine.materials) | set(entries)) - deleted
            if any(old not in deleted or new not in survivors for old, new in mapping.items()):
                raise PCWError("Replacement source must be deleted and its target must survive")
            # Mechanical incoming-link consequences are part of the same review.
            for material in self.engine.materials.values():
                if material.id not in entries and any(link in deleted for link in material.links):
                    entries[material.id] = {"before": self._snapshot(material), "after": {
                        "path": material.path, "content": material.content, "metadata": copy.deepcopy(material.metadata)}}
            for key, entry in entries.items():
                after = entry["after"]
                if after is None:
                    continue
                raw = after["metadata"].get("links", [])
                if not isinstance(raw, list):
                    raise PCWError("links must be a list")
                links = [resolve(value) for value in raw]
                links = [mapping.get(link, link) for link in links if link not in deleted or link in mapping]
                if any(link not in survivors for link in links):
                    raise PCWError("Unknown link target")
                after["metadata"]["links"] = list(dict.fromkeys(link for link in links if link != key))
                after["text"] = "---\n" + yaml.safe_dump(after["metadata"], sort_keys=False, allow_unicode=True) + "---\n" + after.pop("content")
                after.pop("metadata")
                after["fingerprint"] = _revision(after["text"])
            plan = {"cycle_id": cycle_id, "proposal_id": ident, "created_ids": aliases, "entries": entries,
                    "tmp_revision": self._tmp_revision(cycle_id),
                    "instructions_revision": instructions["revision"],
                    "knowledge_approval_required": approval_required}
            if not changes:
                plan["no_changes_reason"] = no_changes_reason
            state = "prepared" if changes else "no_changes"
            return self._save_plan(records, cycle, plan, state)

    @staticmethod
    def _effects(plan):
        result = []
        for ident, entry in sorted(plan["entries"].items()):
            before, after = entry["before"], entry["after"]
            instructions = plan.get("kind") in {"instructions", "project"}
            old_links = _parse(before["text"])[0].get("links", []) if before and not instructions else []
            new_links = _parse(after["text"])[0].get("links", []) if after and not instructions else []
            result.append({"id": ident, "action": "delete" if after is None else "create" if before is None else "update",
                           "old_path": before["path"] if before else None, "path": after["path"] if after else None,
                           "links_added": [x for x in new_links if x not in old_links],
                           "links_removed": [x for x in old_links if x not in new_links]})
        return result

    def _review_changes(self, plan):
        """Exact changed passages for chat presentation; never a generated summary.

        Keep the on-disk review format stable so pending 0.9.0 proposals remain
        verifiable. Labels are supplied by the agent in the conversation language.
        """
        def body(snapshot):
            return snapshot["text"] if plan.get("kind") in {"instructions", "project"} else _parse(snapshot["text"])[1]

        def describe(ident, snapshot=None, previous=False):
            if snapshot is None:
                entry = plan["entries"].get(ident, {})
                snapshot = entry.get("before" if previous else "after") or entry.get("before")
            if snapshot:
                text, path = body(snapshot), snapshot["path"]
            else:
                material = self.engine.materials.get(ident)
                text, path = (material.content, material.path) if material else ("", "knowledge/" + ident)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            title = next((line[2:].strip() for line in lines if line.startswith("# ")),
                         lines[0] if lines else ident)
            return {"id": ident, "title": title, "path": path}

        changes = []
        for effect in self._effects(plan):
            ident = effect["id"]
            before, after = (plan["entries"][ident][key] for key in ("before", "after"))
            old = body(before).splitlines(keepends=True) if before else []
            new = body(after).splitlines(keepends=True) if after else []
            passages = []
            for tag, i, j, k, end in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
                if tag != "equal":
                    passages.append({"before": "".join(old[i:j]), "after": "".join(new[k:end]),
                                     "before_start_line": i + 1, "after_start_line": k + 1,
                                     "context_before": "".join(old[max(0, i - 3):i]),
                                     "context_after": "".join(old[j:j + 3])})
            changes.append({**effect, "title": describe(ident, after or before)["title"],
                            "old_title": describe(ident, before)["title"] if before else None,
                            "body_changes": passages,
                            "links_added": [describe(link) for link in effect["links_added"]],
                            "links_removed": [describe(link, previous=True) for link in effect["links_removed"]]})
            if plan.get("kind", "knowledge") == "knowledge":
                old_description = _parse(before["text"])[0].get("description", "") if before else ""
                new_description = _parse(after["text"])[0].get("description", "") if after else ""
                if old_description != new_description:
                    changes[-1]["description_change"] = {"before": old_description, "after": new_description}
        return changes

    @staticmethod
    def _review(plan):
        heading = "# Proposed instructions changes\n" if plan.get("kind") == "instructions" else "# Proposed permanent-memory changes\n"
        parts = [heading, "Temporary context remains until this cycle is explicitly closed.\n"]
        if "no_changes_reason" in plan:
            parts.append("\nNo permanent changes after result review:\n" + plan["no_changes_reason"] + "\n")
        for ident, entry in sorted(plan["entries"].items()):
            before, after = entry["before"], entry["after"]
            parts.append(f"\n## {ident}\n")
            parts.append(f"Path: {before['path'] if before else '/dev/null'} -> {after['path'] if after else '/dev/null'}\n")
            diff = "\n".join(difflib.unified_diff(
                before["text"].splitlines() if before else [],
                after["text"].splitlines() if after else [],
                fromfile=before["path"] if before else "/dev/null",
                tofile=after["path"] if after else "/dev/null", lineterm=""))
            parts.append(diff or "No content change.\n")
        return "\n".join(parts)

    def proposal_read(self, cycle_id: str, proposal_id: str):
        with self._cycle(cycle_id) as (_, cycle), self.engine.read_guard():
            entry = cycle["proposals"].get(_id(proposal_id))
            if entry is None:
                raise PCWError("Unknown proposal")
            plan = self._load_plan(cycle_id, proposal_id, entry)
            return {"proposal_id": proposal_id, **entry, "review": self._review(plan),
                    "review_changes": self._review_changes(plan),
                    **self._review_policy(plan, entry["state"]),
                    **({"no_changes_reason": plan["no_changes_reason"]} if "no_changes_reason" in plan else {})}

    def proposal_discard(self, cycle_id: str, proposal_id: str, expected_revision: str):
        with self._cycle(cycle_id) as (records, cycle):
            entry = cycle["proposals"].get(_id(proposal_id))
            if entry is None or entry["revision"] != expected_revision or entry["state"] not in {"prepared", "discarded"}:
                raise PCWError("Only the exact unapplied proposal may be discarded")
            entry["state"] = "discarded"
            self._persist(records)
            return {"proposal_id": proposal_id, "status": "discarded"}

    def _matches(self, snapshot):
        path = self.engine.root / snapshot["path"]
        self.engine._assert_safe(path)
        return path.is_file() and _revision(path.read_bytes().decode("utf-8")) == snapshot["fingerprint"]

    def _preflight(self, plan, retry):
        for ident, entry in plan["entries"].items():
            before, after = entry["before"], entry["after"]
            material = self.engine.materials.get(ident)
            if retry and after is None and material is None:
                continue
            if retry and after is not None and self._matches(after) and (before is None or before["path"] == after["path"] or not (self.engine.root / before["path"]).exists()):
                continue
            if before is None:
                if material is not None or (self.engine.root / after["path"]).exists():
                    raise PCWError("Proposal conflict: new material already exists")
            elif not self._matches(before):
                moved = {**before, "path": after["path"]} if after is not None else None
                if not (retry and moved and not (self.engine.root / before["path"]).exists() and self._matches(moved)):
                    raise PCWError("Proposal conflict: material or navigation changed; prepare and present again")
            if after and before and after["path"] != before["path"]:
                destination = self.engine.root / after["path"]
                if destination.exists() and not (retry and self._matches({**before, "path": after["path"]})):
                    raise PCWError("Proposal conflict: move destination exists")

    def proposal_apply(self, cycle_id: str, proposal_id: str, expected_revision: str,
                       confirmation: str | None = None):
        with self._cycle(cycle_id) as (records, cycle), self.engine._guard():
            self._require_work(cycle)
            entry = cycle["proposals"].get(_id(proposal_id))
            if entry is None or entry["revision"] != expected_revision or entry["state"] in {"discarded", "no_changes"}:
                raise PCWError("Apply only the exact presented proposal revision")
            plan = self._load_plan(cycle_id, proposal_id, entry)
            if plan.get("kind") in {"instructions", "project"}:
                raise PCWError("Use instructions_apply or project_apply for document changes")
            if entry["state"] == "applied":
                return {"proposal_id": proposal_id, "revision": expected_revision, "status": "applied", "replayed": True}
            # Finish an already-started authorized write before reviewing it under
            # new rules; otherwise a mid-recovery edit could strand partial data.
            if entry["state"] == "prepared" and plan.get("instructions_revision") != self._instructions()["revision"]:
                raise PCWError("Instructions changed; read them and prepare the knowledge proposal again")
            if plan.get("knowledge_approval_required", True):
                _text(confirmation, "current user's explicit confirmation")
            self._preflight(plan, entry["state"] != "prepared")
            entry["state"] = "applying"
            self._persist(records)
            try:
                # Write survivors and redirect incoming links before any deletion.
                for ident, change in plan["entries"].items():
                    before, after = change["before"], change["after"]
                    if after is None or self._matches(after):
                        continue
                    if before is None or _parse(before["text"])[1] != _parse(after["text"])[1]:
                        self.engine._delete_rows(ident)
                    target = self.engine.root / after["path"]
                    if before and before["path"] != after["path"]:
                        old = self.engine.root / before["path"]
                        if old.exists():
                            target.parent.mkdir(parents=True, exist_ok=True)
                            os.rename(old, target)
                            _sync_directory(old.parent)
                            _sync_directory(target.parent)
                    self.engine._write(target, after["text"])
                    if not self._matches(after):
                        raise PCWError("Applied text verification failed")
                for ident, change in plan["entries"].items():
                    if change["after"] is None:
                        self.engine._delete_rows(ident)
                        target = self.engine.root / change["before"]["path"]
                        target.unlink(missing_ok=True)
                        _sync_directory(target.parent)
                self.engine._scan()
                self.engine._reconcile()
                materials = [self.engine._index_receipt(self.engine._material(ident))
                             for ident, change in plan["entries"].items() if change["after"] is not None]
                history = self._history_record(proposal_id)
                entry["state"] = "index_pending" if any(m["index_status"] != "indexed" for m in materials) else "applied"
                self._persist(records)
                return {"proposal_id": proposal_id, "revision": expected_revision, "status": entry["state"],
                        "materials": materials, "tmp_preserved": True, "history": history}
            except Exception as exc:
                entry["state"] = "partial"
                self._persist(records)
                return {"proposal_id": proposal_id, "status": "partial", "error": str(exc),
                        "tmp_preserved": True, "next_action": "proposal_apply"}

    def finish(self, cycle_id: str, cancel: bool = False):
        if type(cancel) is not bool:
            raise PCWError("cancel must be a boolean")
        with self._cycle(cycle_id, ("starting", "active", "closing", "closed", "cancelled")) as (records, cycle):
            if cycle["state"] in {"closed", "cancelled"}:
                return {"cycle_id": cycle_id, "status": cycle["state"], "replayed": True}
            if cycle["state"] == "starting" and not cancel:
                return {"status": "blocked", "reason": "Startup is incomplete; retry it or explicitly cancel"}
            if cycle["state"] in {"starting", "active"}:
                unfinished = [key for key, entry in cycle["proposals"].items()
                              if entry["state"] not in {"applied", "discarded", "no_changes"}]
                if unfinished and not cancel:
                    return {"status": "blocked", "unfinished_proposals": unfinished,
                            "reason": "Apply or discard proposals before closing; tmp is preserved"}
                if not cancel and cycle.get("purpose") != "audit":
                    temporary_revision = self._tmp_revision(cycle_id)
                    plans = [self._load_plan(cycle_id, key, entry) for key, entry in cycle["proposals"].items()]
                    instructions_only = cycle.get("purpose") == "instructions"
                    instructions_revision = self._instructions()["revision"]
                    reviewed = any(plan.get("kind") == "instructions" if instructions_only else
                                   plan.get("kind", "knowledge") == "knowledge" and plan.get("tmp_revision") == temporary_revision
                                   and plan.get("instructions_revision") == instructions_revision
                                   for plan in plans)
                    if not reviewed:
                        if instructions_only:
                            return {"status": "blocked", "tmp_preserved": True,
                                    "reason": "Complete the requested instructions review before closing",
                                    "next_action": "instructions_prepare"}
                        return {"status": "blocked", "tmp_preserved": True,
                                "reason": "Current results have not completed memory review. Search by the conclusion, "
                                          "read relevant knowledge and prepare the changes; if none are needed, "
                                          "prepare changes=[] with no_changes_reason. No closure permission is needed.",
                                "next_action": "proposal_prepare"}
                cycle["cancelled_operations"] = unfinished if cancel else []
                cycle["closing_as"] = "cancelled" if cancel else "closed"
                cycle["state"] = "closing"
                self._persist(records)
            previous_id = cycle.get("restart_cycle_id")
            if previous_id and records["cycles"][previous_id]["state"] == "restarting":
                self._purge(previous_id)
                previous = records["cycles"][previous_id]
                previous["state"], previous["proposals"] = "replaced", {}
            self._purge(cycle_id)
            cycle["state"] = cycle.pop("closing_as")
            cycle["proposals"] = {}  # no approval or draft body is carried forward
            self._persist(records)
            return {"cycle_id": cycle_id, "status": cycle["state"], "tmp_cleared": True,
                    "cancelled_operations": cycle.get("cancelled_operations", [])}

    def reconcile(self, cycle_id: str):
        return self._call(cycle_id, "reconcile")

    def switch_embeddings(self, cycle_id: str, config: dict, search: dict, chunking: dict | None = None):
        return self._call(cycle_id, "switch_embeddings", config=config, search=search, chunking=chunking)

    def checkpoint(self, cycle_id: str, paths: list[str], message: str):
        if not paths or any(not path.startswith("knowledge/") for path in paths):
            raise PCWError("Only exact permanent knowledge paths may enter memory Git history")
        return self._call(cycle_id, "checkpoint", paths=paths, message=message)

    def recover_workspace(self, cycle_id: str):
        with self._cycle(cycle_id, ("active", "starting")):
            return self.engine.recover_workspace(recreate_missing_knowledge=False)

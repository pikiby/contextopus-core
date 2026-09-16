"""Explicit task/assignment receipts and observable completion conditions."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import uuid

from .control import RecoveryRequired


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class TaskLedger:
    def __init__(self, runtime):
        self.runtime = runtime
        self.control = runtime.control
        self.path = self.control.root / "task-ledger.json"

    def load(self):
        self.control.safe(self.path)
        return json.loads(self.path.read_text()) if self.path.exists() else {"active": None, "tasks": {}}

    def store(self, data):
        self.control.write(self.path, json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n")

    def active(self, data):
        task = data["tasks"].get(data.get("active"))
        if task is None:
            raise ValueError("Open the user request with pcw_task_begin before assigning work")
        return task

    def entry(self, data, assignment_id):
        task = self.active(data)
        if assignment_id not in task["assignments"]:
            raise ValueError("Assignment is not registered for the active task")
        return task, task["assignments"][assignment_id]

    def begin(self, goal: str, constraints: str, completion: str,
              checkpoint_policy: str = "required", checkpoint_reason: str = ""):
        if not all(isinstance(v, str) and v.strip() for v in (goal, completion)) or not isinstance(constraints, str):
            raise ValueError("Task goal and completion must be non-empty; constraints must be text")
        if checkpoint_policy not in {"required", "forbidden"}:
            raise ValueError("checkpoint_policy must be required or forbidden")
        if checkpoint_policy == "forbidden" and not checkpoint_reason.strip():
            raise ValueError("Record the user's actual checkpoint prohibition")
        with self.control.guard():
            data = self.load()
            request = dict(goal=goal, constraints=constraints, completion=completion,
                           checkpoint_policy=checkpoint_policy, checkpoint_reason=checkpoint_reason)
            previous = data["tasks"].get(data.get("active"))
            if previous and previous["status"] != "complete":
                if previous["request"] == request:
                    return self.status()
                raise ValueError("An unfinished task exists; resume it before opening another request")
            try:
                baseline = self.runtime.durable_state()["files"]
                recovery = None
            except Exception as exc:
                baseline = {}
                recovery = (exc.details if isinstance(exc, RecoveryRequired) else
                            {"status": "memory_unavailable", "reason": str(exc), "next_action": "prepare_assignment"})
            task_id = uuid.uuid4().hex
            data["active"] = task_id
            data["tasks"][task_id] = {"id": task_id, "request": request, "status": "active",
                                      "started_at": now(), "baseline": baseline, "assignments": {}, "owned_paths": [],
                                      "recovery_at_start": recovery}
            self.store(data)
            return self.status()

    def status(self):
        with self.control.guard():
            data = self.load()
            task = data["tasks"].get(data.get("active"))
            return {"task": task, "status": "absent" if task is None else task["status"]}

    def register(self, assignment, environment_revision, continuation_of=None):
        data = self.load()
        task = self.active(data)
        prior = None
        if continuation_of:
            _, prior = self.entry(data, continuation_of)
            if not prior.get("executor_session_id") or not prior.get("processed_at"):
                raise ValueError("Read and process the previous executor return before a continuation")
        key = digest([assignment, environment_revision, continuation_of])
        for entry in task["assignments"].values():
            if entry["key"] == key:
                return self.handoff(entry)
        ident = uuid.uuid4().hex
        entry = {"id": ident, "key": key, "assignment": assignment,
                 "environment_revision": environment_revision, "prepared_at": now(),
                 "return_id": prior["return_id"] if prior else self.runtime._allocate_material_id(),
                 "executor_session_id": prior["executor_session_id"] if prior else None,
                 "continuation_of": continuation_of, "status": "prepared"}
        task["assignments"][ident] = entry
        task["status"] = "active"
        self.store(data)
        return self.handoff(entry)

    def handoff(self, entry):
        return {"assignment_id": entry["id"], "return_id": entry["return_id"],
                "assignment": entry["assignment"], "assignment_revision": digest(entry["assignment"]),
                "executor_session_id": entry["executor_session_id"],
                "launch_message": (
                    "Execute this complete registered PCW assignment. First obtain your own native executor "
                    "session ID and call pcw_assignment_get with assignment_id=" + entry["id"] +
                    ", that executor_session_id, work_root=" + str(self.runtime.work_root) +
                    ", workspace=" + self.runtime.root.name + ". Read the returned assignment before work. "
                    "Return your unmodified findings to the primary for MCP recording.\n\n" +
                    json.dumps(entry["assignment"], ensure_ascii=False, sort_keys=True, indent=2))}

    def bind(self, assignment_id: str, executor_session_id: str, *, delivered=False):
        if not isinstance(executor_session_id, str) or not executor_session_id.strip():
            raise ValueError("Actual executor_session_id is required")
        with self.control.guard():
            data = self.load()
            _, entry = self.entry(data, assignment_id)
            if entry["status"] == "cancelled":
                raise ValueError("Assignment was cancelled")
            if entry.get("executor_session_id") not in (None, executor_session_id):
                raise ValueError("Assignment belongs to another executor session")
            entry["executor_session_id"] = executor_session_id
            entry.setdefault("launched_at", now())
            if delivered:
                entry["delivered_revision"] = digest(entry["assignment"])
                entry.setdefault("delivered_at", now())
            if entry["status"] == "prepared":
                entry["status"] = "launched"
            self.store(data)
            return self.handoff(entry)

    def cancel(self, assignment_id: str, reason: str):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("A cancellation reason is required")
        with self.control.guard():
            data = self.load()
            _, entry = self.entry(data, assignment_id)
            if entry.get("launched_at"):
                raise ValueError("A launched executor must return its observations or blocker; it cannot be silently cancelled")
            entry.update(status="cancelled", cancellation_reason=reason)
            self.store(data)
            return {"status": "cancelled", "assignment_id": assignment_id}

    def delivery_blocker(self, assignment_id, reason):
        data = self.load()
        _, entry = self.entry(data, assignment_id)
        entry.setdefault("needs_attention_since", now())
        entry["discrepancy_reason"] = reason
        entry.pop("resolved_by", None)
        self.store(data)

    def result_target(self, assignment_id, executor_session_id):
        data = self.load()
        _, entry = self.entry(data, assignment_id)
        if entry.get("executor_session_id") != executor_session_id or not entry.get("launched_at"):
            raise ValueError("Bind the actual executor to this assignment before saving its return")
        if entry.get("delivered_revision") != digest(entry["assignment"]):
            raise ValueError("Executor must obtain the complete registered assignment through pcw_assignment_get")
        return entry["return_id"]

    def note_saved(self, assignment_id, material):
        data = self.load()
        _, entry = self.entry(data, assignment_id)
        if entry.get("saved_revision") != material.revision:
            entry.update(status="saved", saved_revision=material.revision, saved_at=material.metadata["saved_at"])
            for key in ("read_revision", "read_at", "processed_at", "assessment"):
                entry.pop(key, None)
            self.store(data)

    def note_read(self, assignment_id, material):
        data = self.load()
        _, entry = self.entry(data, assignment_id)
        if entry["return_id"] != material.id or entry.get("saved_revision") != material.revision:
            raise ValueError("Read the exact saved return revision for this assignment")
        entry.update(read_revision=material.revision, read_at=now())
        self.store(data)

    def note_changed(self, *paths):
        data = self.load()
        task = data["tasks"].get(data.get("active"))
        if task is not None and task["status"] != "complete":
            task["owned_paths"] = sorted(set(task.get("owned_paths", [])) | set(paths))
            self.store(data)

    def note_retired(self, material_id):
        data = self.load()
        task = data["tasks"].get(data.get("active"))
        if task is not None:
            for entry in task["assignments"].values():
                if entry["return_id"] == material_id and entry.get("processed_at"):
                    entry["retired_after_processing"] = True
            self.store(data)

    def process(self, assignment_id, assessment):
        data = self.load()
        task, entry = self.entry(data, assignment_id)
        if not entry.get("saved_revision") or entry.get("read_revision") != entry["saved_revision"]:
            raise ValueError("Save and read this assignment's actual return before processing it")
        if not isinstance(assessment, dict) or assessment.get("status") not in {"accepted", "needs_attention"}:
            raise ValueError("assessment.status must be accepted or needs_attention")
        if not isinstance(assessment.get("reason"), str) or not assessment["reason"].strip():
            raise ValueError("Record the reason for the assessment")
        resolves = assessment.get("resolves", [])
        if not isinstance(resolves, list) or any(not isinstance(i, str) for i in resolves):
            raise ValueError("assessment.resolves must be a list of earlier assignment IDs")
        if resolves and assessment["status"] != "accepted":
            raise ValueError("Only an accepted clarification/check can resolve a discrepancy")
        for ident in resolves:
            _, prior = self.entry(data, ident)
            if ident == assignment_id or not prior.get("needs_attention_since") or prior.get("resolved_by"):
                raise ValueError("Resolution must reference an earlier unresolved discrepancy")
        entry.update(processed_at=now(), assessment=assessment, status="processed")
        if assessment["status"] == "needs_attention":
            entry.setdefault("needs_attention_since", now())
            entry["discrepancy_reason"] = assessment["reason"]
            entry.pop("resolved_by", None)
        for ident in resolves:
            task["assignments"][ident]["resolved_by"] = assignment_id
        self.store(data)

    def completion_missing(self):
        data = self.load()
        task = self.active(data)
        missing = []
        def add(field, reason, action):
            missing.append({"field": field, "reason": reason, "action": action})
        for ident, entry in task["assignments"].items():
            if entry["status"] == "cancelled":
                continue
            field = "assignments." + ident
            if not entry.get("saved_revision"):
                add(field, "Executor return has not been saved (including recovery work).", "save_subagent_result")
            elif entry.get("read_revision") != entry["saved_revision"]:
                add(field, "Saved return has not been read for this assignment.", "read")
            elif not entry.get("processed_at"):
                add(field, "Saved return has not been assessed.", "process_result")
            if entry.get("needs_attention_since") and not entry.get("resolved_by"):
                add(field, "An observed discrepancy requires a saved and assessed clarification/check.", "prepare_assignment")
        try:
            actual = self.runtime.durable_state()
        except Exception as exc:
            add("runtime", str(exc), "recover_workspace" if isinstance(exc, RecoveryRequired) else "prepare_assignment")
            return missing
        baseline = task["baseline"]
        affected = {p for p in task.get("owned_paths", []) if baseline.get(p) != actual["files"].get(p)}
        returns = {entry["return_id"] for entry in task["assignments"].values()
                   if entry.get("saved_revision") and not entry.get("retired_after_processing")}
        for ident in returns:
            path = actual["paths"].get(ident)
            if path:
                affected.add(path)
            else:
                add("returns." + ident, "Saved return is no longer addressable; resolve it before completion.", "read")
        affected_ids = {ident for ident, path in actual["paths"].items() if path in affected}
        for ident in sorted(affected_ids & set(actual["pending"])):
            add("materials." + ident, "Current material body has not been prepared for search.", "prepare")
        for item in actual["unregistered"]:
            if item["path"] in affected:
                add("materials." + item["path"], "Changed material is not registered.", "adopt")
        current = self.runtime.current_get()
        if not all(current.get(k) for k in ("goal", "completion", "step")):
            add("current", "Current must state the request, completion condition and actual step.", "current_set")
        if current.get("blocker"):
            add("current.blocker", "Current records an unresolved blocker: " + current["blocker"], "resolve_blocker")
        for field in ("goal", "constraints", "completion"):
            if current.get(field) != task["request"][field]:
                add("current." + field, "Current differs from the registered user request.", "current_set")
        if task["request"]["checkpoint_policy"] == "required":
            for path in self.runtime.uncheckpointed(sorted(affected)):
                add("checkpoint." + path, "Changed durable path is not in the current memory checkpoint.", "checkpoint")
        return missing

    def complete(self):
        data = self.load()
        task = self.active(data)
        task.update(status="complete", completed_at=now())
        self.store(data)

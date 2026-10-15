"""Project definition and independent task state, outside vector knowledge."""

from __future__ import annotations

import json
import uuid

import yaml

from .runtime import PCWError, _id, _parse, _revision
from .policies import policies
from .workspaces import encode


TASK_FIELDS = {
    "goal",
    "constraints",
    "verified_state",
    "next_step",
    "blockers",
    "status",
}
TASK_STATUSES = {"active", "blocked", "completed", "cancelled"}


class DocumentsMixin:
    def project_read(self):
        self._require_format()
        with self.control.guard():
            path = self.engine.root / "PROJECT.md"
            self.engine._assert_safe(path)
            text = path.read_bytes().decode("utf-8")
            return {"path": "PROJECT.md", "content": text, "revision": _revision(text)}

    def project_update(
        self,
        cycle_id: str,
        content: str,
        expected_revision: str,
        user_request: str,
        proposal_id: str | None = None,
    ):
        """Prepare PROJECT changes for presentation; project_apply performs the write."""
        if not isinstance(user_request, str) or not user_request.strip():
            raise PCWError("Supply the user's requested project change")
        if not isinstance(content, str) or not content.strip():
            raise PCWError("Project content must be nonempty text")
        with self._cycle(cycle_id) as (records, cycle):
            self._require_work(cycle)
            current = self.project_read()
            if current["revision"] != expected_revision:
                raise PCWError("PROJECT changed; read the current revision")
            ident = self._proposal_id(cycle_id, cycle, proposal_id, "project")
            instructions = self._instructions()
            before = {
                "path": "PROJECT.md",
                "text": current["content"],
                "fingerprint": current["revision"],
            }
            after = {
                "path": "PROJECT.md",
                "text": content,
                "fingerprint": _revision(content),
            }
            plan = {
                "cycle_id": cycle_id,
                "proposal_id": ident,
                "kind": "project",
                "created_ids": {},
                "user_request": user_request,
                "instructions_revision": instructions["revision"],
                "knowledge_approval_required": policies(instructions["content"])[
                    "knowledge_approval_required"
                ],
                "entries": {"PROJECT.md": {"before": before, "after": after}},
            }
            state = "no_changes" if content == current["content"] else "prepared"
            if state == "no_changes":
                plan["no_changes_reason"] = "PROJECT content is unchanged."
            return self._save_plan(records, cycle, plan, state)

    def project_apply(
        self,
        cycle_id: str,
        proposal_id: str,
        expected_revision: str,
        confirmation: str | None = None,
    ):
        with self._cycle(cycle_id) as (records, cycle):
            self._require_work(cycle)
            entry = cycle["proposals"].get(_id(proposal_id))
            if (
                entry is None
                or entry["revision"] != expected_revision
                or entry["state"] in {"discarded", "no_changes"}
            ):
                raise PCWError("Apply the exact presented PROJECT revision")
            plan = self._load_plan(cycle_id, proposal_id, entry)
            if plan.get("kind") != "project":
                raise PCWError("Use the apply operation matching the proposal kind")
            if entry["state"] == "applied":
                return {
                    "status": "applied",
                    "proposal_id": proposal_id,
                    "replayed": True,
                }
            if entry["state"] == "prepared":
                if plan["instructions_revision"] != self._instructions()["revision"]:
                    raise PCWError(
                        "Instructions changed; prepare and present PROJECT again"
                    )
                if plan["knowledge_approval_required"] and (
                    not isinstance(confirmation, str) or not confirmation.strip()
                ):
                    raise PCWError(
                        "Current user's explicit confirmation of the presented PROJECT changes is required"
                    )
            change = plan["entries"]["PROJECT.md"]
            retry = entry["state"] != "prepared"
            if not (retry and self._matches(change["after"])) and not self._matches(
                change["before"]
            ):
                raise PCWError("PROJECT conflict; prepare and present again")
            entry["state"] = "applying"
            self._persist(records)
            try:
                self.engine._write(
                    self.engine.root / "PROJECT.md", change["after"]["text"]
                )
                if not self._matches(change["after"]):
                    raise PCWError("PROJECT write verification failed")
                history = self._history_record(proposal_id)
                entry["state"] = "applied"
                self._persist(records)
                return {
                    "status": "applied",
                    "proposal_id": proposal_id,
                    "project": self.project_read(),
                    "tmp_preserved": True,
                    "history": history,
                }
            except Exception as exc:
                entry["state"] = "partial"
                self._persist(records)
                return {
                    "status": "partial",
                    "error": str(exc),
                    "next_action": "project_apply",
                    "tmp_preserved": True,
                }

    def _task_path(self, task_id):
        path = self.engine.root / "current" / (_id(task_id) + ".md")
        self.engine._assert_safe(path)
        return path

    @staticmethod
    def _task_fields(fields):
        if not isinstance(fields, dict) or set(fields) - TASK_FIELDS:
            raise PCWError(
                "Unknown Current fields; use " + ", ".join(sorted(TASK_FIELDS))
            )
        if any(not isinstance(value, str) for value in fields.values()):
            raise PCWError("Current fields must be text")
        if "status" in fields and fields["status"] not in TASK_STATUSES:
            raise PCWError("Invalid task status")
        if "goal" in fields and not fields["goal"].strip():
            raise PCWError("Task goal must be nonempty")

    def _task_write(self, task_id, fields):
        self._task_fields(fields)
        text = (
            "---\n"
            + yaml.safe_dump(fields, sort_keys=False, allow_unicode=True)
            + "---\n"
        )
        self.engine._write(self._task_path(task_id), text)
        return self.current_read(task_id)

    def current_create(
        self, cycle_id: str, request_id: str, goal: str, constraints: str = ""
    ):
        _id(request_id)
        self._task_fields({"goal": goal, "constraints": constraints})
        with self._cycle(cycle_id) as (records, cycle):
            self._require_work(cycle)
            path = self.control.root / "task-requests.json"
            self.control.safe(path)
            requests = json.loads(path.read_text()) if path.exists() else {}
            signature = _revision(encode([cycle_id, goal, constraints]))
            old = requests.get(request_id)
            if old and old["signature"] != signature:
                raise PCWError("Task request_id belongs to a different task")
            if cycle.get("task_id") and (not old or old["task_id"] != cycle["task_id"]):
                raise PCWError(
                    "This cycle already has a task; start another cycle for another task"
                )
            task_id = old["task_id"] if old else uuid.uuid4().hex
            requests[request_id] = {"signature": signature, "task_id": task_id}
            self.control.write(path, encode(requests))
            if not self._task_path(task_id).exists():
                result = self._task_write(
                    task_id,
                    {
                        "goal": goal,
                        "constraints": constraints,
                        "verified_state": "",
                        "next_step": "",
                        "blockers": "",
                        "status": "active",
                    },
                )
            else:
                result = self.current_read(task_id)
            cycle["task_id"] = task_id
            self._persist(records)
            return result

    def current_read(self, task_id: str):
        self._require_format()
        with self.control.guard():
            path = self._task_path(task_id)
            if not path.is_file():
                raise PCWError(
                    "Unknown task_id; list tasks and select the intended task"
                )
            text = path.read_bytes().decode("utf-8")
            fields, _ = _parse(text)
            self._task_fields(fields)
            return {
                "task_id": task_id,
                "path": path.relative_to(self.engine.root).as_posix(),
                "revision": _revision(text),
                **fields,
            }

    def current_list(self, offset: int = 0, limit: int = 50):
        self._require_format()
        if (
            type(offset) is not int
            or offset < 0
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise PCWError("Use a nonnegative offset and limit between 1 and 100")
        with self.control.guard():
            paths = sorted((self.engine.root / "current").glob("*.md"))
            result = []
            for path in paths[offset : offset + limit]:
                task = self.current_read(path.stem)
                result.append(
                    {
                        key: task[key]
                        for key in ("task_id", "goal", "status", "revision")
                    }
                )
            return {
                "tasks": result,
                "total": len(paths),
                "next_offset": offset + limit if offset + limit < len(paths) else None,
            }

    def current_update(
        self, cycle_id: str, task_id: str, expected_revision: str, fields: dict
    ):
        self._task_fields(fields)
        with self._cycle(cycle_id) as (_, cycle):
            self._require_work(cycle)
            if cycle.get("task_id") != task_id:
                raise PCWError(
                    "This cycle is not bound to that task; select it explicitly on startup"
                )
            current = self.current_read(task_id)
            if current["revision"] != expected_revision:
                raise PCWError("Current changed; read the latest task revision")
            final = {key: current[key] for key in TASK_FIELDS}
            final.update(fields)
            if all(final[key] == current[key] for key in TASK_FIELDS):
                return {**current, "unchanged": True}
            return self._task_write(task_id, final)

"""Explicit task/assignment receipts and observable completion conditions."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import uuid
from typing import Literal

from .control import RecoveryRequired


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


CheckpointPolicy = Literal["not_authorized", "required", "forbidden"]


def validate_request(goal, constraints, completion, checkpoint_policy, checkpoint_reason):
    if not all(isinstance(v, str) and v.strip() for v in (goal, completion)) or not isinstance(constraints, str):
        raise ValueError("Task goal and completion must be non-empty; constraints must be text")
    if checkpoint_policy not in {"required", "forbidden", "not_authorized"}:
        raise ValueError("checkpoint_policy must be required, forbidden or not_authorized")
    if not isinstance(checkpoint_reason, str) or (checkpoint_policy != "not_authorized" and not checkpoint_reason.strip()):
        raise ValueError("Record the actual authority for requiring or forbidding a checkpoint")
    return dict(goal=goal, constraints=constraints, completion=completion,
                checkpoint_policy=checkpoint_policy, checkpoint_reason=checkpoint_reason)


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
              checkpoint_policy: CheckpointPolicy = "not_authorized", checkpoint_reason: str = ""):
        request = validate_request(goal, constraints, completion, checkpoint_policy, checkpoint_reason)
        with self.control.guard():
            data = self.load()
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

    def update(self, expected_request_revision, reason, **changes):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("State the user's correction or authority for changing the active request")
        with self.control.guard():
            data = self.load()
            task = self.active(data)
            if task["status"] == "complete":
                raise ValueError("A completed task cannot be changed; open the next request")
            if digest(task["request"]) != expected_request_revision:
                raise ValueError("Task request changed; read task_status before updating")
            request = validate_request(**{**task["request"], **{k: v for k, v in changes.items() if v is not None}})
            task.setdefault("request_changes", []).append({"previous": task["request"], "reason": reason, "changed_at": now()})
            task["request"] = request
            self.store(data)
            return self.status()

    def status(self):
        with self.control.guard():
            data = self.load()
            task = data["tasks"].get(data.get("active"))
            return {"task": task, "status": "absent" if task is None else task["status"],
                    "request_revision": digest(task["request"]) if task else None}

    def checks_set(self, checks, reason):
        if not isinstance(checks, list) or not isinstance(reason, str) or not reason.strip():
            raise ValueError("Supply a checks plan and the reason for this plan or its revision")
        with self.control.guard():
            data = self.load()
            task = self.active(data)
            if task["status"] == "complete":
                raise ValueError("Cannot change the check plan of a completed task")
            seen = set()
            for check in checks:
                if not isinstance(check, dict) or set(check) - {"id", "when", "scope", "criteria", "assignment_id"}:
                    raise ValueError("Each check needs id, when, scope, criteria and optionally assignment_id")
                if any(not isinstance(check.get(k), str) or not check[k].strip() for k in ("id", "when", "scope")):
                    raise ValueError("Check id, when and scope must be non-empty strings")
                if check["id"] in seen:
                    raise ValueError("Duplicate check id")
                seen.add(check["id"])
                if not isinstance(check.get("criteria"), list) or not check["criteria"] or any(not isinstance(c, str) or not c.strip() for c in check["criteria"]):
                    raise ValueError("Check criteria must be a non-empty list of strings")
                if "assignment_id" in check:
                    _, entry = self.entry(data, check["assignment_id"])
                    if entry["assignment"].get("purpose") != "check":
                        raise ValueError("A factual check must reference a check assignment")
            task.setdefault("check_plan_history", []).append({"checks": task.get("checks_plan", []), "reason": reason, "changed_at": now()})
            task["checks_plan"] = checks
            self.store(data)
            return self.status()

    def note_checks_due(self, due):
        data = self.load()
        task = self.active(data)
        task["checks_due"] = due
        self.store(data)

    def register(self, assignment, environment_revision, continuation_of=None, check_id=None):
        data = self.load()
        task = self.active(data)
        if task["status"] == "complete":
            raise ValueError("Cannot add assignments to a completed task")
        planned = None
        if check_id is not None:
            if assignment.get("purpose") != "check":
                raise ValueError("check_id is only valid for a check assignment")
            planned = next((check for check in task.get("checks_plan", []) if check["id"] == check_id), None)
            if planned is None:
                raise ValueError("check_id must identify a registered planned check")
        prior = None
        if continuation_of:
            _, prior = self.entry(data, continuation_of)
            if not prior.get("executor_session_id") or not prior.get("processed_at"):
                raise ValueError("Read and process the previous executor return before a continuation")
        key = digest([assignment, environment_revision, continuation_of] + ([check_id] if check_id is not None else []))
        for entry in task["assignments"].values():
            if entry["key"] == key:
                return self.handoff(entry)
        if planned and planned.get("assignment_id"):
            bound = task["assignments"].get(planned["assignment_id"], {})
            if bound.get("status") != "cancelled" and planned["assignment_id"] != continuation_of:
                raise ValueError("The planned check already has an assignment; continue or cancel it first")
        ident = uuid.uuid4().hex
        entry = {"id": ident, "key": key, "assignment": assignment,
                 "environment_revision": environment_revision, "prepared_at": now(),
                 "return_id": None if assignment.get("purpose") == "semantic_split" else self.runtime._allocate_material_id(),
                 "executor_session_id": prior["executor_session_id"] if prior else None,
                 "continuation_of": continuation_of, "status": "prepared"}
        if check_id is not None:
            entry["check_id"] = check_id
            planned["assignment_id"] = ident
        task["assignments"][ident] = entry
        task["status"] = "active"
        self.store(data)
        return self.handoff(entry)

    def handoff(self, entry):
        # Only this packet goes to the worker. Ledger IDs, model selection and
        # memory coordinates stay with the primary, including on continuations.
        packet = {key: entry["assignment"][key] for key in (
            "goal", "expected_result", "boundaries", "context", "constraints",
            "acceptance_criteria", "knowledge_to_return", "source_units") if key in entry["assignment"]}
        prohibition = (
            "Execute only the explicitly authorized task below. Work in a separate context; "
            "do not inherit the primary's conversation or memory instructions. "
            "Do not use PCW MCP tools. Do not discover, read or change any .pcw directory "
            "through filesystem tools, shell, scripts or other tools. Do not manage shared memory "
            "or Current. Return your findings to the primary; do not save a memory report yourself. "
            "Only explicitly listed source objects and actions are authorized.\n\n")
        return {"assignment_id": entry["id"], "return_id": entry["return_id"],
                "assignment": entry["assignment"], "assignment_revision": digest(entry["assignment"]),
                "executor_session_id": entry["executor_session_id"],
                "context_policy": "isolated_assignment_only",
                "launch_message": prohibition + json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2)}

    def bind(self, assignment_id: str, executor_session_id: str):
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
            entry["delivered_revision"] = digest(entry["assignment"])
            entry.setdefault("delivered_at", now())
            if entry["status"] == "prepared":
                entry["status"] = "launched"
            self.store(data)
            return {"assignment_id": assignment_id, "executor_session_id": executor_session_id,
                    "delivered_revision": entry["delivered_revision"], "status": entry["status"]}

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
            raise ValueError("Primary must bind the executor after sending the complete launch message")
        if entry["return_id"] is None:
            raise ValueError("Semantic boundaries are service data; submit them through pcw_submit_boundaries, not knowledge")
        return entry["return_id"]

    @staticmethod
    def result_records(entry):
        """Uniform saved-return receipts, including persisted pre-batch ledgers."""
        if "result_blocks" in entry:
            return entry["result_blocks"]
        if entry.get("return_id") is None:
            return []
        return [{"material_id": entry["return_id"], **{key: entry[key] for key in (
            "saved_revision", "saved_at", "read_revision", "read_at", "retired_after_processing") if key in entry}}]

    @staticmethod
    def _clear_assessment(entry):
        for key in ("read_revision", "read_at", "processed_at", "assessment"):
            entry.pop(key, None)

    @staticmethod
    def _summarize_blocks(entry):
        blocks = entry["result_blocks"]
        if all(block.get("saved_revision") for block in blocks):
            entry["saved_revision"] = digest([[block["material_id"], block["saved_revision"]] for block in blocks])
            entry["saved_at"] = max(block["saved_at"] for block in blocks)
            entry["status"] = "saved" if not entry.get("processed_at") else "processed"
            if all(block.get("read_revision") == block["saved_revision"] for block in blocks):
                entry["read_revision"] = entry["saved_revision"]
                entry["read_at"] = max(block["read_at"] for block in blocks)
        else:
            entry.pop("saved_revision", None)
            entry.pop("read_revision", None)
            entry["status"] = "saving"

    def reserve_result_blocks(self, assignment_id, executor_session_id, blocks, expected_previous_revisions=None):
        """Persist all MCP-generated names before any body write; exact retries reuse them."""
        if not isinstance(blocks, list) or not 1 <= len(blocks) <= 100 or any(not isinstance(body, str) or not body.strip() for body in blocks):
            raise ValueError("blocks must be a non-empty list of non-empty knowledge texts")
        with self.control.guard():
            self.result_target(assignment_id, executor_session_id)
            data = self.load()
            task, entry = self.entry(data, assignment_id)
            incoming = [digest(body) for body in blocks]
            records = entry.get("result_blocks")
            if task["status"] == "complete" and (records is None or [record["content_digest"] for record in records] != incoming):
                raise ValueError("A completed task cannot accept changed result blocks")
            if records is None:
                if entry.get("saved_revision"):
                    material = self.runtime.materials.get(entry["return_id"])
                    if len(blocks) != 1 or material is None or material.content != blocks[0]:
                        raise ValueError("A saved legacy return cannot be replaced by a different block collection")
                    records = self.result_records(entry)
                    records[0]["content_digest"] = incoming[0]
                else:
                    reserved_at = now()
                    records = [{"material_id": entry["return_id"] if i == 0 else self.runtime._allocate_material_id(),
                                "content_digest": value, "saved_at": reserved_at} for i, value in enumerate(incoming)]
                    self._clear_assessment(entry)
                entry["result_blocks"] = records
            elif [block["content_digest"] for block in records] != incoming:
                entry["return_conflict"] = {"incoming_digest": digest(incoming), "observed_at": now()}
                self.store(data)
                if (not isinstance(expected_previous_revisions, list) or len(expected_previous_revisions) != len(records)
                        or len(blocks) != len(records)):
                    raise ValueError("Conflicting result blocks; provide every current expected_previous_revisions for an explicit correction")
                for record, expected in zip(records, expected_previous_revisions):
                    material = self.runtime.materials.get(record["material_id"])
                    if not isinstance(expected, str) or material is None or material.revision != expected:
                        raise ValueError("Result block revision changed; read every current block before correcting")
                for record, value, expected in zip(records, incoming, expected_previous_revisions):
                    if record["content_digest"] != value:
                        record.update(content_digest=value, saved_at=now(), previous_revision=expected)
                        for key in ("saved_revision", "read_revision", "read_at"):
                            record.pop(key, None)
                self._clear_assessment(entry)
            elif expected_previous_revisions is not None:
                if not isinstance(expected_previous_revisions, list) or len(expected_previous_revisions) != len(records):
                    raise ValueError("Supply every current expected_previous_revisions for an explicit correction")
                for record, expected in zip(records, expected_previous_revisions):
                    material = self.runtime.materials.get(record["material_id"])
                    resumed = (material is not None and expected == record.get("previous_revision")
                               and digest(material.content) == record["content_digest"])
                    if not isinstance(expected, str) or material is None or (material.revision != expected and not resumed):
                        raise ValueError("Result block revision changed; read every current block before correcting")
                if entry.get("return_conflict"):
                    entry["return_conflict"]["incoming_digest"] = digest(incoming)
            self._summarize_blocks(entry)
            self.store(data)
            return [{"material_id": block["material_id"], "revision": block.get("saved_revision"),
                     "saved_at": block["saved_at"], "previous_revision": block.get("previous_revision")} for block in records]

    def note_conflict(self, assignment_id, result, block_key=None):
        data = self.load()
        _, entry = self.entry(data, assignment_id)
        entry["return_conflict"] = {"incoming_digest": digest(result), "observed_at": now()}
        if block_key is not None:
            entry["return_conflict"]["block_key"] = block_key
        self.store(data)

    def note_saved(self, assignment_id, material):
        data = self.load()
        _, entry = self.entry(data, assignment_id)
        if "result_blocks" in entry:
            record = next((block for block in entry["result_blocks"] if block["material_id"] == material.id), None)
            if record is None or record["content_digest"] != digest(material.content):
                raise ValueError("Saved material must match a reserved result block")
            if record.get("saved_revision") != material.revision:
                record.update(saved_revision=material.revision, saved_at=material.metadata["saved_at"])
                record.pop("read_revision", None)
                record.pop("read_at", None)
                self._clear_assessment(entry)
            self._summarize_blocks(entry)
            incoming = digest([block["content_digest"] for block in entry["result_blocks"]])
            if entry.get("saved_revision") and entry.get("return_conflict", {}).get("incoming_digest") == incoming:
                entry.pop("return_conflict", None)
        else:
            if entry["return_id"] != material.id:
                raise ValueError("Saved material is not this assignment's reserved return")
            if entry.get("return_conflict") and entry["return_conflict"]["incoming_digest"] == digest(material.content):
                entry.pop("return_conflict", None)
            if entry.get("saved_revision") != material.revision:
                entry.update(status="saved", saved_revision=material.revision, saved_at=material.metadata["saved_at"])
                self._clear_assessment(entry)
        self.store(data)

    def note_read_many(self, assignment_id, materials):
        with self.control.guard():
            data = self.load()
            _, entry = self.entry(data, assignment_id)
            records = self.result_records(entry)
            by_id = {record["material_id"]: record for record in records}
            for material in materials:
                record = by_id.get(material.id)
                if record is None or record.get("saved_revision") != material.revision:
                    raise ValueError("Read the exact saved return revision for this assignment")
            observed_at = now()
            if "result_blocks" in entry:
                for material in materials:
                    by_id[material.id].update(read_revision=material.revision, read_at=observed_at)
                self._summarize_blocks(entry)
            elif materials:
                entry.update(read_revision=materials[0].revision, read_at=observed_at)
            self.store(data)

    def note_read(self, assignment_id, material):
        return self.note_read_many(assignment_id, [material])

    def invalidations(self, material_id, revision):
        """Only exact bodies marked incorrect are withheld from knowledge retrieval."""
        result = []
        for task in self.load()["tasks"].values():
            for ident, entry in task["assignments"].items():
                if entry.get("affected_materials", {}).get(material_id) == revision:
                    result.append({"assignment_id": ident, "material_id": material_id, "revision": revision,
                                   "reason": entry.get("discrepancy_reason", "Needs correction")})
        return result

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
                if not entry.get("processed_at"):
                    continue
                if "result_blocks" in entry:
                    for record in entry["result_blocks"]:
                        if record["material_id"] == material_id:
                            record["retired_after_processing"] = True
                elif entry["return_id"] == material_id:
                    entry["retired_after_processing"] = True
            self.store(data)

    def process(self, assignment_id, assessment):
        data = self.load()
        task, entry = self.entry(data, assignment_id)
        if task["status"] == "complete":
            raise ValueError("A completed task cannot accept new assessments")
        if not entry.get("saved_revision") or entry.get("read_revision") != entry["saved_revision"]:
            raise ValueError("Save and read every actual return block before processing this assignment")
        if entry.get("return_conflict"):
            raise ValueError("Resolve the conflicting actual return before accepting a different saved body")
        for record in self.result_records(entry):
            material = self.runtime.materials.get(record["material_id"])
            if record.get("retired_after_processing") and entry.get("processed_at"):
                continue
            if material is None or material.revision != record.get("read_revision"):
                raise ValueError("Read and assess the current saved revision of every result block")
        if not isinstance(assessment, dict) or assessment.get("status") not in {"accepted", "needs_attention"}:
            raise ValueError("assessment.status must be accepted or needs_attention")
        if not isinstance(assessment.get("reason"), str) or not assessment["reason"].strip():
            raise ValueError("Record the reason for the assessment")
        if set(assessment) - {"status", "reason", "resolves", "affected_material_ids"}:
            raise ValueError("assessment accepts only status, reason, resolves and affected_material_ids")
        resolves = assessment.get("resolves", [])
        if not isinstance(resolves, list) or any(not isinstance(i, str) for i in resolves) or len(set(resolves)) != len(resolves):
            raise ValueError("assessment.resolves must be a list of unique earlier assignment IDs")
        if resolves and assessment["status"] != "accepted":
            raise ValueError("Only an accepted clarification/check can resolve a discrepancy")
        resolution_evidence = {}
        for ident in resolves:
            _, prior = self.entry(data, ident)
            if ident == assignment_id or not prior.get("needs_attention_since") or prior.get("resolved_by"):
                raise ValueError("Resolution must reference an earlier unresolved discrepancy")
            evidence = []
            for material_id, previous_revision in prior.get("affected_materials", {}).items():
                material = self.runtime.materials.get(material_id)
                if material is not None and material.revision == previous_revision:
                    raise ValueError("Apply the correction to every affected knowledge material before resolving the discrepancy: " + material_id)
                evidence.append({"material_id": material_id, "previous_revision": previous_revision,
                                 "current_revision": material.revision if material is not None else None})
            resolution_evidence[ident] = evidence
        affected = None
        if assessment["status"] == "needs_attention":
            affected_ids = assessment.get("affected_material_ids", [r["material_id"] for r in self.result_records(entry)])
            if (not isinstance(affected_ids, list) or not affected_ids or any(not isinstance(i, str) for i in affected_ids)
                    or len(set(affected_ids)) != len(affected_ids)):
                raise ValueError("affected_material_ids must list unique existing knowledge materials")
            affected = {}
            for material_id in affected_ids:
                material = self.runtime.materials.get(material_id)
                if material is None:
                    raise ValueError("Affected knowledge material does not exist: " + material_id)
                affected[material_id] = material.revision
        elif "affected_material_ids" in assessment:
            raise ValueError("affected_material_ids is only valid for needs_attention")
        entry.update(processed_at=now(), assessment=assessment, status="processed")
        if affected is not None:
            entry.setdefault("needs_attention_since", now())
            entry["discrepancy_reason"] = assessment["reason"]
            entry.setdefault("affected_materials", {}).update(affected)
            entry.pop("resolved_by", None)
        for ident in resolves:
            task["assignments"][ident]["resolved_by"] = assignment_id
            task["assignments"][ident]["resolution_evidence"] = resolution_evidence[ident]
        self.store(data)

    def note_service(self, assignment_id, result, observed):
        data = self.load()
        _, entry = self.entry(data, assignment_id)
        entry.update(service_result=result, service_observed=observed, processed_at=now(), status="processed")
        entry.pop("service_error", None)
        prior_id = entry.get("continuation_of")
        while prior_id:
            _, prior = self.entry(data, prior_id)
            def source_ids(assignment):
                sources = assignment.get("split_sources", [assignment.get("split_source", {})])
                return [source.get("material_id") for source in sources]
            if prior.get("service_error") and source_ids(prior["assignment"]) == source_ids(entry["assignment"]):
                prior["service_resolved_by"] = assignment_id
            prior_id = prior.get("continuation_of")
        self.store(data)

    def service_error(self, assignment_id, executor_session_id, error):
        if not isinstance(error, str) or not error.strip():
            raise ValueError("Record the actual service return or error")
        with self.control.guard():
            data = self.load()
            _, entry = self.entry(data, assignment_id)
            if entry.get("return_id") is not None or not entry.get("launched_at") or entry.get("executor_session_id") != executor_session_id:
                raise ValueError("A bound semantic service assignment is required")
            entry.update(service_error=error, processed_at=now(), status="needs_attention")
            entry.pop("service_resolved_by", None)
            self.store(data)
            return {"assignment_id": assignment_id, "status": "needs_attention", "result_storage": "control"}

    def completion_missing(self):
        data = self.load()
        task = self.active(data)
        missing = []
        def add(field, reason, action):
            missing.append({"field": field, "reason": reason, "action": action})
        if task.get("checks_due"):
            add("checks_due", "A previously declared factual check is still due.", "declare_checks")
        for check in task.get("checks_plan", []):
            entry = task["assignments"].get(check.get("assignment_id"), {})
            if not entry.get("processed_at") or entry.get("assessment", {}).get("status") != "accepted":
                add("checks_plan." + check["id"], "Planned factual check needs an accepted observed result.", "assign_factual_check")
        for ident, entry in task["assignments"].items():
            if entry["status"] == "cancelled":
                continue
            field = "assignments." + ident
            if entry.get("return_id") is None:
                if not entry.get("processed_at"):
                    add(field, "Semantic boundaries have not been successfully applied by the primary.", "submit_boundaries")
                if entry.get("service_error") and not entry.get("service_resolved_by"):
                    add(field, "Semantic service failed: " + entry["service_error"], "prepare_assignment")
                if entry.get("needs_attention_since") and not entry.get("resolved_by"):
                    add(field, "The service assignment has an unresolved discrepancy.", "prepare_assignment")
                continue
            if entry.get("return_conflict"):
                add(field, "The actual return conflicts with the saved body.", "save_subagent_result")
            if not entry.get("saved_revision"):
                add(field, "Executor return has not been saved (including recovery work).", "save_subagent_result")
            elif entry.get("read_revision") != entry["saved_revision"]:
                add(field, "Saved return has not been read for this assignment.", "read")
            elif not entry.get("processed_at"):
                add(field, "Saved return has not been assessed.", "process_result")
            if entry.get("needs_attention_since") and not entry.get("resolved_by"):
                add(field, "An observed discrepancy requires a saved and assessed clarification/check.", "prepare_assignment")
            for material_id, revision in entry.get("affected_materials", {}).items():
                material = self.runtime.materials.get(material_id)
                if material is not None and material.revision == revision:
                    add("materials." + material_id, "Knowledge marked incorrect is still active unchanged.", "update")
        try:
            actual = self.runtime.durable_state()
        except Exception as exc:
            add("runtime", str(exc), "recover_workspace" if isinstance(exc, RecoveryRequired) else "prepare_assignment")
            return missing
        baseline = task["baseline"]
        affected = {p for p in task.get("owned_paths", []) if baseline.get(p) != actual["files"].get(p)}
        returns = {record["material_id"] for entry in task["assignments"].values()
                   for record in self.result_records(entry)
                   if record.get("saved_revision") and not record.get("retired_after_processing")}
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

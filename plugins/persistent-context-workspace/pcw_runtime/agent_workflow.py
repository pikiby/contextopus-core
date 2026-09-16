"""Environment-bound agent workflow state and mechanical prerequisites.

The main agent owns model selection and semantic acceptance.  This module only
persists the environment/map supplied by that agent and verifies facts that the
plugin can observe.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from .assignments import TaskLedger
from .control import RecoveryRequired


class WorkflowError(ValueError):
    """A malformed workflow input or stored workflow asset."""


class ModelSnapshot(TypedDict):
    id: str
    reasoning: NotRequired[dict[str, list[object]]]
    launch_constraints: NotRequired[dict[str, object]]


class EnvironmentSnapshot(TypedDict):
    environment: str
    version: str
    models: list[ModelSnapshot]
    native: dict[str, object]


class ToolsMapProfile(TypedDict):
    id: str
    model: str
    reasoning: dict[str, object]
    roles: list[str]
    suitable_when: list[str]


class SavedResultCoordinate(TypedDict):
    material_name: str
    executor_session_id: str
    assignment_id: NotRequired[str]


class AssignmentContext(TypedDict):
    goal: str
    expected_result: str
    boundaries: str
    context: "AssignmentKnowledgeContext"
    constraints: list[str]
    acceptance_criteria: list[str]
    knowledge_to_return: str
    profile: str
    selection_reason: str
    launch_parameters: NotRequired[dict[str, object]]
    purpose: NotRequired[Literal["work", "recovery"]]


class AssignmentKnowledgeContext(TypedDict):
    summary: str
    material_ids: list[str]


class ChecksDue(TypedDict):
    status: Literal["none_due", "assigned"]
    reason: NotRequired[str]
    checks: NotRequired[list[SavedResultCoordinate]]


class AcceptanceChecks(TypedDict):
    status: Literal["none_assigned", "assigned"]
    scope: str
    reason: NotRequired[str]
    checks: NotRequired[list[SavedResultCoordinate]]


class ActionContext(TypedDict):
    assignment: NotRequired[AssignmentContext]
    result: NotRequired[SavedResultCoordinate]
    checks_due: NotRequired[ChecksDue]
    acceptance_checks: NotRequired[AcceptanceChecks]
    mismatch_needs_attention: NotRequired[bool]
    planned_checks_due: NotRequired[bool]
    continuation_of: NotRequired[str]
    assessment: NotRequired[dict[str, Any]]


_ACTION_NAMES = frozenset({"prepare_assignment", "process_result", "transition", "finish"})
ActionName = Literal["prepare_assignment", "process_result", "transition", "finish"]
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.md$")
_STATE_FILE = "agent-workflow.json"


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _revision(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowError(f"{field} must be a non-empty string")
    return value.strip()


def _object(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise WorkflowError(f"{field} must be an object")
    return value


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise WorkflowError(f"{field} must be a non-empty list of strings")
    result = [_string(item, field) for item in value]
    if len(set(result)) != len(result):
        raise WorkflowError(f"{field} must not contain duplicate values")
    return result


def _json_value(value: object, field: str) -> object:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WorkflowError(f"{field} must contain JSON values") from exc
    return value


def _canonical_capability(value: object) -> object:
    """Normalise unordered capability declarations without naming provider fields."""
    if isinstance(value, dict):
        return {str(key): _canonical_capability(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        values = [_canonical_capability(item) for item in value]
        return sorted(values, key=_canonical)
    return value


def _same_json(left: object, right: object) -> bool:
    """JSON equality keeps booleans and numbers distinct unlike Python ==."""
    return _canonical(left) == _canonical(right)


def normalize_environment_snapshot(value: object) -> dict[str, object]:
    """Validate a portable actual-environment snapshot and put it in stable order."""
    raw = _object(value, "environment_snapshot")
    required = {"environment", "version", "models", "native"}
    missing = required - set(raw)
    if missing:
        raise WorkflowError("environment_snapshot is missing " + ", ".join(sorted(missing)))
    unexpected = set(raw) - required
    if unexpected:
        raise WorkflowError("environment_snapshot has unsupported fields: " + ", ".join(sorted(unexpected)))
    environment = _string(raw["environment"], "environment_snapshot.environment")
    version = _string(raw["version"], "environment_snapshot.version")
    native = _object(raw["native"], "environment_snapshot.native")
    _json_value(native, "environment_snapshot.native")
    models_value = raw["models"]
    if not isinstance(models_value, list):
        raise WorkflowError("environment_snapshot.models must be a list")
    models: list[dict[str, object]] = []
    seen = set()
    for index, item in enumerate(models_value):
        model = _object(item, f"environment_snapshot.models[{index}]")
        extras = set(model) - {"id", "reasoning", "launch_constraints"}
        if "id" not in model or extras:
            raise WorkflowError(f"environment_snapshot.models[{index}] must contain id and supported optional fields")
        ident = _string(model["id"], f"environment_snapshot.models[{index}].id")
        if ident in seen:
            raise WorkflowError("environment_snapshot.models contains duplicate model id: " + ident)
        seen.add(ident)
        normalized: dict[str, object] = {"id": ident}
        # A model without any reasoning parameter is represented by an absent
        # field or {}.  No environment-specific effort names are assumed.
        reasoning = model.get("reasoning", {})
        reasoning_obj = _object(reasoning, f"environment_snapshot.models[{index}].reasoning")
        normalized_reasoning: dict[str, list[object]] = {}
        for parameter, values in reasoning_obj.items():
            key = _string(parameter, f"environment_snapshot.models[{index}].reasoning key")
            if not isinstance(values, list) or not values:
                raise WorkflowError(f"environment_snapshot.models[{index}].reasoning.{key} must be a non-empty list")
            normalized_values = [_json_value(v, f"environment_snapshot.models[{index}].reasoning.{key}") for v in values]
            unique_values = {_canonical(item): item for item in normalized_values}
            if len(unique_values) != len(normalized_values):
                raise WorkflowError(f"environment_snapshot.models[{index}].reasoning.{key} must not contain duplicate values")
            # Capability values are a set.  Their discovery order must not
            # invalidate an otherwise current map.
            normalized_reasoning[key] = [unique_values[item] for item in sorted(unique_values)]
        normalized["reasoning"] = {key: normalized_reasoning[key] for key in sorted(normalized_reasoning)}
        constraints = model.get("launch_constraints", {})
        constraints_obj = _object(constraints, f"environment_snapshot.models[{index}].launch_constraints")
        _json_value(constraints_obj, f"environment_snapshot.models[{index}].launch_constraints")
        normalized["launch_constraints"] = _canonical_capability(constraints_obj)
        models.append(normalized)
    return {"environment": environment, "version": version, "models": sorted(models, key=lambda item: str(item["id"])), "native": _canonical_capability(native)}


class AgentWorkflow:
    """State bound to one ``PCWRuntime`` workspace, separate from active.json."""

    def __init__(self, runtime: Any):
        self.runtime = runtime
        self.path = runtime.control.root / _STATE_FILE
        self.ledger = TaskLedger(runtime)

    def _guard(self):
        return self.runtime.control.guard()

    def task_begin(self, goal: str, constraints: str, completion: str,
                   checkpoint_policy: str = "required", checkpoint_reason: str = ""):
        return self.ledger.begin(goal, constraints, completion, checkpoint_policy, checkpoint_reason)

    def task_status(self):
        return self.ledger.status()

    def assignment_bind(self, assignment_id: str, executor_session_id: str):
        return self.ledger.bind(assignment_id, executor_session_id)

    def assignment_get(self, assignment_id: str, executor_session_id: str):
        with self._guard():
            state = self._load()
            _, entry = self.ledger.entry(self.ledger.load(), assignment_id)
            revision = (state.get("environment") or {}).get("environment_revision")
            if self._map_status(state) != "current" or entry["environment_revision"] != revision:
                reason = "Environment changed after preparation; refresh the map and prepare the assignment again"
                handoff = self.ledger.bind(assignment_id, executor_session_id, delivered=True)
                self.ledger.delivery_blocker(assignment_id, reason)
                return {**handoff, "status": "blocked", "reason": reason,
                        "instruction": "Do not execute this assignment. Return this blocker to the primary for save/read and re-preparation."}
            return {**self.ledger.bind(assignment_id, executor_session_id, delivered=True), "status": "ready"}

    def assignment_cancel(self, assignment_id: str, reason: str):
        return self.ledger.cancel(assignment_id, reason)

    def result_target(self, assignment_id, executor_session_id):
        return self.ledger.result_target(assignment_id, executor_session_id)

    def note_saved(self, assignment_id, material):
        return self.ledger.note_saved(assignment_id, material)

    def note_read(self, assignment_id, material):
        return self.ledger.note_read(assignment_id, material)

    def _load(self) -> dict[str, object]:
        self.runtime.control.safe(self.path)
        if not self.path.exists():
            legacy = Path(self.runtime.state) / _STATE_FILE
            self.runtime._assert_safe(legacy)
            if legacy.is_file():
                state = json.loads(legacy.read_text(encoding="utf-8"))
                if state.get("schema_version") != 1:
                    raise WorkflowError("Stored legacy workflow state has an unsupported schema")
                self.runtime.control.write(self.path, json.dumps(state) + "\n")
                return state
            return {"schema_version": 1, "environment": None, "tools_map": None}
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkflowError("Stored agent workflow state is unreadable") from exc
        if not isinstance(state, dict) or state.get("schema_version") != 1:
            raise WorkflowError("Stored agent workflow state has an unsupported schema")
        if set(state) - {"schema_version", "environment", "tools_map", "state_revision"}:
            raise WorkflowError("Stored agent workflow state has unsupported fields")
        return state

    def _store(self, state: dict[str, object]) -> dict[str, object]:
        persisted = dict(state)
        persisted["state_revision"] = _revision({key: value for key, value in persisted.items() if key != "state_revision"})
        self.runtime.control.write(self.path, json.dumps(persisted, ensure_ascii=False, indent=2) + "\n")
        return persisted

    @staticmethod
    def _map_status(state: dict[str, object]) -> str:
        environment = state.get("environment")
        tools_map = state.get("tools_map")
        if not isinstance(environment, dict):
            return "absent"
        if not isinstance(tools_map, dict):
            return "absent"
        if tools_map.get("environment_revision") != environment.get("environment_revision"):
            return "refresh_required"
        return "current"

    def environment_get(self) -> dict[str, object]:
        with self._guard():
            state = self._load()
            environment = state.get("environment")
            return {
                "status": "absent" if not isinstance(environment, dict) else "current",
                "environment": environment,
                "environment_revision": environment.get("environment_revision") if isinstance(environment, dict) else None,
                "tools_map_status": self._map_status(state),
                "state_revision": state.get("state_revision"),
            }

    def environment_check(self, environment_snapshot: EnvironmentSnapshot) -> dict[str, object]:
        snapshot = normalize_environment_snapshot(environment_snapshot)
        environment_revision = _revision(snapshot)
        with self._guard():
            state = self._load()
            previous = state.get("environment")
            changed = not isinstance(previous, dict) or previous.get("environment_revision") != environment_revision
            if changed:
                state["environment"] = {
                    "snapshot": snapshot,
                    "environment_revision": environment_revision,
                    "checked_at": _now(),
                }
                state = self._store(state)
            environment = state["environment"]
            return {
                "status": "updated" if changed else "current",
                "environment": environment,
                "environment_revision": environment_revision,
                "tools_map_status": self._map_status(state),
                "state_revision": state.get("state_revision"),
                "reason": "The environment snapshot changed; publish a map for this revision." if changed else None,
                "action": "publish_tools_map" if self._map_status(state) != "current" else None,
            }

    def tools_map_get(self) -> dict[str, object]:
        with self._guard():
            state = self._load()
            return {
                "status": self._map_status(state),
                "environment_revision": (state.get("environment") or {}).get("environment_revision") if isinstance(state.get("environment"), dict) else None,
                "tools_map": state.get("tools_map"),
                "state_revision": state.get("state_revision"),
                "reason": "Check the actual environment and publish a tools map." if self._map_status(state) == "absent" else ("Refresh the map for the current environment revision." if self._map_status(state) == "refresh_required" else None),
                "action": "environment_check" if not isinstance(state.get("environment"), dict) else ("publish_tools_map" if self._map_status(state) != "current" else None),
            }

    def _normalize_profiles(self, profiles: object, snapshot: dict[str, object]) -> list[dict[str, object]]:
        if not isinstance(profiles, list) or not profiles:
            raise WorkflowError("profiles must be a non-empty list")
        available = {str(model["id"]): model for model in snapshot["models"]}  # type: ignore[index]
        normalized: list[dict[str, object]] = []
        ids = set()
        for index, value in enumerate(profiles):
            profile = _object(value, f"profiles[{index}]")
            required = {"id", "model", "reasoning", "roles", "suitable_when"}
            if set(profile) != required:
                raise WorkflowError(f"profiles[{index}] must contain exactly id, model, reasoning, roles and suitable_when")
            ident = _string(profile["id"], f"profiles[{index}].id")
            if ident in ids:
                raise WorkflowError("profiles contains duplicate id: " + ident)
            ids.add(ident)
            model_name = _string(profile["model"], f"profiles[{index}].model")
            if model_name not in available:
                raise WorkflowError(f"profiles[{index}].model is unavailable in the current environment: {model_name}")
            selected = _object(profile["reasoning"], f"profiles[{index}].reasoning")
            supported = available[model_name]["reasoning"]
            if not isinstance(supported, dict):
                raise WorkflowError("Stored environment has invalid reasoning data")
            for parameter, selected_value in selected.items():
                _json_value(selected_value, f"profiles[{index}].reasoning.{parameter}")
                if parameter not in supported:
                    raise WorkflowError(f"profiles[{index}].reasoning.{parameter} is not supported by {model_name}")
                if not any(_same_json(selected_value, candidate) for candidate in supported[parameter]):
                    raise WorkflowError(f"profiles[{index}].reasoning.{parameter} value is unavailable for {model_name}")
            missing_parameters = set(supported) - set(selected)
            if missing_parameters:
                raise WorkflowError(
                    f"profiles[{index}].reasoning must explicitly select every supported parameter for {model_name}: "
                    + ", ".join(sorted(missing_parameters)))
            normalized.append({"id": ident, "model": model_name, "reasoning": dict(selected),
                               "roles": _string_list(profile["roles"], f"profiles[{index}].roles"),
                               "suitable_when": _string_list(profile["suitable_when"], f"profiles[{index}].suitable_when")})
        return sorted(normalized, key=lambda item: str(item["id"]))

    def tools_map_publish(self, expected_environment_revision: str, profiles: list[ToolsMapProfile]) -> dict[str, object]:
        expected = _string(expected_environment_revision, "expected_environment_revision")
        with self._guard():
            state = self._load()
            environment = state.get("environment")
            if not isinstance(environment, dict):
                return {"status": "rejected", "reason": "No actual environment snapshot is recorded.", "action": "environment_check", "environment_revision": None}
            actual = environment.get("environment_revision")
            if expected != actual:
                return {"status": "rejected", "reason": "expected_environment_revision is stale.", "action": "environment_check", "environment_revision": actual}
            snapshot = environment.get("snapshot")
            if not isinstance(snapshot, dict):
                raise WorkflowError("Stored environment snapshot is invalid")
            try:
                normalized = self._normalize_profiles(profiles, snapshot)
            except WorkflowError as exc:
                return {"status": "rejected", "reason": str(exc), "action": "publish_tools_map", "environment_revision": actual}
            state["tools_map"] = {"environment_revision": actual, "profiles": normalized, "published_at": _now()}
            state = self._store(state)
            return {"status": "published", "environment_revision": actual, "tools_map": state["tools_map"], "state_revision": state["state_revision"]}

    @staticmethod
    def _requirements(action: str) -> str:
        reference = Path(__file__).resolve().parents[1] / "skills" / "pcw" / "references" / "action-requirements.md"
        if not reference.is_file():
            return ""
        text = reference.read_text(encoding="utf-8")
        match = re.search(rf"(?ms)^## {re.escape(action)}\s*$\n(.*?)(?=^## |\Z)", text)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _requirements_paths(action: str) -> tuple[str, str]:
        reference = (Path(__file__).resolve().parents[1] / "skills" / "pcw" / "references" /
                     "action-requirements.md").resolve()
        return f"{reference}#{action}", str(reference.parent)

    def _saved_result(self, coordinate: object, label: str) -> tuple[dict[str, object] | None, list[dict[str, str]]]:
        if not isinstance(coordinate, dict):
            return None, [{"field": label, "reason": "A saved result coordinate is required.", "action": "save_subagent_result"}]
        name = coordinate.get("material_name")
        if not isinstance(name, str) or not _NAME.fullmatch(name) or name.startswith(".") or ".." in name.split("/"):
            return None, [{"field": f"{label}.material_name", "reason": "A safe Markdown material name is required.", "action": "save_subagent_result"}]
        material = getattr(self.runtime, "materials", {}).get(name)
        if material is None:
            assignment_id = coordinate.get("assignment_id")
            if isinstance(assignment_id, str):
                try:
                    _, entry = self.ledger.entry(self.ledger.load(), assignment_id)
                except ValueError:
                    entry = {}
                if (entry.get("retired_after_processing") and entry.get("processed_at") and
                        entry.get("return_id") == name and
                        entry.get("executor_session_id") == coordinate.get("executor_session_id") and
                        entry.get("saved_revision") == entry.get("read_revision")):
                    return {"material_name": name, "executor_session_id": entry["executor_session_id"],
                            "saved_at": entry["saved_at"], "assignment_id": assignment_id,
                            "status": "read_and_processed_before_explicit_removal"}, []
            return None, [{"field": f"{label}.material_name", "reason": "The declared saved result does not exist in this workspace.", "action": "save_subagent_result"}]
        metadata = material.metadata
        saved_at = metadata.get("saved_at")
        actual_session = metadata.get("executor_session_id")
        missing: list[dict[str, str]] = []
        if not isinstance(saved_at, str) or not saved_at:
            missing.append({"field": f"{label}.saved_at", "reason": "The material is not a confirmed saved subagent result.", "action": "save_subagent_result"})
        else:
            try:
                parsed_saved_at = datetime.fromisoformat(saved_at.replace("Z", "+00:00"))
            except ValueError:
                parsed_saved_at = None
            if parsed_saved_at is None or parsed_saved_at.tzinfo is None or parsed_saved_at.utcoffset() != timezone.utc.utcoffset(parsed_saved_at):
                missing.append({"field": f"{label}.saved_at", "reason": "The saved result timestamp must be a valid ISO-8601 UTC time with a zone.", "action": "save_subagent_result"})
        if not isinstance(actual_session, str) or not actual_session:
            missing.append({"field": f"{label}.executor_session_id", "reason": "The material has no executor session metadata.", "action": "save_subagent_result"})
        supplied_session = coordinate.get("executor_session_id")
        if not isinstance(supplied_session, str) or not supplied_session:
            missing.append({"field": f"{label}.executor_session_id", "reason": "The expected executor session ID is required to verify this saved result.", "action": "read_saved_result"})
        elif supplied_session != actual_session:
            missing.append({"field": f"{label}.executor_session_id", "reason": "The declared executor session does not match the saved result.", "action": "read_saved_result"})
        if missing:
            return None, missing
        return {"material_name": name, "executor_session_id": actual_session, "saved_at": saved_at}, []

    @staticmethod
    def _assignment(value: object) -> tuple[dict[str, object] | None, list[dict[str, str]]]:
        if not isinstance(value, dict):
            return None, [{"field": "context.assignment", "reason": "A structured assignment is required before a native launch.", "action": "prepare_assignment"}]
        required = {"goal", "expected_result", "boundaries", "context", "constraints", "acceptance_criteria", "knowledge_to_return", "profile", "selection_reason"}
        missing: list[dict[str, str]] = []
        normalized: dict[str, object] = {}
        for field in ("goal", "expected_result", "boundaries", "knowledge_to_return", "profile", "selection_reason"):
            try:
                normalized[field] = _string(value.get(field), f"context.assignment.{field}")
            except WorkflowError as exc:
                missing.append({"field": f"context.assignment.{field}", "reason": str(exc), "action": "prepare_assignment"})
        for field in ("acceptance_criteria",):
            try:
                normalized[field] = _string_list(value.get(field), f"context.assignment.{field}")
            except WorkflowError as exc:
                missing.append({"field": f"context.assignment.{field}", "reason": str(exc), "action": "prepare_assignment"})
        constraints = value.get("constraints")
        if not isinstance(constraints, list) or any(not isinstance(item, str) or not item.strip() for item in constraints):
            missing.append({"field": "context.assignment.constraints", "reason": "constraints must be a list of non-empty strings; use [] to declare no constraints.", "action": "prepare_assignment"})
        else:
            normalized["constraints"] = [item.strip() for item in constraints]
        supplied_context = value.get("context")
        if not isinstance(supplied_context, dict):
            missing.append({"field": "context.assignment.context", "reason": "context must contain summary and material_ids.", "action": "prepare_assignment"})
        else:
            try:
                summary = _string(supplied_context.get("summary"), "context.assignment.context.summary")
            except WorkflowError as exc:
                missing.append({"field": "context.assignment.context.summary", "reason": str(exc), "action": "prepare_assignment"})
                summary = None
            material_ids = supplied_context.get("material_ids")
            if not isinstance(material_ids, list) or any(not isinstance(item, str) or not item for item in material_ids):
                missing.append({"field": "context.assignment.context.material_ids", "reason": "material_ids must be a list of exact material filename IDs; [] is allowed for empty knowledge.", "action": "prepare_assignment"})
            elif len(set(material_ids)) != len(material_ids):
                missing.append({"field": "context.assignment.context.material_ids", "reason": "material_ids must not contain duplicates.", "action": "prepare_assignment"})
            elif summary is not None:
                normalized["context"] = {"summary": summary, "material_ids": material_ids}
            extras_context = set(supplied_context) - {"summary", "material_ids"}
            if extras_context:
                missing.append({"field": "context.assignment.context", "reason": "Unknown context fields: " + ", ".join(sorted(extras_context)), "action": "prepare_assignment"})
        purpose = value.get("purpose", "work")
        if purpose not in {"work", "recovery"}:
            missing.append({"field": "context.assignment.purpose", "reason": "purpose must be work or recovery", "action": "prepare_assignment"})
        else:
            normalized["purpose"] = purpose
        extras = set(value) - required - {"launch_parameters", "purpose"}
        if extras:
            missing.append({"field": "context.assignment", "reason": "Unknown assignment fields: " + ", ".join(sorted(extras)), "action": "prepare_assignment"})
        if "launch_parameters" in value:
            if not isinstance(value["launch_parameters"], dict):
                missing.append({"field": "context.assignment.launch_parameters", "reason": "launch_parameters must be an object.", "action": "prepare_assignment"})
            else:
                normalized["launch_parameters"] = value["launch_parameters"]
        return (normalized if not missing else None), missing

    @staticmethod
    def _launch_parameters(value: object, profile: dict[str, object], state: dict[str, object]) -> list[dict[str, str]]:
        if value is None:
            return []
        if not isinstance(value, dict):
            return [{"field": "context.assignment.launch_parameters", "reason": "launch_parameters must be an object.", "action": "prepare_assignment"}]
        environment = state.get("environment")
        tools_map = state.get("tools_map")
        if not isinstance(environment, dict) or not isinstance(tools_map, dict):
            return [{"field": "context.assignment.launch_parameters", "reason": "Current environment and tools map are required to validate launch parameters.", "action": "environment_check"}]
        snapshot = environment.get("snapshot")
        if not isinstance(snapshot, dict):
            return [{"field": "context.assignment.launch_parameters", "reason": "The stored environment snapshot is invalid.", "action": "environment_check"}]
        model = next((item for item in snapshot.get("models", []) if item.get("id") == profile.get("model")), None)
        if not isinstance(model, dict):
            return [{"field": "context.assignment.launch_parameters", "reason": "The profile model is absent from the current environment.", "action": "publish_tools_map"}]
        constraints: dict[str, object] = {}
        native = snapshot.get("native")
        if isinstance(native, dict) and isinstance(native.get("launch_constraints"), dict):
            constraints.update(native["launch_constraints"])
        if isinstance(model.get("launch_constraints"), dict):
            constraints.update(model["launch_constraints"])
        missing: list[dict[str, str]] = []
        for key, selected in value.items():
            try:
                _json_value(selected, f"context.assignment.launch_parameters.{key}")
            except WorkflowError as exc:
                missing.append({"field": f"context.assignment.launch_parameters.{key}", "reason": str(exc), "action": "prepare_assignment"})
                continue
            if key not in constraints:
                missing.append({"field": f"context.assignment.launch_parameters.{key}", "reason": "The parameter is not declared by current native launch constraints and cannot be confirmed.", "action": "environment_check"})
                continue
            allowed = constraints[key]
            allowed_values = allowed if isinstance(allowed, list) else [allowed]
            if not any(_same_json(selected, candidate) for candidate in allowed_values):
                missing.append({"field": f"context.assignment.launch_parameters.{key}", "reason": "The selected parameter value is unavailable in current native launch constraints.", "action": "environment_check"})
        return missing

    def _checks_declaration(self, value: object, *, field: str, none_status: str,
                            require_scope: bool, block_none: bool) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
        if not isinstance(value, dict):
            return [], [{"field": field, "reason": "A checks declaration is required; omitted data does not mean no check is due or assigned.", "action": "declare_checks"}]
        status = value.get("status")
        base_fields = {"status", "reason", "checks"}
        if require_scope:
            base_fields.add("scope")
        extras = set(value) - base_fields
        missing: list[dict[str, str]] = []
        prerequisites: list[dict[str, object]] = []
        if extras:
            missing.append({"field": field, "reason": "Unknown checks declaration fields: " + ", ".join(sorted(extras)), "action": "declare_checks"})
        if require_scope:
            try:
                scope = _string(value.get("scope"), f"{field}.scope")
            except WorkflowError as exc:
                missing.append({"field": f"{field}.scope", "reason": str(exc), "action": "declare_checks"})
            else:
                prerequisites.append({"field": f"{field}.scope", "status": "declared", "scope": scope})
        if status == none_status:
            try:
                reason = _string(value.get("reason"), f"{field}.reason")
            except WorkflowError as exc:
                missing.append({"field": f"{field}.reason", "reason": str(exc), "action": "declare_checks"})
                reason = None
            if value.get("checks") not in (None, []):
                missing.append({"field": f"{field}.checks", "reason": f"{none_status} cannot include result references.", "action": "declare_checks"})
            if block_none:
                missing.append({"field": f"{field}.status", "reason": "A planned or mismatch-triggered factual check is declared due and needs a saved result reference.", "action": "assign_factual_check"})
            elif reason is not None:
                prerequisites.append({"field": field, "status": "declared", "checks_status": none_status, "reason": reason})
            return prerequisites, missing
        if status != "assigned":
            missing.append({"field": f"{field}.status", "reason": f"status must be {none_status!r} or 'assigned'.", "action": "declare_checks"})
            return prerequisites, missing
        if "reason" in value:
            missing.append({"field": f"{field}.reason", "reason": "reason is only valid when no check is due or assigned.", "action": "declare_checks"})
        checks = value.get("checks")
        if not isinstance(checks, list) or not checks:
            missing.append({"field": f"{field}.checks", "reason": "Assigned checks require at least one saved result coordinate.", "action": "save_subagent_result"})
            return prerequisites, missing
        for index, check in enumerate(checks):
            result, result_missing = self._saved_result(check, f"{field}.checks[{index}]")
            missing.extend(result_missing)
            if result is not None:
                prerequisites.append({"field": f"{field}.checks[{index}]", "status": "verified", "result": result})
        return prerequisites, missing

    def action_requirements(self, action: ActionName, context: ActionContext | None = None) -> dict[str, object]:
        if action not in _ACTION_NAMES:
            raise WorkflowError("action must be one of " + ", ".join(sorted(_ACTION_NAMES)))
        if context is not None and not isinstance(context, dict):
            raise WorkflowError("context must be an object when supplied")
        context = context or {}
        requirements = self._requirements(action)
        requirements_source, references_root = self._requirements_paths(action)
        if requirements:
            requirements = "Relative reference links resolve through references_root.\n\n" + requirements
        prerequisites: list[dict[str, object]] = []
        missing: list[dict[str, str]] = []
        handoff = None
        if not requirements:
            missing.append({"field": "requirements", "reason": "The packaged action-requirements section is unavailable.", "action": "repair_plugin"})
        with self._guard():
            state = self._load()
            map_status = self._map_status(state)
            allowed_context = {
                "prepare_assignment": {"assignment", "continuation_of"},
                "process_result": {"result", "assessment"},
                "transition": {"checks_due", "mismatch_needs_attention", "planned_checks_due"},
                "finish": {"acceptance_checks", "mismatch_needs_attention", "planned_checks_due"},
            }[action]
            extras = set(context) - allowed_context
            if extras:
                missing.append({"field": "context", "reason": "Fields are not valid for this action: " + ", ".join(sorted(extras)), "action": action})
            try:
                self.ledger.active(self.ledger.load())
            except ValueError as exc:
                missing.append({"field": "task", "reason": str(exc), "action": "task_begin"})
            recovery_assignment = (action == "prepare_assignment" and
                                   isinstance(context.get("assignment"), dict) and
                                   context["assignment"].get("purpose") == "recovery")
            if not recovery_assignment:
                try:
                    with self.runtime._guard():
                        pass
                except Exception as exc:
                    missing.append({"field": "runtime", "reason": str(exc),
                                    "action": "recover_workspace" if isinstance(exc, RecoveryRequired) else "prepare_assignment"})
            if action == "prepare_assignment":
                assignment, assignment_missing = self._assignment(context.get("assignment"))
                missing.extend(assignment_missing)
                if map_status != "current":
                    missing.append({"field": "tools_map", "reason": "An up-to-date tools map is required before selecting a launch profile.", "action": "environment_check" if not isinstance(state.get("environment"), dict) else "publish_tools_map"})
                profile_id = assignment.get("profile") if assignment is not None else None
                if isinstance(profile_id, str) and map_status == "current":
                    profiles = (state.get("tools_map") or {}).get("profiles", [])
                    profile = next((item for item in profiles if item.get("id") == profile_id), None)
                    if profile is None:
                        missing.append({
                            "field": "context.assignment.profile",
                            "reason": (
                                "The selected profile is absent from the current tools map. "
                                "Read pcw_tools_map_get, choose an exact published profile ID, "
                                "update context.assignment.profile and context.assignment.selection_reason, "
                                "and resubmit the complete assignment to pcw_action_requirements "
                                "with action prepare_assignment. Do not launch the native agent "
                                "until this action returns ready: true."
                            ),
                            "action": "select_profile",
                        })
                    else:
                        prerequisites.append({"field": "context.assignment.profile", "status": "verified", "profile": profile})
                        assert assignment is not None
                        material_ids = assignment["context"]["material_ids"]  # type: ignore[index]
                        for material_id in material_ids:
                            if material_id not in getattr(self.runtime, "materials", {}):
                                missing.append({"field": "context.assignment.context.material_ids", "reason": f"Referenced knowledge material is unavailable: {material_id}", "action": "read_or_refresh_knowledge"})
                        missing.extend(self._launch_parameters(assignment.get("launch_parameters"), profile, state))
                if not missing:
                    try:
                        handoff = self.ledger.register(assignment, state["environment"]["environment_revision"], context.get("continuation_of"))
                    except ValueError as exc:
                        missing.append({"field": "assignment", "reason": str(exc), "action": "prepare_assignment"})
            if action == "process_result":
                result, result_missing = self._saved_result(context.get("result"), "context.result")
                missing.extend(result_missing)
                if result is not None:
                    prerequisites.append({"field": "context.result", "status": "verified", "result": result})
                coordinate = context.get("result") or {}
                if not isinstance(coordinate, dict) or not coordinate.get("assignment_id"):
                    missing.append({"field": "context.result.assignment_id", "reason": "Identify the registered assignment for this return.", "action": "task_status"})
                elif not missing:
                    try:
                        _, entry = self.ledger.entry(self.ledger.load(), coordinate["assignment_id"])
                        if entry["return_id"] != coordinate.get("material_name") or entry["executor_session_id"] != coordinate.get("executor_session_id"):
                            raise ValueError("Result coordinates do not match the registered assignment")
                        self.ledger.process(coordinate["assignment_id"], context.get("assessment"))
                    except ValueError as exc:
                        missing.append({"field": "context.assessment", "reason": str(exc), "action": "process_result"})
            elif action == "transition":
                for flag in ("mismatch_needs_attention", "planned_checks_due"):
                    if flag in context and type(context[flag]) is not bool:
                        missing.append({"field": f"context.{flag}", "reason": f"{flag} must be a boolean.", "action": "declare_checks"})
                block_none = context.get("mismatch_needs_attention") is True or context.get("planned_checks_due") is True
                checked, checks_missing = self._checks_declaration(context.get("checks_due"), field="context.checks_due", none_status="none_due", require_scope=False, block_none=block_none)
                prerequisites.extend(checked)
                missing.extend(checks_missing)
            elif action == "finish":
                for flag in ("mismatch_needs_attention", "planned_checks_due"):
                    if flag in context and type(context[flag]) is not bool:
                        missing.append({"field": f"context.{flag}", "reason": f"{flag} must be a boolean.", "action": "declare_checks"})
                block_none = context.get("mismatch_needs_attention") is True or context.get("planned_checks_due") is True
                checked, checks_missing = self._checks_declaration(context.get("acceptance_checks"), field="context.acceptance_checks", none_status="none_assigned", require_scope=True, block_none=block_none)
                prerequisites.extend(checked)
                missing.extend(checks_missing)
                try:
                    missing.extend(self.ledger.completion_missing())
                except (ValueError, OSError) as exc:
                    missing.append({"field": "completion", "reason": str(exc), "action": "task_status"})
                if not missing:
                    self.ledger.complete()
        return {"action": action, "requirements": requirements,
                "requirements_source": requirements_source, "references_root": references_root,
                "ready": not missing,
                "prerequisites": prerequisites, "missing": missing,
                "reason": None if not missing else "Required machine-checkable workflow data is missing or does not match saved state.",
                "next_action": None if not missing else missing[0]["action"],
                "handoff": handoff}

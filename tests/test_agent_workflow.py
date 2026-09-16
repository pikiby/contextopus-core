"""Unit coverage for the environment-bound PCW workflow control plane."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "persistent-context-workspace"))

from pcw_runtime.agent_workflow import AgentWorkflow, WorkflowError
from pcw_runtime.control import control_store


class Material:
    def __init__(self, name: str, *, saved_at: str | None = None, session: str | None = None):
        self.id = name
        self.revision = "fixture-revision"
        self.path = "knowledge/" + name
        self.metadata = {}
        if saved_at is not None:
            self.metadata["saved_at"] = saved_at
        if session is not None:
            self.metadata["executor_session_id"] = session


class Runtime:
    def __init__(self, root: Path):
        self.work_root = root
        self.root = root / ".pcw" / "unit"
        self.state = self.root / ".pcw-runtime"
        self.state.mkdir(parents=True)
        self.control = control_store(root, "unit")
        self.materials = {}

    @contextmanager
    def _guard(self):
        yield

    def _assert_safe(self, path):
        assert path.is_relative_to(self.root)

    def _allocate_material_id(self):
        return uuid.uuid4().hex + ".md"

    def durable_state(self):
        return {"files": {}, "paths": {k: v.path for k, v in self.materials.items()}, "pending": [], "unregistered": []}

    def current_get(self):
        return {"goal": "Test", "constraints": "Temporary", "completion": "Done", "step": "Work", "blocker": ""}

    def uncheckpointed(self, paths):
        return []

    def _write(self, path: Path, content: str):
        path.write_text(content, encoding="utf-8")


def snapshot(version="1", models=None):
    return {
        "environment": "example-host",
        "version": version,
        "native": {"launch": {"supports_clean_context": True}},
        "models": models if models is not None else [
            {"id": "researcher", "reasoning": {"depth": ["compact", "thorough"]}, "launch_constraints": {"max_workers": 2}},
            {"id": "plain-worker"},
        ],
    }


def profiles():
    return [
        {"id": "prepared-change", "model": "researcher", "reasoning": {"depth": "compact"},
         "roles": ["implementation"], "suitable_when": ["scope is prepared"]},
        {"id": "split-text", "model": "plain-worker", "reasoning": {},
         "roles": ["search_preparation"], "suitable_when": ["literal source split"]},
    ]


def publish_current(workflow):
    checked = workflow.environment_check(snapshot())
    published = workflow.tools_map_publish(checked["environment_revision"], profiles())
    assert published["status"] == "published"
    return checked


def assignment(**overrides):
    value = {
        "goal": "Investigate the selected source",
        "expected_result": "Return observations",
        "boundaries": "Read only selected source",
        "context": {"summary": "User requested a bounded investigation.", "material_ids": []},
        "constraints": [],
        "acceptance_criteria": ["Observed result is recorded"],
        "knowledge_to_return": "Facts, sources and blocker",
        "profile": "prepared-change",
        "selection_reason": "The map marks this profile suitable for the prepared scope.",
    }
    value.update(overrides)
    return value


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.workflow = AgentWorkflow(Runtime(Path(self.directory.name)))
        self.workflow.task_begin("Test", "Temporary", "Done")

    def test_environment_lifecycle_is_canonical_and_forces_map_refresh(self):
        workflow = self.workflow
        self.assertEqual("absent", workflow.environment_get()["status"])
        checked = workflow.environment_check(snapshot())
        self.assertEqual("updated", checked["status"])
        self.assertEqual("absent", checked["tools_map_status"])
        published = workflow.tools_map_publish(checked["environment_revision"], profiles())
        self.assertEqual("published", published["status"])
        self.assertEqual("current", workflow.tools_map_get()["status"])

        reordered = snapshot(models=[
            {"id": "plain-worker"},
            {"id": "researcher", "reasoning": {"depth": ["thorough", "compact"]}, "launch_constraints": {"max_workers": 2}},
        ])
        same = workflow.environment_check(reordered)
        self.assertEqual("current", same["status"])
        self.assertEqual(checked["environment_revision"], same["environment_revision"])
        self.assertEqual("current", same["tools_map_status"])

        changed = workflow.environment_check(snapshot(version="2"))
        self.assertEqual("updated", changed["status"])
        self.assertEqual("refresh_required", changed["tools_map_status"])
        map_state = workflow.tools_map_get()
        self.assertEqual("refresh_required", map_state["status"])
        self.assertEqual("publish_tools_map", map_state["action"])


    def test_publish_rejects_stale_environment_and_unavailable_profile_capabilities(self):
        workflow = self.workflow
        checked = workflow.environment_check(snapshot())
        stale = workflow.tools_map_publish("sha256:not-current", profiles())
        self.assertEqual({
            "status": "rejected", "reason": "expected_environment_revision is stale.",
            "action": "environment_check", "environment_revision": checked["environment_revision"],
        }, stale)
        bad_model = workflow.tools_map_publish(checked["environment_revision"], [{
            "id": "bad", "model": "not-present", "reasoning": {}, "roles": ["research"], "suitable_when": ["investigation"],
        }])
        self.assertEqual("rejected", bad_model["status"])
        self.assertIn("unavailable", bad_model["reason"])
        bad_reasoning = workflow.tools_map_publish(checked["environment_revision"], [{
            "id": "bad", "model": "plain-worker", "reasoning": {"depth": "compact"}, "roles": ["research"], "suitable_when": ["investigation"],
        }])
        self.assertEqual("rejected", bad_reasoning["status"])
        self.assertIn("not supported", bad_reasoning["reason"])
        implicit_reasoning = workflow.tools_map_publish(checked["environment_revision"], [{
            "id": "bad", "model": "researcher", "reasoning": {}, "roles": ["research"], "suitable_when": ["investigation"],
        }])
        self.assertEqual("rejected", implicit_reasoning["status"])
        self.assertIn("explicitly select", implicit_reasoning["reason"])
        boolean_reasoning = workflow.tools_map_publish(checked["environment_revision"], [{
            "id": "bad", "model": "researcher", "reasoning": {"depth": True}, "roles": ["research"], "suitable_when": ["investigation"],
        }])
        self.assertEqual("rejected", boolean_reasoning["status"])
        self.assertIn("unavailable", boolean_reasoning["reason"])
        numeric = workflow.environment_check(snapshot(models=[{"id": "number", "reasoning": {"mode": [1]}}]))
        true_is_not_one = workflow.tools_map_publish(numeric["environment_revision"], [{
            "id": "bad", "model": "number", "reasoning": {"mode": True}, "roles": ["research"], "suitable_when": ["investigation"],
        }])
        self.assertEqual("rejected", true_is_not_one["status"])
        self.assertIn("unavailable", true_is_not_one["reason"])


    def test_action_requirements_refuse_missing_data_then_verify_all_four_phases(self):
        workflow = self.workflow
        missing_prepare = workflow.action_requirements("prepare_assignment")
        self.assertTrue(missing_prepare["requirements"])
        self.assertFalse(missing_prepare["ready"])
        self.assertTrue({item["field"] for item in missing_prepare["missing"]} >= {"tools_map", "context.assignment"})

        publish_current(workflow)
        ready = workflow.action_requirements("prepare_assignment", {"assignment": assignment()})
        self.assertTrue(ready["ready"])
        aid = ready["handoff"]["assignment_id"]
        result_id = ready["handoff"]["return_id"]
        workflow.assignment_bind(aid, "worker-1")
        workflow.assignment_get(aid, "worker-1")
        empty_scope = workflow.action_requirements("prepare_assignment", {"assignment": assignment(goal="")})
        self.assertFalse(empty_scope["ready"])
        extra_field = workflow.action_requirements("prepare_assignment", {"assignment": assignment(extra=object())})
        self.assertFalse(extra_field["ready"])
        legacy_untyped = workflow.action_requirements("prepare_assignment", {"assignment_scope": []})
        self.assertFalse(legacy_untyped["ready"])
        unknown = workflow.action_requirements("prepare_assignment", {"assignment": assignment(profile="gone")})
        self.assertFalse(unknown["ready"])
        self.assertEqual("select_profile", unknown["missing"][0]["action"])

        process_missing = workflow.action_requirements("process_result", {})
        self.assertFalse(process_missing["ready"])
        self.assertEqual("save_subagent_result", process_missing["missing"][0]["action"])
        workflow.runtime.materials[result_id] = Material(result_id, saved_at="2026-01-02T03:04:05Z", session="worker-1")
        material_only = workflow.action_requirements("process_result", {"result": {"material_name": result_id}})
        self.assertFalse(material_only["ready"])
        mismatched = workflow.action_requirements("process_result", {"result": {"material_name": result_id, "executor_session_id": "other"}})
        self.assertFalse(mismatched["ready"])
        workflow.note_saved(aid, workflow.runtime.materials[result_id])
        workflow.note_read(aid, workflow.runtime.materials[result_id])
        process = workflow.action_requirements("process_result", {"result": {"assignment_id": aid, "material_name": result_id, "executor_session_id": "worker-1"}, "assessment": {"status": "accepted", "reason": "Fixture observed"}})
        self.assertTrue(process["ready"])

        transition_missing = workflow.action_requirements("transition", {})
        self.assertFalse(transition_missing["ready"])
        transition_none_due = workflow.action_requirements("transition", {"checks_due": {"status": "none_due", "reason": "No planned stage or mismatch requires a check."}})
        self.assertTrue(transition_none_due["ready"])
        transition_blocked = workflow.action_requirements("transition", {"mismatch_needs_attention": True, "checks_due": {"status": "none_due", "reason": "Not needed"}})
        self.assertFalse(transition_blocked["ready"])
        transition_verified = workflow.action_requirements("transition", {"checks_due": {"status": "assigned", "checks": [{"material_name": result_id, "executor_session_id": "worker-1"}]}})
        self.assertTrue(transition_verified["ready"])

        finish_missing = workflow.action_requirements("finish", {})
        self.assertFalse(finish_missing["ready"])
        finish_none = workflow.action_requirements("finish", {"acceptance_checks": {"status": "none_assigned", "scope": "Whole requested task", "reason": "No factual check was assigned."}})
        self.assertTrue(finish_none["ready"])
        finish_material_only = workflow.action_requirements("finish", {"acceptance_checks": {"status": "assigned", "scope": "Whole requested task", "checks": [{"material_name": result_id}]}})
        self.assertFalse(finish_material_only["ready"])
        finish_verified = workflow.action_requirements("finish", {"acceptance_checks": {"status": "assigned", "scope": "Whole requested task", "checks": [{"material_name": result_id, "executor_session_id": "worker-1"}]}})
        self.assertTrue(finish_verified["ready"])
        self.assertEqual("2026-01-02T03:04:05Z", finish_verified["prerequisites"][1]["result"]["saved_at"])

    def test_unknown_profile_requires_exact_map_selection_and_full_revalidation(self):
        workflow = self.workflow
        publish_current(workflow)
        proposed = assignment(profile="gone")
        rejected = workflow.action_requirements("prepare_assignment", {"assignment": proposed})
        self.assertFalse(rejected["ready"])
        self.assertEqual("select_profile", rejected["next_action"])
        self.assertEqual(1, len(rejected["missing"]))
        missing = rejected["missing"][0]
        self.assertEqual("context.assignment.profile", missing["field"])
        self.assertEqual("select_profile", missing["action"])
        for instruction in ("pcw_tools_map_get", "exact published profile ID",
                            "context.assignment.profile", "context.assignment.selection_reason",
                            "complete assignment", "pcw_action_requirements", "prepare_assignment"):
            with self.subTest(instruction=instruction):
                self.assertIn(instruction, missing["reason"])
        self.assertRegex(missing["reason"], r"Do not launch.*until.*ready:\s*true")

        current_map = workflow.tools_map_get()
        selected = next(profile for profile in current_map["tools_map"]["profiles"]
                        if "implementation" in profile["roles"])
        proposed["profile"] = selected["id"]
        proposed["selection_reason"] = "The published implementation profile fits this prepared scope."
        corrected = workflow.action_requirements("prepare_assignment", {"assignment": proposed})
        self.assertTrue(corrected["ready"])
        self.assertEqual([], corrected["missing"])
        self.assertIsNone(corrected["next_action"])
        self.assertEqual(selected, corrected["prerequisites"][0]["profile"])

    def test_prepare_instructions_include_correction_loop_when_prerequisites_are_missing(self):
        workflow = self.workflow
        absent = workflow.action_requirements("prepare_assignment")
        self.assertFalse(absent["ready"])
        self.assertEqual({"context.assignment", "tools_map"},
                         {item["field"] for item in absent["missing"]})
        self.assertTrue(absent["requirements_source"].endswith("action-requirements.md#prepare_assignment"))
        instructions = absent["requirements"].replace("`", "")
        self.assertIn("complete assignment", instructions)
        self.assertIn("exact published profile ID", instructions)
        self.assertRegex(instructions, r"ready.*false.*repeat.*corrected context")
        self.assertRegex(instructions, r"Launch only after.*ready:\s*true")

        publish_current(workflow)
        no_assignment = workflow.action_requirements("prepare_assignment")
        self.assertFalse(no_assignment["ready"])
        self.assertEqual({"context.assignment"}, {item["field"] for item in no_assignment["missing"]})
        self.assertEqual(absent["requirements"], no_assignment["requirements"])

    def test_missing_map_repair_uses_environment_presence(self):
        workflow = self.workflow
        for environment_present, expected_action in ((False, "environment_check"),
                                                     (True, "publish_tools_map")):
            with self.subTest(environment_present=environment_present):
                if environment_present:
                    workflow.environment_check(snapshot())
                current_map = workflow.tools_map_get()
                self.assertEqual("absent", current_map["status"])
                self.assertEqual(expected_action, current_map["action"])
                result = workflow.action_requirements("prepare_assignment", {"assignment": assignment()})
                self.assertFalse(result["ready"])
                self.assertTrue(result["requirements"])
                self.assertEqual(expected_action, result["next_action"])
                self.assertEqual("tools_map", result["missing"][0]["field"])
                self.assertEqual(expected_action, result["missing"][0]["action"])

    def test_timestamp_and_launch_parameter_diagnostics_are_strict(self):
        workflow = self.workflow
        publish_current(workflow)
        workflow.runtime.materials["bad-time.md"] = Material("bad-time.md", saved_at="not-a-utc-time", session="worker-1")
        bad_time = workflow.action_requirements("process_result", {"result": {"material_name": "bad-time.md", "executor_session_id": "worker-1"}})
        self.assertFalse(bad_time["ready"])
        self.assertIn("ISO-8601 UTC", bad_time["missing"][0]["reason"])
        unknown_launch = workflow.action_requirements("prepare_assignment", {"assignment": assignment(launch_parameters={"not_declared": True})})
        self.assertFalse(unknown_launch["ready"])
        self.assertIn("cannot be confirmed", unknown_launch["missing"][-1]["reason"])
        non_json_launch = workflow.action_requirements("prepare_assignment", {"assignment": assignment(launch_parameters={"mechanism": object()})})
        self.assertFalse(non_json_launch["ready"])
        self.assertIn("must contain JSON values", non_json_launch["missing"][-1]["reason"])
        nan_launch = workflow.action_requirements("prepare_assignment", {"assignment": assignment(launch_parameters={"mechanism": float("nan")})})
        self.assertFalse(nan_launch["ready"])
        self.assertIn("must contain JSON values", nan_launch["missing"][-1]["reason"])
        supported_launch = workflow.action_requirements("prepare_assignment", {"assignment": assignment(launch_parameters={"max_workers": 2})})
        self.assertTrue(supported_launch["ready"])


    def test_invalid_actions_and_snapshots_are_rejected(self):
        workflow = self.workflow
        with self.assertRaisesRegex(WorkflowError, "action must be one of"):
            workflow.action_requirements("dispatch", {})
        with self.assertRaisesRegex(WorkflowError, "missing native"):
            workflow.environment_check({"environment": "x", "version": "1", "models": []})
        with self.assertRaisesRegex(WorkflowError, "duplicate model"):
            workflow.environment_check(snapshot(models=[{"id": "same"}, {"id": "same"}]))
        # State is a real JSON asset, separate from the embedding active.json.
        publish_current(workflow)
        state = workflow.path
        document = json.loads(state.read_text())
        self.assertEqual(1, document["schema_version"])
        self.assertTrue(document["environment"]["environment_revision"].startswith("sha256:"))

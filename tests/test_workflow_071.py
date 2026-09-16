"""Mechanical workflow guards for compact commands and multi-material returns."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_agent_workflow import Runtime, assignment, profiles, publish_current, snapshot
from pcw_runtime.agent_workflow import AgentWorkflow


class Body:
    def __init__(self, ident, content, saved_at="2026-01-02T03:04:05Z", session="worker"):
        self.id = ident
        self.path = "knowledge/" + ident
        self.content = content
        self.revision = hashlib.sha256(content.encode()).hexdigest()
        self.metadata = {"saved_at": saved_at, "executor_session_id": session}


class Workflow071Tests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.runtime = Runtime(Path(directory.name))
        self.flow = AgentWorkflow(self.runtime)
        self.flow.task_begin("Test", "Temporary", "Done")
        publish_current(self.flow)

    def register(self, **kwargs):
        prepared = self.flow.assignment_prepare(assignment(**kwargs))
        self.assertTrue(prepared["ready"], prepared)
        ident = prepared["handoff"]["assignment_id"]
        self.flow.assignment_bind(ident, "worker")
        return ident

    def save(self, assignment_id, bodies):
        targets = self.flow.ledger.reserve_result_blocks(assignment_id, "worker", bodies)
        materials = []
        for target, body in zip(targets, bodies):
            material = Body(target["material_id"], body, target["saved_at"])
            self.runtime.materials[material.id] = material
            self.flow.note_saved(assignment_id, material)
            materials.append(material)
        return materials

    def assess(self, assignment_id, **extra):
        return self.flow.result_assess(assignment_id, {"status": "accepted", "reason": "Observed", **extra})

    def test_operational_commands_do_not_read_or_repeat_rules(self):
        with patch.object(self.flow, "_requirements", side_effect=AssertionError("Rules read by mutation")):
            prepared = self.flow.assignment_prepare(assignment())
        self.assertTrue(prepared["ready"])
        self.assertNotIn("requirements", prepared)
        self.assertNotIn("assignment", prepared["handoff"])
        bound = self.flow.assignment_bind(prepared["handoff"]["assignment_id"], "worker")
        self.assertNotIn("launch_message", bound)
        self.assertNotIn("assignment", bound)
        before = self.flow.ledger.path.read_bytes()
        rules = self.flow.rules_get("finish")
        self.assertTrue(rules["requirements"])
        self.assertEqual(before, self.flow.ledger.path.read_bytes())

    def test_startup_reuses_map_and_supplies_resume_state_without_mutation(self):
        ident = self.register()
        before = (self.flow.path.read_bytes(), self.flow.ledger.path.read_bytes())
        startup = self.flow.startup()
        self.assertEqual("current", startup["tools_map_status"])
        self.assertEqual(profiles(), startup["profiles"])
        self.assertEqual(ident, startup["assignments"][0]["id"])
        self.assertEqual("worker", startup["assignments"][0]["executor_session_id"])
        self.assertEqual(0, startup["material_count"])
        self.assertEqual("Test", startup["current"]["goal"])
        self.assertEqual(before, (self.flow.path.read_bytes(), self.flow.ledger.path.read_bytes()))
        with patch.object(self.runtime, "durable_state", side_effect=RuntimeError("Unavailable index")):
            recovered = self.flow.startup()
        self.assertEqual("Unavailable index", recovered["recovery"]["reason"])
        self.assertEqual(ident, recovered["assignments"][0]["id"])

    def test_planned_check_is_bound_atomically_and_not_in_worker_packet(self):
        self.flow.task_checks_set([{"id": "acceptance-1", "when": "Finish", "scope": "Requested state",
                                    "criteria": ["Observed"]}], "Requested check")
        prepared = self.flow.assignment_prepare(assignment(purpose="check"), check_id="acceptance-1")
        self.assertTrue(prepared["ready"], prepared)
        ident = prepared["handoff"]["assignment_id"]
        task = self.flow.task_status()["task"]
        self.assertEqual(ident, task["checks_plan"][0]["assignment_id"])
        self.assertNotIn("acceptance-1", prepared["handoff"]["launch_message"])
        self.assertEqual(ident, self.flow.assignment_prepare(assignment(purpose="check"), check_id="acceptance-1")["handoff"]["assignment_id"])
        rejected = self.flow.assignment_prepare(assignment(purpose="check", goal="Other check"), check_id="absent")
        self.assertFalse(rejected["ready"])
        self.assertEqual(1, len(self.flow.task_status()["task"]["assignments"]))

    def test_launch_validation_uses_declared_model_reasoning_native_types(self):
        env = snapshot(models=[{"id": "worker-model", "reasoning": {"effort": ["low", "high"]}}])
        env["native"] = {"agent_types": ["worker", "explorer"], "launch": {"supports_clean_context": True}}
        checked = self.flow.environment_check(env)
        self.flow.tools_map_publish(checked["environment_revision"], [{"id": "prepared-change", "model": "worker-model",
            "reasoning": {"effort": "low"}, "roles": ["work"], "suitable_when": ["Prepared scope"]}])
        params = {"model": "worker-model", "reasoning_effort": "low", "agent_type": "worker", "fork_turns": "none"}
        self.assertTrue(self.flow.assignment_prepare(assignment(launch_parameters=params))["ready"])
        for key, wrong in (("model", "other"), ("reasoning_effort", "high"), ("agent_type", "unknown"), ("fork_turns", "all")):
            self.assertFalse(self.flow.assignment_prepare(assignment(launch_parameters={**params, key: wrong}))["ready"])

    def test_all_reserved_blocks_must_be_saved_and_read(self):
        ident = self.register()
        targets = self.flow.ledger.reserve_result_blocks(ident, "worker", ["A", "B"])
        first = Body(targets[0]["material_id"], "A", targets[0]["saved_at"])
        self.runtime.materials[first.id] = first
        self.flow.note_saved(ident, first)
        self.flow.note_read(ident, first)
        self.assertFalse(self.assess(ident)["ready"])
        second = Body(targets[1]["material_id"], "B", targets[1]["saved_at"])
        self.runtime.materials[second.id] = second
        self.flow.note_saved(ident, second)
        self.assertFalse(self.assess(ident)["ready"])
        self.flow.note_read(ident, second)
        self.assertTrue(self.assess(ident)["ready"])

    def test_read_many_receipts_are_atomic_for_foreign_material(self):
        ident = self.register()
        materials = self.save(ident, ["A", "B"])
        before = self.flow.ledger.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "exact saved return"):
            self.flow.ledger.note_read_many(ident, [materials[0], Body("foreign.md", "Foreign")])
        self.assertEqual(before, self.flow.ledger.path.read_bytes())
        self.assertFalse(self.assess(ident)["ready"])

    def test_reservations_survive_reload_and_conflicts_require_explicit_cas(self):
        ident = self.register()
        materials = self.save(ident, ["A", "B"])
        original_ids = [material.id for material in materials]
        self.flow = AgentWorkflow(self.runtime)
        retry = self.flow.ledger.reserve_result_blocks(ident, "worker", ["A", "B"])
        self.assertEqual(original_ids, [record["material_id"] for record in retry])
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.flow.ledger.reserve_result_blocks(ident, "worker", ["New A", "B"])
        self.flow.ledger.note_read_many(ident, materials)
        self.assertFalse(self.assess(ident)["ready"])
        revisions = [material.revision for material in materials]
        correction = self.flow.ledger.reserve_result_blocks(ident, "worker", ["New A", "B"], revisions)
        corrected = Body(original_ids[0], "New A", correction[0]["saved_at"])
        self.runtime.materials[corrected.id] = corrected
        self.flow.note_saved(ident, corrected)
        self.flow = AgentWorkflow(self.runtime)
        resumed = self.flow.ledger.reserve_result_blocks(ident, "worker", ["New A", "B"], revisions)
        self.assertEqual(original_ids, [record["material_id"] for record in resumed])
        self.flow.note_saved(ident, materials[1])
        self.flow.ledger.note_read_many(ident, [corrected, materials[1]])
        self.assertTrue(self.assess(ident)["ready"])

    def test_resolution_requires_every_known_wrong_body_to_change(self):
        wrong_id = self.register()
        wrong = self.save(wrong_id, ["Wrong A", "Wrong B"])
        self.flow.ledger.note_read_many(wrong_id, wrong)
        flagged = self.assess(wrong_id, status="needs_attention")
        self.assertTrue(flagged["ready"])
        clarification_id = self.register(goal="Check actual state")
        correct = self.save(clarification_id, ["Corrected facts"])
        self.flow.ledger.note_read_many(clarification_id, correct)
        self.assertFalse(self.assess(clarification_id, resolves=[wrong_id])["ready"])
        wrong[0].metadata["links"] = [correct[0].id]
        self.assertFalse(self.assess(clarification_id, resolves=[wrong_id])["ready"])
        self.runtime.materials[wrong[0].id] = Body(wrong[0].id, "Correct A")
        self.assertFalse(self.assess(clarification_id, resolves=[wrong_id])["ready"])
        self.runtime.materials.pop(wrong[1].id)
        self.flow.ledger.note_retired(wrong[1].id)
        self.assertTrue(self.assess(clarification_id, resolves=[wrong_id])["ready"])
        self.assertEqual([], self.flow.ledger.invalidations(wrong[0].id, self.runtime.materials[wrong[0].id].revision))
        self.assertTrue(self.flow.ledger.invalidations(wrong[0].id, wrong[0].revision))

    def test_explicit_affected_materials_do_not_invalidate_unrelated_blocks(self):
        ident = self.register()
        materials = self.save(ident, ["Wrong", "Valid"])
        self.flow.ledger.note_read_many(ident, materials)
        self.assertTrue(self.assess(ident, status="needs_attention", affected_material_ids=[materials[0].id])["ready"])
        self.assertTrue(self.flow.ledger.invalidations(materials[0].id, materials[0].revision))
        self.assertEqual([], self.flow.ledger.invalidations(materials[1].id, materials[1].revision))

    def test_completed_task_allows_exact_retry_but_rejects_changed_blocks(self):
        ident = self.register()
        materials = self.save(ident, ["Accepted body"])
        self.flow.ledger.note_read_many(ident, materials)
        self.assertTrue(self.assess(ident)["ready"])
        self.flow.ledger.complete()
        before = self.flow.ledger.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "completed task"):
            self.flow.ledger.reserve_result_blocks(ident, "worker", ["Changed body"], [materials[0].revision])
        self.assertEqual(before, self.flow.ledger.path.read_bytes())
        retry = self.flow.ledger.reserve_result_blocks(ident, "worker", ["Accepted body"])
        self.assertEqual(materials[0].id, retry[0]["material_id"])

    def test_semantic_batch_sends_numbered_texts_without_source_coordinates(self):
        sources = [Body("a" * 32 + ".md", "A1\nA2\n"), Body("b" * 32 + ".md", "B1\nB2\n")]
        self.runtime.materials = {material.id: material for material in sources}
        self.runtime.prepare = lambda ident: {"revision": self.runtime.materials[ident].revision,
                                              "content": self.runtime.materials[ident].content}
        prepared = self.flow.assignment_prepare(assignment(purpose="semantic_split"), split_sources=[
            {"material_id": material.id, "revision": material.revision} for material in sources])
        self.assertTrue(prepared["ready"], prepared)
        packet = prepared["handoff"]["launch_message"]
        for material in sources:
            self.assertNotIn(material.id, packet)
            self.assertNotIn(material.revision, packet)
        payload = json.loads(packet.split("\n\n", 1)[1])
        self.assertEqual([1, 2], [text["text_number"] for text in payload["source_units"]])
        self.assertEqual("B2\n", payload["source_units"][1]["units"][1]["text"])
        self.assertIsNone(prepared["handoff"]["return_id"])

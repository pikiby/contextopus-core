"""Opt-in actual-model PCW workflow regression.

Set PCW_TEST_NATIVE=1 to make one online Astra model turn. Reasoning defaults
to high and can be set with PCW_NATIVE_REASONING_EFFORT only when the actual
host catalog supports it. This is separate from PCW_TEST_CODEX, which runs
plain host-MCP integration only. When a native workflow submits prepared
knowledge parts, it may invoke the configured cached local Qwen provider;
PCW_TEST_QWEN remains the separate direct embedding assessment.
"""
from __future__ import annotations

import os
import json
import sys
import tempfile
import unittest
from pathlib import Path

from tests.native_workflow_probe import (FaultAfterSavedReturn, MULTISTAGE_NORMALIZE_CLI_SCENARIO,
                                         NativeWorkflowProbe)


@unittest.skipUnless(os.environ.get("PCW_TEST_NATIVE") == "1", "Set PCW_TEST_NATIVE=1 for an actual native workflow")
class NativeWorkflowTests(unittest.TestCase):
    @unittest.skipIf(os.environ.get("PCW_NATIVE_FOLLOWUP") == "1", "Follow-up runs in its separate opt-in test")
    def test_simple_workflow_retains_raw_actual_trace_for_independent_assessment(self):
        evidence = NativeWorkflowProbe().run_scenario()
        self.assertTrue(evidence["fixture_unchanged"], evidence)
        self.assertEqual([], evidence["unexpected_project_paths"], evidence)
        self.assertEqual("raw observed trace; independently assessed separately", evidence["scope"])
        self.assertGreater(evidence["mcp_tool_count"], 0, evidence)

        if evidence["scenario"] == "prepare-context-only":
            self.assertTrue(all(evidence["forbidden_paths_absent"].values()), evidence)
            self.assertTrue(all(evidence["required_knowledge_markers_present"].values()), evidence)
        if evidence["scenario"] == "multistage-normalize-cli":
            self.assertEqual("passed", evidence["fixture_verification"]["status"], evidence)
        if evidence["scenario"] == "mismatch-before-planned":
            self.assertEqual("fixture_precondition_observed", evidence["fixture_verification"]["status"], evidence)
            self.assertTrue(evidence["fixture_verification"]["final_output_absent"], evidence)
        if evidence["scenario"] == "fault-after-saved-return":
            # A missed temporal trigger is an explicitly labelled test
            # limitation; it is never inferred to be a product failure.
            self.assertIn(evidence["fixture_verification"]["status"], {"injected_requires_trace_review", "inconclusive"}, evidence)
        if evidence["scenario"] == "stale-environment-map":
            seed = evidence["controlled_stale_map_seed"]
            self.assertEqual("updated", seed["seed_outcome"]["environment_status"], evidence)
            self.assertEqual("published", seed["seed_outcome"]["published_status"], evidence)

    @unittest.skipUnless(os.environ.get("PCW_NATIVE_FOLLOWUP") == "1",
                         "Set PCW_NATIVE_FOLLOWUP=1 for the separate same-thread clarification turn")
    def test_optional_same_thread_followup_retains_raw_trace(self):
        evidence = NativeWorkflowProbe().run_scenario(followup=True)
        self.assertTrue(evidence["fixture_unchanged"], evidence)
        self.assertEqual([], evidence["unexpected_project_paths"], evidence)
        self.assertIsNotNone(evidence["followup"], evidence)
        self.assertEqual(0, evidence["followup"]["new_subagent_start_count"], evidence)


class FaultCollectorTests(unittest.TestCase):
    """Local collector regressions; they do not simulate a PCW workflow."""

    RAW = "# implementation return\nresult is correct\n"
    MAIN = "main-thread"
    CHILD = "actual-child-thread"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.work = self.root / "work"
        (self.work / "out").mkdir(parents=True)
        (self.work / "out" / "result.json").write_text(
            json.dumps({"release": "R-17", "count": 2}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.observer = FaultAfterSavedReturn(self.root, self.work)
        self.observer.bind_main(self.MAIN)

    def tearDown(self):
        self.temporary.cleanup()

    def event(self, item, *, actor=MAIN):
        return {"method": "item/completed", "emittedAtMs": 1,
                "params": {"threadId": actor, "item": item}}

    def child_start(self, thread):
        self.observer.observe(self.event({"type": "subAgentActivity", "kind": "started",
                                         "agentThreadId": thread}, actor=self.MAIN), 1)

    def child_final(self, thread=CHILD, raw=None):
        self.observer.observe(self.event({"type": "agentMessage", "phase": "final_answer",
                                         "text": raw or self.RAW}, actor=thread), 2)

    @staticmethod
    def result(payload):
        return {"content": [{"type": "text", "text": json.dumps(payload)}]}

    def save(self, *, raw=None, session=CHILD, material="implementation.md"):
        payload = {"id": material, "executor_session_id": session, "revision": "rev-1", "saved_at": "2026-09-15T00:00:00Z"}
        self.observer.observe(self.event({"type": "mcpToolCall", "server": "pcw", "tool": "pcw_save_subagent_result",
                                          "status": "completed", "arguments": {"result": raw or self.RAW, "executor_session_id": session, "material_name": material},
                                          "result": self.result(payload)}), 3)

    def read(self, *, raw=None, session=CHILD, material="implementation.md"):
        payload = {"id": material, "executor_session_id": session, "revision": "rev-1", "saved_at": "2026-09-15T00:00:00Z", "content": raw or self.RAW}
        self.observer.observe(self.event({"type": "mcpToolCall", "server": "pcw", "tool": "pcw_read", "status": "completed",
                                          "arguments": {"material_id": material}, "result": self.result(payload)}), 4)

    def establish_valid_chain(self):
        self.child_start(self.CHILD)
        self.child_final()
        self.save()
        self.read()

    def test_valid_causal_chain_injects_only_after_main_read(self):
        self.establish_valid_chain()
        self.assertEqual("injected", self.observer.state["status"])
        self.assertEqual({"release": "R-17", "count": 3}, json.loads((self.work / "out" / "result.json").read_text(encoding="utf-8")))

    def test_unrelated_save_and_read_do_not_trigger(self):
        self.child_start(self.CHILD)
        self.child_final()
        self.save(raw="unrelated result", material="unrelated.md")
        self.read(raw="unrelated result", material="unrelated.md")
        self.assertEqual("armed", self.observer.state["status"])
        self.save()
        self.read()
        self.assertEqual("injected", self.observer.state["status"])

    def test_wrong_session_or_final_mismatch_is_inconclusive(self):
        self.child_start(self.CHILD)
        self.child_final()
        self.save(session="copied-parent-session")
        self.assertEqual("inconclusive", self.observer.state["status"])
        self.assertEqual("saved_return_does_not_match_only_actual_child_final", self.observer.state["reason"])

    def test_prior_second_child_is_inconclusive(self):
        self.child_start(self.CHILD)
        self.child_start("second-child-thread")
        self.child_final()
        self.save()
        self.assertEqual("inconclusive", self.observer.state["status"])
        self.assertEqual("saved_return_does_not_match_only_actual_child_final", self.observer.state["reason"])

    def test_observer_exception_is_inconclusive(self):
        self.observer._inject = lambda *args: (_ for _ in ()).throw(RuntimeError("collector failure"))
        self.establish_valid_chain()
        self.assertEqual("inconclusive", self.observer.state["status"])
        self.assertIn("observer_exception", self.observer.state["reason"])


class NativeHarnessFixtureTests(unittest.TestCase):
    """Local checks for harness artifacts and controlled seed data only."""

    def test_stale_map_seed_is_explicitly_harness_authored_and_schema_shaped(self):
        plan = NativeWorkflowProbe._stale_map_seed_plan(Path("/temporary/work"), "native-stale-environment-map")
        self.assertIn("harness-authored", plan["origin"])
        self.assertIn("not an actual Codex upgrade", plan["proof_limit"])
        snapshot = plan["environment_snapshot"]
        self.assertEqual("fixture-pre-model-v1", snapshot["version"])
        self.assertEqual(["low"], snapshot["models"][0]["reasoning"]["effort"])
        profile = plan["profiles"][0]
        self.assertEqual(snapshot["models"][0]["id"], profile["model"])
        self.assertEqual("low", profile["reasoning"]["effort"])

    def test_harness_source_snapshot_is_durable_and_matches_current_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary)
            manifest = NativeWorkflowProbe._snapshot_harness_source(evidence)
            self.assertEqual(3, len(manifest["files"]))
            self.assertTrue(all(item["source_sha256"] == item["snapshot_sha256"]
                                for item in manifest["files"]))
            self.assertTrue((evidence / "harness-source-manifest.json").is_file())

    def test_primary_reasoning_effort_comes_from_catalog_not_a_hardcoded_turn(self):
        models = {"data": [{
            "id": "gpt-6-astra",
            "supportedReasoningEfforts": [{"reasoningEffort": "high"}, {"reasoningEffort": "xhigh"}],
        }]}
        self.assertEqual("high", NativeWorkflowProbe.selected_primary_effort("high"))
        selection = NativeWorkflowProbe._primary_selection(models, "xhigh")
        self.assertEqual("xhigh", selection["reasoning_effort"])
        with self.assertRaisesRegex(AssertionError, "primary_effort_is_unavailable"):
            NativeWorkflowProbe._primary_selection(models, "max")


class MultistageCollectorTests(unittest.TestCase):
    """Reproduction uses the fixture's documented positional CLI interface."""

    def test_reproduces_saved_style_pipeline_in_a_separate_work_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary)
            work = evidence / "work"
            for relative, content in MULTISTAGE_NORMALIZE_CLI_SCENARIO.files.items():
                path = work / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            (work / "app" / "normalize.py").write_text(
                """def normalize(records):
    result, seen = [], set()
    for record in records:
        if record[\"id\"] in seen:
            continue
        seen.add(record[\"id\"])
        if record[\"active\"]:
            result.append({\"id\": record[\"id\"], \"label\": record[\"label\"].strip().casefold(), \"amount\": record[\"amount\"]})
    return result
""", encoding="utf-8")
            (work / "app" / "report.py").write_text(
                """def build_summary(normalized):
    return {\"count\": len(normalized), \"total_amount\": sum(item[\"amount\"] for item in normalized), \"zero_amount_ids\": [item[\"id\"] for item in normalized if item[\"amount\"] == 0]}
""", encoding="utf-8")
            (work / "app" / "cli.py").write_text(
                """import json
import sys
from pathlib import Path
from .normalize import normalize
from .report import build_summary
records = json.loads(Path(sys.argv[1]).read_text(encoding=\"utf-8\"))
for path, value in ((Path(sys.argv[2]), normalize(records)), (Path(sys.argv[3]), build_summary(normalize(records)))):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + \"\\n\", encoding=\"utf-8\")
""", encoding="utf-8")
            (work / "out").mkdir()
            (work / "out" / "normalized.json").write_text(
                json.dumps([{"id": "A", "label": "alpha", "amount": 10}, {"id": "B", "label": "beta", "amount": 0}]) + "\n",
                encoding="utf-8")
            (work / "out" / "summary.json").write_text(
                json.dumps({"count": 2, "total_amount": 10, "zero_amount_ids": ["B"]}) + "\n", encoding="utf-8")
            result = NativeWorkflowProbe._verify_fixture(
                evidence, MULTISTAGE_NORMALIZE_CLI_SCENARIO, {"status": "not_applicable"})
            self.assertEqual("passed", result["status"], result)
            contract = MULTISTAGE_NORMALIZE_CLI_SCENARIO.files["spec/contract.md"]
            self.assertIn("`python -m app.cli INPUT NORMALIZED SUMMARY`", contract)
            self.assertIn("`INPUT` is `data/events.json`", contract)
            self.assertIn("`NORMALIZED` is\n`out/normalized.json`", contract)
            self.assertIn("`SUMMARY` is `out/summary.json`", contract)
            self.assertEqual(0, result["repeat_cli"]["exit_code"], result)
            self.assertEqual([sys.executable, "-m", "app.cli", "data/events.json",
                              "out/normalized.json", "out/summary.json"], result["repeat_cli"]["arguments"])


if __name__ == "__main__":
    unittest.main()

"""Protocol-facing contract checks for workflow MCP registrations without MCP deps."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "plugins" / "persistent-context-workspace" / "pcw_runtime" / "server.py"


def _functions():
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}


class MCPWorkflowTests(unittest.TestCase):
    def test_workflow_mcp_tools_have_explicit_coordinate_and_payload_parameters(self):
        functions = _functions()
        expected = {
        "pcw_environment_get": ["work_root", "workspace"],
        "pcw_environment_check": ["work_root", "workspace", "environment_snapshot"],
        "pcw_tools_map_get": ["work_root", "workspace"],
        "pcw_tools_map_publish": ["work_root", "workspace", "expected_environment_revision", "profiles"],
        "pcw_rules_get": ["work_root", "workspace", "action"],
        "pcw_startup": ["work_root", "workspace"],
        "pcw_result_assess": ["work_root", "workspace", "assignment_id", "assessment"],
    }
        for name, parameters in expected.items():
            node = functions[name]
            self.assertEqual(parameters, [argument.arg for argument in node.args.args])
            self.assertIsNone(node.args.kwarg)
            self.assertTrue(all(argument.annotation is not None for argument in node.args.args))


    def test_workflow_tools_are_registered_and_described_as_control_plane_only(self):
        source = SERVER.read_text(encoding="utf-8")
        for name in ("environment_get", "environment_check", "tools_map_get", "tools_map_publish", "rules_get", "assignment_prepare", "result_assess", "finish"):
            self.assertIn(f'"{name}":', source)
            self.assertIn(f'"pcw_{name}"', source)
        self.assertIn("This tool never chooses a model.", source)
        self.assertIn("It never dispatches agents or gives semantic acceptance.", source)

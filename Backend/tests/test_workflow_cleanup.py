import sys
import unittest
import importlib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(PROJECT_ROOT))

backend_app = importlib.import_module("Backend.app")
sys.modules["app"] = backend_app

from app.agents.workflow import create_workflow


class WorkflowCleanupTests(unittest.TestCase):
    def test_bc_retry_nodes_removed_from_workflow_definition(self):
        workflow = create_workflow()
        node_names = set(workflow.nodes.keys())
        self.assertNotIn("retry_counter_b", node_names)
        self.assertNotIn("retry_counter_c", node_names)
        self.assertIn("quality_gate_bc", node_names)
        self.assertIn("agent_d", node_names)


if __name__ == "__main__":
    unittest.main()

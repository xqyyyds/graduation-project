import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class ProgressComputationTests(unittest.TestCase):
    def test_prepare_stage_progress_uses_weighted_overall_progress(self):
        from Backend.app.core.progress import build_progress_payload

        payload = build_progress_payload("prepare", 50, "准备中")

        self.assertEqual(payload["stage_id"], "prepare")
        self.assertEqual(payload["stage_progress"], 50)
        self.assertEqual(payload["overall_progress"], 8)

    def test_done_stage_clamps_to_full_progress(self):
        from Backend.app.core.progress import build_progress_payload

        payload = build_progress_payload("done", 100, "完成")

        self.assertEqual(payload["overall_progress"], 100)
        self.assertEqual(payload["stage_label"], "导出完成")

    def test_unknown_stage_falls_back_to_prepare(self):
        from Backend.app.core.progress import build_progress_payload

        payload = build_progress_payload("unexpected", 10, "未知")

        self.assertEqual(payload["stage_id"], "prepare")
        self.assertEqual(payload["stage_label"], "数据准备")


if __name__ == "__main__":
    unittest.main()

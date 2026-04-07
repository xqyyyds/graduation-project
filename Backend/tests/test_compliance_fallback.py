import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class ComplianceFallbackTests(unittest.TestCase):
    def test_finalize_batch_no_model_switch_when_filtered(self):
        from Backend.app.services.compliance import AgentCompliance

        agent = AgentCompliance()
        primary_llm = object()
        agent.strong_llm = primary_llm

        calls = []

        def fake_invoke(llm, post_content, candidate_items):
            calls.append(llm)
            raise RuntimeError("content_filter triggered")

        agent._invoke_final_chain = fake_invoke

        cases, blocked = agent._finalize_batch(
            post_content="主贴内容",
            candidate_items=[
                {
                    "index": 0,
                    "source_type": "comment",
                    "source_id": "c1",
                    "content": "把他挂出来冲",
                    "candidate_category": "不良信息-网暴",
                    "reason_brief": "存在围攻煽动倾向",
                }
            ],
            batch_size=1,
            llm=primary_llm,
            llm_name="strong",
            allow_backup=True,
        )

        self.assertEqual(calls, [primary_llm])
        self.assertEqual(blocked, 1)
        self.assertEqual(cases, [])


if __name__ == "__main__":
    unittest.main()

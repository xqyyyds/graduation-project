import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class QualityGateRuleTests(unittest.TestCase):
    def test_check_c_requires_source_trace_fields_for_cases(self):
        from Backend.app.agents.quality_gate import _check_c

        result = _check_c(
            {
                "audit_results": [
                    {
                        "violation_info": {
                            "post_case": {
                                "quote": "主贴违规摘录",
                                "category": "不良信息-网暴",
                                "reasoning": "理由",
                                "primary_law": "第十四条",
                                "disposal_suggestion": "限制/更改/屏蔽/删除相关内容的展示",
                                "source_type": "post",
                                "source_id": "",
                                "index": -1,
                            },
                            "comment_cases": [
                                {
                                    "quote": "评论违规摘录",
                                    "category": "人身攻击-侮辱",
                                    "reasoning": "理由",
                                    "primary_law": "第九条",
                                    "disposal_suggestion": "限制/更改/屏蔽/删除相关内容的展示",
                                    "source_type": "comment",
                                    "source_id": "comment-1",
                                }
                            ],
                        }
                    }
                ]
            }
        )

        self.assertFalse(result["passed"])
        self.assertTrue(
            any("source_id" in issue or "index" in issue for issue in result["issues"])
        )

    def test_check_d_requires_summary_paragraph_for_each_point(self):
        from Backend.app.agents.quality_gate import _check_d

        result = _check_d(
            {
                "trend_forecast": {
                    "topics": [
                        {
                            "topic_name": "议题一",
                            "background": "背景",
                            "main_tension": "个体结果焦虑被迅速改写为程序公平质疑",
                            "points": [
                                {
                                    "subtitle": "点一",
                                    "audience": "考生与家长",
                                    "scene": "查分夜群聊截图集中流出",
                                    "evolution_path": "先因分数截图起火，再滑向规则不透明争议",
                                    "evidence_basis": ["历史规律"],
                                    "summary_paragraph": "",
                                },
                                {
                                    "subtitle": "点二",
                                    "audience": "考生与家长",
                                    "scene": "调剂名单对比图在社媒扩散",
                                    "evolution_path": "先因名单对比起火，再滑向资源分配争议",
                                    "evidence_basis": ["未来情报"],
                                    "summary_paragraph": "完整段落",
                                },
                            ],
                        },
                        {
                            "topic_name": "议题二",
                            "background": "背景",
                            "main_tension": "回应失误被放大为治理能力争论",
                            "points": [
                                {
                                    "subtitle": "点一",
                                    "audience": "家长与学校管理者",
                                    "scene": "家长群内回应截图二次传播",
                                    "evolution_path": "先因回应措辞失误起火，再滑向治理能力争议",
                                    "evidence_basis": ["历史规律"],
                                    "summary_paragraph": "完整段落",
                                },
                                {
                                    "subtitle": "点二",
                                    "audience": "家长与学校管理者",
                                    "scene": "短视频复盘片段被集中转发",
                                    "evolution_path": "先因复盘视频起火，再滑向问责范围扩张",
                                    "evidence_basis": ["未来情报"],
                                    "summary_paragraph": "完整段落",
                                },
                            ],
                        },
                        {
                            "topic_name": "议题三",
                            "background": "背景",
                            "main_tension": "个案评价演化为群体标签冲突",
                            "points": [
                                {
                                    "subtitle": "点一",
                                    "audience": "教师与在校生",
                                    "scene": "课堂片段剪辑引发身份对立讨论",
                                    "evolution_path": "先因剪辑片段起火，再滑向群体标签冲突",
                                    "evidence_basis": ["历史规律"],
                                    "summary_paragraph": "完整段落",
                                },
                                {
                                    "subtitle": "点二",
                                    "audience": "教师与在校生",
                                    "scene": "论坛热帖延伸到线下争吵",
                                    "evolution_path": "先因热帖起火，再滑向群体互斥表达",
                                    "evidence_basis": ["未来情报"],
                                    "summary_paragraph": "完整段落",
                                },
                            ],
                        },
                    ]
                }
            }
        )

        self.assertFalse(result["passed"])
        self.assertTrue(any("summary_paragraph" in issue for issue in result["issues"]))


if __name__ == "__main__":
    unittest.main()

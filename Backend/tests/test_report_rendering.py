import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class ReportRenderingTests(unittest.TestCase):
    def test_forecast_markdown_prefers_summary_paragraph_over_internal_fields(self):
        from Backend.app.services.report import _assemble_markdown_from_report_doc

        report_doc = {
            "meta": {
                "title": "测试报告",
                "category": "高校",
                "generated_at": "2026-04-02 18:00:00",
                "report_period": "2026-04-01 至 2026-04-30",
            },
            "preface": {
                "report_period": "2026-04-01 至 2026-04-30",
                "paragraphs": ["前言段落"],
            },
            "overview_table": [],
            "deep_reads": [],
            "compliance": {
                "summary": {
                    "total_cases": 0,
                    "event_count": 0,
                    "phase_summary": "本期未检出需要重点处置的违规内容。",
                    "risk_levels": [],
                    "categories": [],
                    "laws": [],
                }
            },
            "forecast": {
                "target_period": "2026-04-01 至 2026-04-30",
                "topics": [
                    {
                        "topic_name": "（一）测试议题",
                        "background": "背景说明",
                        "audience": "考生",
                        "scene_opening": "查分夜",
                        "points": [
                            {
                                "subtitle": "成绩节点叠加焦虑",
                                "trigger": "查分截图流出",
                                "spread_path": "群聊到热搜",
                                "offline_scene": "宿舍讨论",
                                "online_scene": "评论区",
                                "evidence_basis": ["历史同期规律"],
                                "content": "旧的内部研判正文",
                                "summary_paragraph": "这是一段面向读者的段落式预测正文。",
                            }
                        ],
                    }
                ],
            },
            "appendix_stats": {"risk_levels": [], "categories": [], "laws": []},
            "appendix_cases": [],
        }

        markdown = _assemble_markdown_from_report_doc(report_doc)
        self.assertIn("这是一段面向读者的段落式预测正文。", markdown)
        self.assertNotIn("**触发点**", markdown)
        self.assertNotIn("**传播路径**", markdown)
        self.assertNotIn("**线下场景**", markdown)
        self.assertNotIn("**线上场景**", markdown)
        self.assertNotIn("**依据**", markdown)

    def test_forecast_html_uses_summary_paragraph_not_internal_field_rows(self):
        from Backend.app.services.render_html import render_report_html

        report_doc = {
            "meta": {
                "title": "测试报告",
                "category": "高校",
                "generated_at": "2026-04-02 18:00:00",
                "report_period": "2026-04-01 至 2026-04-30",
            },
            "preface": {
                "report_period": "2026-04-01 至 2026-04-30",
                "paragraphs": ["前言段落"],
            },
            "overview_table": [],
            "deep_reads": [],
            "compliance": {
                "summary": {
                    "total_cases": 0,
                    "event_count": 0,
                    "phase_summary": "本期未检出需要重点处置的违规内容。",
                    "risk_levels": [],
                    "categories": [],
                    "laws": [],
                }
            },
            "forecast": {
                "target_period": "2026-04-01 至 2026-04-30",
                "topics": [
                    {
                        "topic_name": "（一）测试议题",
                        "background": "背景说明",
                        "audience": "考生",
                        "scene_opening": "查分夜",
                        "points": [
                            {
                                "subtitle": "成绩节点叠加焦虑",
                                "trigger": "查分截图流出",
                                "spread_path": "群聊到热搜",
                                "offline_scene": "宿舍讨论",
                                "online_scene": "评论区",
                                "evidence_basis": ["历史同期规律"],
                                "content": "旧的内部研判正文",
                                "summary_paragraph": "这是一段面向读者的段落式预测正文。",
                            }
                        ],
                    }
                ],
            },
            "appendix_stats": {"risk_levels": [], "categories": [], "laws": []},
            "appendix_cases": [],
        }

        html = render_report_html(report_doc)
        self.assertIn("这是一段面向读者的段落式预测正文。", html)
        self.assertNotIn("触发点：", html)
        self.assertNotIn("传播路径：", html)
        self.assertNotIn("线下场景：", html)
        self.assertNotIn("线上场景：", html)
        self.assertNotIn("依据：", html)


if __name__ == "__main__":
    unittest.main()

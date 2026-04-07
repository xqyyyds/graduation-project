import sys
import unittest
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


fake_utils = ModuleType("app.services.utils")
fake_utils.normalize_category = lambda value: value or "其他"
fake_utils.get_web_context = lambda *args, **kwargs: ""
fake_utils.tavily_search = lambda *args, **kwargs: []
sys.modules.setdefault("app.services.utils", fake_utils)

fake_llm_factory = ModuleType("app.core.llm_factory")
fake_llm_factory.get_main_llm = lambda **kwargs: object()
fake_llm_factory.build_chat_openai = lambda **kwargs: object()
fake_llm_factory.resolve_llm_config = lambda: SimpleNamespace(
    model="fake-model",
    base_url="http://fake",
    api_key="fake",
)
sys.modules.setdefault("app.core.llm_factory", fake_llm_factory)

fake_xhtml2pdf = ModuleType("xhtml2pdf")
fake_xhtml2pdf.pisa = ModuleType("pisa")
fake_xhtml2pdf.pisa.CreatePDF = lambda src, dest, encoding="utf-8": type(
    "Result", (), {"err": 0}
)()
sys.modules.setdefault("xhtml2pdf", fake_xhtml2pdf)


class ReportDocumentBuilderTests(unittest.TestCase):
    def test_report_law_text_supports_string_and_dict_entries(self):
        from Backend.app.services.report import _law_entry_text
        from Backend.app.services.report_document import _first_law_text

        self.assertEqual(
            _law_entry_text("《微博投诉操作细则》第十四条"),
            "《微博投诉操作细则》第十四条",
        )
        self.assertEqual(
            _law_entry_text(
                {"article": "第十四条", "category": "不良信息", "full_desc": "网暴煽动"}
            ),
            "《《微博社区公约》》第十四条：不良信息\n网暴煽动",
        )
        self.assertEqual(
            _first_law_text(["《微博投诉操作细则》第十四条"]),
            "《微博投诉操作细则》第十四条",
        )

    def test_overview_rows_keep_fixed_four_columns(self):
        from Backend.app.services.report_document import build_overview_rows

        rows = build_overview_rows(
            [
                {
                    "created_at": "2026-04-01 12:30:00",
                    "event_name": "#高校舆情#",
                    "total_heat": 12345,
                }
            ]
        )

        self.assertEqual(
            rows,
            [
                {
                    "seq": 1,
                    "time": "2026-04-01",
                    "event_name": "高校舆情",
                    "heat_value": "1.2万",
                }
            ],
        )

    def test_compliance_cases_flatten_post_and_comment_items(self):
        from Backend.app.services.report_document import build_compliance_cases

        audit_results = [
            {
                "event_name": "事件A",
                "post_content": "这是一条很长的帖子原文，需要被截断展示。",
                "violation_info": {
                    "overall_risk_level": "High",
                    "category": "人身攻击-侮辱",
                    "matched_laws": [{"article": "第九条", "category": "人身攻击"}],
                    "evidence_report": {
                        "reasoning": "主帖直接针对个人进行侮辱。",
                        "disposal_suggestion": "建议删除主帖",
                    },
                    "is_post_violated": True,
                    "violated_comments": [
                        {
                            "index": 0,
                            "category": "不良信息-网暴",
                            "reasoning": "评论含有围攻煽动倾向。",
                        }
                    ],
                },
                "violated_comment_originals": [
                    {
                        "index": 0,
                        "content": "大家一起去骂他",
                        "category": "不良信息-网暴",
                        "risk_level": "Medium",
                    }
                ],
            }
        ]

        cases = build_compliance_cases(audit_results)

        self.assertEqual(len(cases), 2)
        self.assertEqual(cases[0]["source_type"], "帖子")
        self.assertEqual(cases[0]["primary_law"], "人身攻击 / 第九条")
        self.assertEqual(cases[1]["source_type"], "评论")
        self.assertEqual(cases[1]["quote"], "大家一起去骂他")
        self.assertEqual(cases[1]["category"], "不良信息-网暴")

    def test_compliance_cases_support_new_case_structure(self):
        from Backend.app.services.report_document import build_compliance_cases

        audit_results = [
            {
                "event_name": "事件B",
                "post_content": "主帖上下文",
                "violation_info": {
                    "overall_risk_level": "Medium",
                    "matched_laws": [{"article": "第十四条", "category": "不良信息"}],
                    "evidence_report": {
                        "disposal_suggestion": "建议删除并限制传播",
                    },
                    "post_case": {
                        "category": "不良信息-网暴",
                        "quote": "把他挂出来冲",
                        "reasoning": "主帖存在明显围攻煽动。",
                        "primary_law": "第十四条 网暴煽动",
                        "disposal_suggestion": "建议删除主帖",
                    },
                    "comment_cases": [
                        {
                            "category": "人身攻击-侮辱",
                            "risk_level": "Low",
                            "quote": "真是个废物",
                            "reasoning": "对具体对象进行恶毒侮辱。",
                            "primary_law": "第九条 人身攻击",
                            "disposal_suggestion": "建议删除评论",
                        }
                    ],
                },
            }
        ]

        cases = build_compliance_cases(audit_results)
        self.assertEqual(len(cases), 2)
        self.assertEqual(cases[0]["quote"], "把他挂出来冲")
        self.assertEqual(cases[0]["primary_law"], "第十四条 网暴煽动")
        self.assertEqual(cases[1]["source_type"], "评论")
        self.assertEqual(cases[1]["primary_law"], "第九条 人身攻击")

    def test_compliance_cases_include_traceability_source_id_and_index(self):
        from Backend.app.services.report_document import build_compliance_cases

        audit_results = [
            {
                "event_name": "事件C",
                "note_id": "note-123",
                "post_content": "主帖上下文",
                "violation_info": {
                    "overall_risk_level": "Medium",
                    "matched_laws": [{"article": "第十四条", "category": "不良信息"}],
                    "evidence_report": {
                        "disposal_suggestion": "建议删除并限制传播",
                    },
                    "post_case": {
                        "index": -1,
                        "source_id": "note-123",
                        "category": "不良信息-网暴",
                        "quote": "把他挂出来冲",
                        "reasoning": "主帖存在明显围攻煽动。",
                        "primary_law": "第十四条 网暴煽动",
                        "disposal_suggestion": "建议删除主帖",
                    },
                    "comment_cases": [
                        {
                            "index": 0,
                            "source_id": "comment-456",
                            "category": "人身攻击-侮辱",
                            "risk_level": "Low",
                            "quote": "真是个废物",
                            "reasoning": "对具体对象进行恶毒侮辱。",
                            "primary_law": "第九条 人身攻击",
                            "disposal_suggestion": "建议删除评论",
                        }
                    ],
                },
            }
        ]

        cases = build_compliance_cases(audit_results)
        self.assertEqual(cases[0]["source_id"], "note-123")
        self.assertEqual(cases[0]["index"], -1)
        self.assertEqual(cases[1]["source_id"], "comment-456")
        self.assertEqual(cases[1]["index"], 0)

    def test_build_report_document_adds_render_version_and_forecast_summary_paragraph(
        self,
    ):
        from types import SimpleNamespace

        from Backend.app.services.report_document import build_report_document

        report = build_report_document(
            state_data={
                "category": "高校",
                "core_events": [],
                "analyzed_events": [],
                "audit_results": [],
                "trend_forecast": {
                    "target_period": "2026-04-01 至 2026-04-30",
                    "topics": [
                        {
                            "topic_name": "成绩节点叠加下的升学焦虑外溢",
                            "main_tension": "个体升学焦虑会被持续改写为程序公平争议",
                            "points": [
                                {
                                    "subtitle": "二手消息再次抢跑",
                                    "audience": "考生、家长、高校招生办",
                                    "scene": "复试线、调剂名额、院校通知在群聊和信息帖抢跑流出",
                                    "evolution_path": "先因二手截图起火，再滑向规则不透明与资源分配争议",
                                    "content": "未来一个月内，围绕调剂信息、院校名额和复试公平性的二手截图仍会频繁出现。",
                                    "evidence_basis": [
                                        "当前查分与分数线焦虑",
                                        "下月复试和调剂节点临近",
                                    ],
                                }
                            ],
                        }
                    ],
                },
            },
            markdown="",
            preface=SimpleNamespace(
                report_period="2026-04-01 至 2026-04-30",
                paragraphs=["第一段前言", "第二段前言"],
            ),
        )

        self.assertEqual(report["meta"]["render_version"], "report_json_v2")
        self.assertEqual(len(report["preface"]["paragraphs"]), 2)
        self.assertEqual(report["preface"]["paragraphs"][0], "第一段前言")
        self.assertEqual(report["preface"]["paragraphs"][1], "第二段前言")
        point = report["forecast"]["topics"][0]["points"][0]
        self.assertIn("复试线、调剂名额、院校通知", point["summary_paragraph"])
        self.assertIn("规则不透明与资源分配争议", point["summary_paragraph"])


if __name__ == "__main__":
    unittest.main()

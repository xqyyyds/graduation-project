import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _install_backend_test_stubs():
    fake_utils = ModuleType("app.services.utils")
    fake_utils.normalize_category = lambda value: value or "其他"
    fake_utils.get_web_context = lambda *args, **kwargs: ""
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

    fake_main = ModuleType("main")
    fake_main.run_task = lambda *args, **kwargs: None
    sys.modules.setdefault("main", fake_main)

    fake_mongo_module = ModuleType("app.db.mongo_manager")
    fake_mongo_module.mongo_db = SimpleNamespace(
        get_report_session_by_filename=lambda filename: None
    )
    sys.modules.setdefault("app.db.mongo_manager", fake_mongo_module)


_install_backend_test_stubs()


def _sample_report_doc():
    return {
        "meta": {
            "title": "舆情研判报告（高校）",
            "category": "高校",
            "generated_at": "2026-04-02 16:00:00",
            "task_id": "task_20260402_1600",
            "report_period": "2026-04-01 至 2026-04-30",
            "render_version": "report_json_v2",
        },
        "preface": {
            "report_period": "2026-04-01 至 2026-04-30",
            "paragraphs": ["前言第一段", "前言第二段"],
        },
        "overview_table": [
            {
                "seq": 1,
                "time": "2026-04-01",
                "event_name": "考研国家线讨论升温",
                "heat_value": "12.3万",
            }
        ],
        "deep_reads": [
            {
                "event_name": "考研国家线讨论升温",
                "editorial_title": "分数线还没落地，焦虑先在评论区炸开了",
                "one_line_verdict": "这不是一次普通热议，而是升学压力在节点上的集中释放。",
                "event_overview": "事件概况正文",
                "public_opinions": ["观点一", "观点二"],
                "depth_analysis": "深度研判正文",
                "key_quotes": ["引用一"],
            }
        ],
        "compliance": {
            "summary": {
                "total_cases": 1,
                "event_count": 1,
                "risk_levels": [{"label": "High", "count": 1}],
                "categories": [{"label": "不良信息-网暴", "count": 1}],
                "laws": [{"label": "《微博投诉操作细则》第十四条", "count": 1}],
                "phase_summary": "当前违规主要集中在围攻煽动表达。",
            },
            "events": [],
        },
        "forecast": {
            "target_period": "2026-04-01 至 2026-04-30",
            "topics": [
                {
                    "topic_name": "成绩节点叠加下的升学焦虑外溢",
                    "background": "背景导语",
                    "audience": "考研考生、毕业生、家长",
                    "scene_opening": "查分夜和调剂群将成为情绪集中释放点",
                    "points": [
                        {
                            "subtitle": "二手消息再次抢跑",
                            "trigger": "复试线、调剂名额、院校通知流出",
                            "spread_path": "从群聊截图扩散到短视频平台和评论区",
                            "offline_scene": "宿舍、考研自习室、家长群讨论",
                            "online_scene": "热搜评论区、考研博主账号、信息汇总帖",
                            "content": "未来一个月内，围绕调剂信息、院校名额和复试公平性的二手截图仍会频繁出现。",
                            "summary_paragraph": "一旦复试线、调剂名额和院校通知流出，相关讨论很可能沿着群聊截图扩散到短视频平台和评论区，并在宿舍、考研自习室、家长群讨论、热搜评论区、考研博主账号、信息汇总帖等场景中持续放大。未来一个月内，围绕调剂信息、院校名额和复试公平性的二手截图仍会频繁出现。",
                            "evidence_basis": [
                                "当前查分与分数线焦虑",
                                "下月复试和调剂节点临近",
                            ],
                        }
                    ],
                }
            ],
        },
        "appendix_stats": {
            "risk_levels": [{"label": "High", "count": 1}],
            "categories": [{"label": "不良信息-网暴", "count": 1}],
            "laws": [{"label": "《微博投诉操作细则》第十四条", "count": 1}],
        },
        "appendix_cases": [
            {
                "event_name": "考研国家线讨论升温",
                "cases": [
                    {
                        "source_type": "评论",
                        "category": "不良信息-网暴",
                        "risk_level": "High",
                        "quote": "把他信息挂出来，大家一起冲",
                        "reasoning": "存在明显围攻与人肉倾向。",
                        "primary_law": "《微博投诉操作细则》第十四条",
                        "law_reason": "该评论直接鼓动围攻具体对象，符合网暴煽动场景。",
                        "evidence_chain": "所属帖子：国家线讨论帖；评论原文：把他信息挂出来，大家一起冲",
                        "disposal_suggestion": "删除评论并限制继续传播",
                    }
                ],
            }
        ],
    }


class ReportArtifactConsistencyTests(unittest.TestCase):
    def _make_output_dir(self) -> Path:
        temp_path = Path(tempfile.mkdtemp(prefix="artifact-test-"))
        self.addCleanup(lambda: shutil.rmtree(temp_path, ignore_errors=True))
        return temp_path

    def test_html_and_markdown_use_summary_paragraph_instead_of_field_rows(self):
        from Backend.app.services.render_html import render_report_html
        from Backend.app.services.report import render_markdown_from_report_doc

        report_doc = _sample_report_doc()
        html = render_report_html(report_doc)
        markdown = render_markdown_from_report_doc(report_doc)

        self.assertIn("预警摘要", html)
        self.assertIn("一旦复试线、调剂名额和院校通知流出", html)
        self.assertNotIn("触发点：", html)
        self.assertNotIn("传播路径：", html)
        self.assertNotIn("线下场景：", html)
        self.assertNotIn("线上场景：", html)
        self.assertIn("所属事件", html)
        self.assertIn("考研国家线讨论升温", html)
        self.assertIn("前言第一段", html)
        self.assertIn("前言第二段", html)

        self.assertIn("#### 二手消息再次抢跑", markdown)
        self.assertIn("一旦复试线、调剂名额和院校通知流出", markdown)
        self.assertNotIn("**触发点**", markdown)
        self.assertNotIn("**传播路径**", markdown)
        self.assertIn("**所属事件**", markdown)
        self.assertIn("前言第一段", markdown)

    def test_report_json_endpoint_falls_back_to_report_session(self):
        from Backend.app.api.main import app

        report_doc = _sample_report_doc()
        output_dir = self._make_output_dir()
        with patch("Backend.app.api.main.OUTPUT_DIR", output_dir), patch(
            "Backend.app.api.main.mongo_db.get_report_session_by_filename",
            return_value={
                "report_json": report_doc,
                "render_version": "report_json_v2",
            },
        ):
            with TestClient(app) as client:
                response = client.get(
                    "/api/reports/舆情研判_高校_20260402_1600.md/json"
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["meta"]["render_version"], "report_json_v2")

    def test_download_html_falls_back_to_report_session_json(self):
        from Backend.app.api.main import app

        report_doc = _sample_report_doc()
        output_dir = self._make_output_dir()
        with patch("Backend.app.api.main.OUTPUT_DIR", output_dir), patch(
            "Backend.app.api.main.mongo_db.get_report_session_by_filename",
            return_value={
                "report_json": report_doc,
                "render_version": "report_json_v2",
            },
        ):
            with TestClient(app) as client:
                response = client.get(
                    "/api/reports/舆情研判_高校_20260402_1600.md/download?format=html"
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        body = response.text
        self.assertIn("舆情研判报告（高校）", body)
        self.assertNotIn("触发点：", body)


if __name__ == "__main__":
    unittest.main()

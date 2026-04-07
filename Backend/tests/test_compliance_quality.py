import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class ComplianceQualityTests(unittest.TestCase):
    def test_finalize_batch_uses_lenient_json_fallback_on_trailing_characters(self):
        from Backend.app.services.compliance import AgentCompliance

        agent = AgentCompliance()

        candidate_items = [
            {
                "index": 0,
                "source_type": "comment",
                "source_id": "comment-001",
                "content": "评论正文",
            }
        ]

        class _FakeCase:
            def model_dump(self):
                return {
                    "index": 0,
                    "quote": "测试摘录",
                    "category": "不实信息-造谣",
                    "reasoning": "测试理由",
                    "is_violation": True,
                }

        fake_result = SimpleNamespace(cases=[_FakeCase()])

        parse_error = ValueError(
            "1 validation error for ViolationCaseStage1Batch\n"
            "Invalid JSON: trailing characters at line 2 column 1 "
            "[type=json_invalid, input_value='<truncated-json>', input_type=str]"
        )

        with patch.object(agent, "_invoke_final_chain", side_effect=parse_error):
            with patch.object(
                agent,
                "_invoke_final_chain_lenient",
                return_value=fake_result,
            ) as fallback_mock:
                cases, blocked = agent._finalize_batch(
                    post_content="主贴内容",
                    candidate_items=candidate_items,
                    batch_size=1,
                    event_name="事件A",
                    source_keyword="关键词",
                )

        self.assertEqual(blocked, 0)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["source_type"], "comment")
        self.assertEqual(cases[0]["source_id"], "comment-001")
        fallback_mock.assert_called_once()

    def test_stage1_batch_rehydrates_source_fields_from_candidate_pool(self):
        from Backend.app.services.compliance import AgentCompliance

        agent = AgentCompliance()

        class _FakeCase:
            def model_dump(self):
                return {
                    "index": 0,
                    "quote": "测试摘录",
                    "category": "不实信息-造谣",
                    "reasoning": "测试理由",
                    "is_violation": True,
                }

        fake_result = SimpleNamespace(cases=[_FakeCase()])
        candidate_items = [
            {
                "index": 0,
                "source_type": "comment",
                "source_id": "comment-001",
                "content": "评论正文",
            }
        ]

        with patch.object(agent, "_invoke_final_chain", return_value=fake_result):
            cases, blocked = agent._finalize_batch(
                post_content="主贴内容",
                candidate_items=candidate_items,
                batch_size=1,
                event_name="事件A",
                source_keyword="关键词",
            )

        self.assertEqual(blocked, 0)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["source_type"], "comment")
        self.assertEqual(cases[0]["source_id"], "comment-001")

    def test_disposal_suggestion_is_normalized_to_whitelist(self):
        from Backend.app.services.compliance import AgentCompliance

        agent = AgentCompliance()
        normalized = agent._normalize_disposal_suggestion(
            "建议删除评论并限制继续传播", "Medium", True
        )
        self.assertIn(normalized, agent.DISPOSAL_OPTIONS)
        self.assertEqual(normalized, "限制/更改/屏蔽/删除相关内容的展示")

    def test_disposal_suggestion_for_non_violation_uses_option_6(self):
        from Backend.app.services.compliance import AgentCompliance

        agent = AgentCompliance()
        normalized = agent._normalize_disposal_suggestion(
            "保留观察/不处置", "Low", False
        )
        self.assertEqual(normalized, "其他合理措施")

    def test_audit_post_packet_uses_direct_review_without_screen_stage(self):
        from Backend.app.services.compliance import AgentCompliance

        agent = AgentCompliance()
        packet = {
            "note_id": "n1",
            "content": "主贴内容",
            "source_keyword": "测试词",
            "audit_comment_items": [
                {
                    "comment_id": "c1",
                    "content": "评论内容",
                    "db_id": "db1",
                }
            ],
        }

        with patch.object(
            agent, "finalize_candidates", return_value=([], 0)
        ) as finalize_mock:
            result = agent.audit_post_packet(packet, event_name="事件A")

        self.assertFalse(result["is_violation"])
        self.assertTrue(finalize_mock.called)
        finalize_kwargs = finalize_mock.call_args.kwargs
        suspects = finalize_kwargs.get("suspects") or []
        self.assertGreaterEqual(len(suspects), 2)
        self.assertEqual(suspects[0]["reason_brief"], "阶段1审核")

    def test_audit_post_packet_applies_stage2_evidence_enhancement(self):
        from Backend.app.services.compliance import AgentCompliance

        agent = AgentCompliance()
        packet = {
            "note_id": "n1",
            "content": "主贴内容",
            "source_keyword": "测试词",
            "audit_comment_items": [],
        }

        stage1_cases = [
            {
                "source_type": "post",
                "source_id": "n1",
                "index": -1,
                "quote": "他就是诈骗犯，已经坐实",
                "category": "不实信息-造谣",
                "risk_level": "Medium",
                "reasoning": "原始理由",
                "is_violation": True,
            }
        ]

        fake_law = {
            "matched_laws": [
                {
                    "category": "不实信息-造谣",
                    "article": "第十四条",
                    "risk_level": "Medium",
                    "rule": "编造并传播未经证实信息。",
                    "full_desc": "编造传播未经证实信息",
                }
            ],
            "primary_law": "第十四条 编造传播未经证实信息",
            "law_reason": "命中规则",
        }

        with patch.object(agent, "finalize_candidates", return_value=(stage1_cases, 0)):
            with patch.object(agent, "_match_laws_for_case", return_value=fake_law):
                with patch.object(
                    agent,
                    "_invoke_evidence_chain",
                    return_value=agent._EvidenceEnhanceResult(
                        reasoning="增强后理由",
                        disposal_suggestion="向有关监管部门或国家机关报告",
                        evidence_chain=["证据A", "证据B"],
                    ),
                ):
                    result = agent.audit_post_packet(packet, event_name="事件A")

        self.assertTrue(result["is_violation"])
        post_case = result["violation_info"]["post_case"]
        self.assertEqual(post_case["reasoning"], "增强后理由")
        self.assertEqual(
            post_case["disposal_suggestion"], "向有关监管部门或国家机关报告"
        )
        self.assertEqual(post_case["evidence_chain"], ["证据A", "证据B"])

    def test_audit_post_packet_uses_law_metadata_as_risk_level_source(self):
        from Backend.app.services.compliance import AgentCompliance

        agent = AgentCompliance()
        packet = {
            "note_id": "n1",
            "content": "主贴内容",
            "source_keyword": "测试词",
            "audit_comment_items": [],
        }

        stage1_cases = [
            {
                "source_type": "post",
                "source_id": "n1",
                "index": -1,
                "quote": "把他挂出来，大家一起冲",
                "category": "不良信息-网暴",
                "risk_level": "High",
                "reasoning": "原始理由",
                "is_violation": True,
            }
        ]

        fake_law = {
            "matched_laws": [
                {
                    "category": "不良信息-网暴",
                    "article": "第十四条",
                    "risk_level": "Low",
                    "rule": "禁止组织围攻",
                    "full_desc": "禁止组织围攻",
                }
            ],
            "primary_law": "第十四条 禁止组织围攻",
            "law_reason": "命中规则",
        }

        with patch.object(agent, "finalize_candidates", return_value=(stage1_cases, 0)):
            with patch.object(agent, "_match_laws_for_case", return_value=fake_law):
                with patch.object(
                    agent,
                    "_invoke_evidence_chain",
                    return_value=agent._EvidenceEnhanceResult(
                        reasoning="增强后理由",
                        disposal_suggestion="限制/更改/屏蔽/删除相关内容的展示",
                        evidence_chain=["证据A"],
                    ),
                ):
                    result = agent.audit_post_packet(packet, event_name="事件A")

        self.assertTrue(result["is_violation"])
        post_case = result["violation_info"]["post_case"]
        self.assertEqual(post_case["risk_level"], "Low")

    def test_category_canonicalization_only_accepts_whitelist_exact_match(self):
        from Backend.app.services.compliance import AgentCompliance

        agent = AgentCompliance()
        self.assertEqual(
            agent._canonicalize_category("不实信息-造谣"),
            "不实信息-造谣",
        )
        self.assertEqual(agent._canonicalize_category("不实信息-造谣/煽动抵制"), "")
        self.assertEqual(agent._canonicalize_category("违法信息-虚假广告"), "")
        self.assertEqual(agent._canonicalize_category("违规营销-引导站外交易"), "")

    def test_unknown_category_should_not_default_to_web_violence(self):
        from Backend.app.services.compliance import AgentCompliance

        agent = AgentCompliance()
        self.assertEqual(agent._canonicalize_category("完全未知类别-foo"), "")

    def test_violation_floor_no_longer_uses_keyword_filtering(self):
        from Backend.app.services.compliance import AgentCompliance

        agent = AgentCompliance()
        self.assertTrue(
            agent._passes_violation_floor(
                {
                    "category": "不良信息-网暴",
                    "quote": "封杀吧",
                    "reasoning": "短句带有抵制色彩",
                }
            )
        )
        self.assertTrue(
            agent._passes_violation_floor(
                {
                    "category": "不实信息-造谣",
                    "quote": "这种博主就是割韭菜的，抵制这种人吧",
                    "reasoning": "对商业行为的负面评价与抵制呼吁",
                }
            )
        )
        self.assertFalse(
            agent._passes_violation_floor(
                {
                    "category": "",
                    "quote": "把他信息挂出来，大家一起冲",
                    "reasoning": "存在明确曝光隐私和组织围攻",
                }
            )
        )
        self.assertTrue(
            agent._passes_violation_floor(
                {
                    "category": "不良信息-网暴",
                    "quote": "把他信息挂出来，大家一起冲",
                    "reasoning": "存在明确曝光隐私和组织围攻",
                }
            )
        )

    def test_law_match_falls_back_to_unfiltered_search(self):
        from Backend.app.services.compliance import AgentCompliance

        agent = AgentCompliance()
        agent._repair_category_once_by_llm = lambda case, current: ""
        fake_doc = SimpleNamespace(
            metadata={
                "category": "不实信息-造谣",
                "article": "第十四条",
                "risk_level": "Medium",
                "full_desc": "编造传播未经证实信息",
            },
            page_content="编造并传播未经证实的信息，扰乱网络秩序。",
        )

        calls = []

        def fake_search(query, top_k=3, category_filter=None, use_hyde=False):
            calls.append((category_filter, use_hyde))
            if category_filter:
                return []
            return [fake_doc]

        with patch(
            "Backend.app.services.compliance.chroma_db.search_related_laws",
            side_effect=fake_search,
        ):
            result = agent._match_laws_for_case(
                {
                    "category": "不实信息-造谣/煽动抵制",
                    "quote": "这是造谣",
                    "reasoning": "断言式传播未经证实信息",
                }
            )

        self.assertNotEqual(result["primary_law"], "未匹配到明确条款")
        self.assertIn((None, False), calls)

    def test_law_match_rechecks_category_once_then_hits_filtered_search(self):
        from Backend.app.services.compliance import AgentCompliance

        agent = AgentCompliance()
        agent._repair_category_once_by_llm = lambda case, current: "不实信息-造谣"

        fake_doc = SimpleNamespace(
            metadata={
                "category": "不实信息-造谣",
                "article": "第十四条",
                "risk_level": "Medium",
                "full_desc": "编造传播未经证实信息",
            },
            page_content="编造并传播未经证实的信息，扰乱网络秩序。",
        )

        calls = []

        def fake_search(query, top_k=3, category_filter=None, use_hyde=False):
            calls.append((category_filter, use_hyde))
            if category_filter == "不良信息-网暴":
                return []
            if category_filter == "不实信息-造谣":
                return [fake_doc]
            return []

        with patch(
            "Backend.app.services.compliance.chroma_db.search_related_laws",
            side_effect=fake_search,
        ):
            result = agent._match_laws_for_case(
                {
                    "category": "不良信息-网暴",
                    "quote": "这是造谣",
                    "reasoning": "断言式传播未经证实信息",
                }
            )

        self.assertTrue(result["matched_laws"])
        self.assertIn(("不良信息-网暴", False), calls)
        self.assertIn(("不实信息-造谣", False), calls)
        self.assertIn("类别复核后改为", result["law_reason"])

    def test_law_match_without_vector_hit_returns_empty_and_should_pass(self):
        from Backend.app.services.compliance import AgentCompliance

        agent = AgentCompliance()
        agent._repair_category_once_by_llm = lambda case, current: ""

        with patch(
            "Backend.app.services.compliance.chroma_db.search_related_laws",
            return_value=[],
        ):
            result = agent._match_laws_for_case(
                {
                    "category": "不良信息-网暴",
                    "quote": "把他信息挂出来，大家一起冲",
                    "reasoning": "存在明确组织围攻导向",
                }
            )

        self.assertEqual(result["primary_law"], "")
        self.assertEqual(result["matched_laws"], [])
        self.assertIn("放行", result["law_reason"])

    def test_model_marked_case_not_blocked_by_keyword_floor(self):
        from Backend.app.services.compliance import AgentCompliance

        agent = AgentCompliance()
        packet = {
            "note_id": "n1",
            "content": "主贴内容",
            "source_keyword": "优思益",
            "audit_comment_items": [
                {
                    "comment_id": "c1",
                    "content": "封杀吧",
                    "db_id": "db1",
                }
            ],
        }

        stage1_cases = [
            {
                "source_type": "comment",
                "source_id": "c1",
                "index": 0,
                "quote": "封杀吧",
                "category": "不良信息-网暴",
                "risk_level": "Medium",
                "reasoning": "短句带有抵制色彩",
                "is_violation": True,
            }
        ]

        with patch.object(agent, "finalize_candidates", return_value=(stage1_cases, 0)):
            with patch.object(
                agent,
                "_match_laws_for_case",
                return_value={
                    "matched_laws": [
                        {
                            "category": "不良信息-网暴",
                            "article": "第十四条",
                            "risk_level": "Low",
                            "rule": "禁止组织围攻",
                            "full_desc": "禁止组织围攻",
                        }
                    ],
                    "primary_law": "第十四条 禁止组织围攻",
                    "law_reason": "命中规则",
                },
            ) as law_mock:
                with patch.object(
                    agent,
                    "_invoke_evidence_chain",
                    return_value=agent._EvidenceEnhanceResult(
                        reasoning="保留模型判定",
                        disposal_suggestion="限制/更改/屏蔽/删除相关内容的展示",
                        evidence_chain=["证据A"],
                    ),
                ):
                    result = agent.audit_post_packet(packet, event_name="优思益")

        self.assertTrue(result["is_violation"])
        self.assertEqual(len(result["violation_info"]["comment_cases"]), 1)
        self.assertEqual(result["violation_info"]["overall_risk_level"], "Low")
        self.assertEqual(result["violation_info"]["blocked_count"], 0)
        law_mock.assert_called_once()

    def test_repair_existing_violation_info_keeps_cases_without_keyword_filter(self):
        from Backend.app.services.compliance import AgentCompliance

        agent = AgentCompliance()
        with patch.object(
            agent,
            "_match_laws_for_case",
            return_value={
                "matched_laws": [
                    {
                        "category": "不良信息-网暴",
                        "article": "第十四条",
                        "risk_level": "Low",
                        "rule": "禁止组织围攻",
                        "full_desc": "禁止组织围攻",
                    }
                ],
                "primary_law": "第十四条 禁止组织围攻",
                "law_reason": "命中规则",
            },
        ):
            repaired = agent.repair_existing_violation_info(
                {
                    "is_post_violated": False,
                    "category": "",
                    "reasoning": "",
                    "post_case": None,
                    "comment_cases": [
                        {
                            "source_type": "comment",
                            "source_id": "c1",
                            "index": 0,
                            "quote": "封杀吧",
                            "category": "不良信息-网暴",
                            "risk_level": "Medium",
                            "reasoning": "有煽动倾向",
                            "disposal_suggestion": "删除",
                            "is_violation": True,
                        },
                        {
                            "source_type": "comment",
                            "source_id": "c2",
                            "index": 1,
                            "quote": "这种博主就是割韭菜的，抵制这种人吧",
                            "category": "不实信息-造谣",
                            "risk_level": "Medium",
                            "reasoning": "负面评价与抵制",
                            "disposal_suggestion": "删除",
                            "is_violation": True,
                        },
                    ],
                    "overall_risk_level": "Medium",
                    "matched_laws": [],
                    "evidence_report": {},
                    "violated_comments": [],
                }
            )

        self.assertFalse(repaired["is_post_violated"])
        self.assertEqual(len(repaired["comment_cases"]), 2)
        self.assertEqual(repaired["overall_risk_level"], "Low")

    def test_repair_existing_violation_info_drops_case_when_law_missing(self):
        from Backend.app.services.compliance import AgentCompliance

        agent = AgentCompliance()
        with patch(
            "Backend.app.services.compliance.chroma_db.search_related_laws",
            return_value=[],
        ):
            repaired = agent.repair_existing_violation_info(
                {
                    "is_post_violated": False,
                    "category": "",
                    "reasoning": "",
                    "post_case": None,
                    "comment_cases": [
                        {
                            "source_type": "comment",
                            "source_id": "c3",
                            "index": 2,
                            "quote": "把他信息挂出来，大家一起冲",
                            "category": "不良信息-网暴",
                            "risk_level": "High",
                            "reasoning": "存在组织围攻与隐私曝光引导",
                            "disposal_suggestion": "删除",
                            "is_violation": True,
                        }
                    ],
                    "overall_risk_level": "High",
                    "matched_laws": [],
                    "evidence_report": {},
                    "violated_comments": [],
                }
            )

        self.assertEqual(repaired["comment_cases"], [])
        self.assertEqual(repaired["matched_laws"], [])
        self.assertEqual(repaired["overall_risk_level"], "Low")


if __name__ == "__main__":
    unittest.main()

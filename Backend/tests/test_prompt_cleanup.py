import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_ROOT = PROJECT_ROOT / "Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from Backend.app.core import prompts, schemas


class PromptCleanupTests(unittest.TestCase):
    def test_preface_prompt_removes_old_sample_style(self):
        template = prompts.AGENT_E_PREFACE_TEMPLATE
        self.assertNotIn("范文参考", template)
        self.assertNotIn("其一，", template)
        self.assertNotIn("其二，", template)
        self.assertNotIn("其三，", template)
        self.assertIn("压缩型新闻综述/评论前言", template)
        self.assertIn("先拎住本期主轴", template)
        self.assertIn("议题A/议题B/议题C", template)
        self.assertIn("像成熟新闻作者写月度综述开篇", template)
        self.assertIn("坏句式黑名单", template)
        self.assertIn("把读者带到门口", template)
        self.assertIn("整体前言总长度建议控制在 260-380 字之间", template)
        self.assertIn("严格 1-2 段", template)

    def test_preface_schema_uses_only_report_period_and_paragraphs(self):
        fields = set(schemas.PrefaceSection.model_fields.keys())
        self.assertEqual(fields, {"report_period", "paragraphs"})

        description = schemas.PrefaceSection.model_fields["paragraphs"].description
        self.assertIn("压缩型新闻综述前言", description)
        self.assertIn("不得展开成正文分析", description)

    def test_preface_prompt_uses_paragraphs_as_primary_output(self):
        template = prompts.AGENT_E_PREFACE_TEMPLATE
        self.assertIn("`paragraphs`", template)
        self.assertIn("输出 1-2 段", template)
        self.assertIn("主输出字段只有 `paragraphs`", template)
        self.assertNotIn("overview", template)
        self.assertNotIn("characteristics", template)

    def test_quality_score_schema_removes_old_score_dimensions(self):
        description = schemas.QualityScore.model_fields["completeness"].description
        self.assertNotIn("完整性得分", description)
        self.assertNotIn("0-10", description)

    def test_active_prompts_drop_old_chief_expert_roleplay(self):
        active_templates = [
            prompts.AGENT_B_REDUCE_TEMPLATE,
            prompts.AGENT_D_FORECAST_TEMPLATE,
            prompts.AGENT_E_PREFACE_TEMPLATE,
        ]
        for template in active_templates:
            self.assertNotIn("国家级智库", template)
            self.assertNotIn("首席", template)

    def test_writing_style_guide_discourages_bureaucratic_tone(self):
        guide = prompts._WRITING_STYLE_GUIDE
        self.assertNotIn("保持严肃、专业、客观的风格", guide)
        self.assertIn("不要写成公文", guide)
        self.assertIn("成品感", guide)
        self.assertIn("套话", guide)
        self.assertIn("标题和开头要有钩子", guide)
        self.assertIn("非专业读者读得下去", guide)
        self.assertIn("稳中带锋", guide)

    def test_compliance_prompts_emphasize_precision_over_overblocking(self):
        screen_prompt = prompts.AGENT_C_SCREEN_TEMPLATE
        audit_prompt = prompts.AGENT_C_AUDIT_TEMPLATE
        final_prompt = prompts.AGENT_C_FINAL_TEMPLATE
        evidence_prompt = prompts.AGENT_C_EVIDENCE_TEMPLATE
        recheck_prompt = prompts.AGENT_C_CATEGORY_RECHECK_TEMPLATE

        self.assertEqual(screen_prompt, prompts.LEGACY_UNUSED_PROMPT)
        self.assertEqual(final_prompt, audit_prompt)
        self.assertIn("宁可少判，不可乱判", audit_prompt)
        self.assertIn("category` 只能从输入白名单中选择", audit_prompt)
        self.assertIn("“封杀吧”“割韭菜”“抠门/抠搜”", audit_prompt)
        self.assertIn("事件标题", audit_prompt)
        self.assertIn("只做“违规与否 + 类别 + 判定依据”", audit_prompt)
        self.assertIn("禁止输出 `disposal_suggestion`", audit_prompt)
        self.assertNotIn("- source_type:", audit_prompt)
        self.assertNotIn("- source_id:", audit_prompt)
        self.assertNotIn("- risk_level:", audit_prompt)
        self.assertIn("不是重新判定是否违规", evidence_prompt)
        self.assertIn("不得改写 is_violation 结论", evidence_prompt)
        self.assertIn("disposal_suggestion 必须且只能", evidence_prompt)
        self.assertIn("laws_json", evidence_prompt)
        self.assertIn("只有以下三项同时成立", audit_prompt)
        self.assertIn("能唯一映射到输入白名单中的一个类别", audit_prompt)
        self.assertIn("若 `is_violation=true`，`quote` 不得为空", audit_prompt)
        self.assertIn("`reasoning` 必须最多两句", audit_prompt)
        self.assertIn("第一句必须说明命中的明确行为", audit_prompt)
        self.assertIn("第二句必须说明“且可稳定归入【category】”", audit_prompt)
        self.assertIn("公共事件的追责、质问、道德批评", audit_prompt)
        self.assertIn("怎么直播平台都不查验", audit_prompt)
        self.assertIn("这是纵容犯罪", audit_prompt)
        self.assertIn("CONTEXT & ENFORCEMENT VIEW", audit_prompt)
        self.assertIn("社区治理/网络执法", audit_prompt)
        self.assertIn("必须优先结合事件语境判断", audit_prompt)
        self.assertIn("PUBLIC-DISCUSSION SAFE HARBOR", audit_prompt)
        self.assertIn("SHORT-COMMENT LENIENCY", audit_prompt)
        self.assertIn("ATTACK-TYPE LIMIT", audit_prompt)
        self.assertIn("原则上不直接视为“人身攻击对象”", audit_prompt)
        self.assertIn("步骤1：先识别语境", audit_prompt)
        self.assertIn("步骤2：再识别对象", audit_prompt)
        self.assertIn("步骤2.5：若对象不明确", audit_prompt)
        self.assertIn("步骤4：仅当对象明确为普通用户或明确个人时", audit_prompt)
        self.assertIn("太无耻了点", audit_prompt)
        self.assertIn("太贱了", audit_prompt)
        self.assertIn("傻子买单", audit_prompt)
        self.assertIn("你搁这左右脑互搏呢", audit_prompt)
        self.assertIn("真不要脸", audit_prompt)
        self.assertIn("吃相真难看", audit_prompt)
        self.assertIn("必须使用以下固定句式", audit_prompt)
        self.assertIn(
            "`不实信息-造谣` 仅在文本本身捏造或断言具体事实时成立", audit_prompt
        )
        self.assertIn(
            "`不良信息-网暴` 仅在存在明确对象、明确攻击行为或组织化煽动时成立",
            audit_prompt,
        )
        self.assertIn("不得新增新的违规事实、对象、动机、后果", evidence_prompt)
        self.assertIn("evidence_chain 只能拆解、重述或归纳已有证据", evidence_prompt)
        self.assertIn("reasoning 应为 1-2 句", evidence_prompt)
        self.assertIn("唯一类别", recheck_prompt)
        self.assertIn("如果证据不足、类别边界模糊、可能对应多个类别", recheck_prompt)
        self.assertIn("EXTRA RULE", recheck_prompt)
        self.assertIn("公共事件追责/消费吐槽/平台批评/道德谴责", recheck_prompt)

    def test_forecast_prompt_requires_reader_facing_paragraph_rather_than_field_list(
        self,
    ):
        template = prompts.AGENT_D_FORECAST_TEMPLATE
        self.assertIn("summary_paragraph", template)
        self.assertIn("你不是在填写风控台账", template)
        self.assertIn("可传播的瞬间", template)
        self.assertIn("三拍式", template)
        self.assertIn("起火场景", template)
        self.assertIn("外溢方向", template)
        self.assertIn("三拍式是内部节奏要求，不是显性模板", template)
        self.assertIn(
            "首句禁止以“当前/未来/这一风险/这一议题/值得关注/需要警惕/可能出现”",
            template,
        )
        self.assertIn("禁止用以下句式充当 summary_paragraph 的骨架", template)
        self.assertIn(
            "读者看到的 `summary_paragraph` 应该像一段成熟专栏中的预判", template
        )
        self.assertIn("结尾必须明确指出将升级成哪类更大的公共议题", template)

    def test_forecast_schema_prefers_scene_and_evolution_path(self):
        point_fields = schemas.ForecastPoint.model_fields
        topic_fields = schemas.ForecastTopic.model_fields

        self.assertIn("audience", point_fields)
        self.assertIn("scene", point_fields)
        self.assertIn("evolution_path", point_fields)
        self.assertIn("summary_paragraph", point_fields)
        self.assertIn("main_tension", topic_fields)

        point_scene_desc = point_fields["scene"].description
        point_path_desc = point_fields["evolution_path"].description
        point_summary_desc = point_fields["summary_paragraph"].description
        topic_tension_desc = topic_fields["main_tension"].description

        self.assertIn("具体、可感知", point_scene_desc)
        self.assertIn("先因为什么起", point_path_desc)
        self.assertIn("首句必须从具体、可传播的起火场景切入", point_summary_desc)
        self.assertIn("不能机械履约", point_summary_desc)
        self.assertIn("更大的公共议题", point_summary_desc)
        self.assertIn("最核心的矛盾", topic_tension_desc)

    def test_deep_read_prompt_pushes_for_hook_and_non_template_analysis(self):
        template = prompts.AGENT_B_REDUCE_TEMPLATE
        self.assertIn("标题要抓住矛盾和情绪", template)
        self.assertIn("为什么偏偏在这个节点炸开", template)
        self.assertIn("禁止使用“折射出、引发广泛关注、值得警惕、值得深思”", template)
        self.assertIn("面向真实读者", template)
        self.assertIn("还不够具体", template)

    def test_event_overview_requires_natural_paragraph_not_labelized_blocks(self):
        template = prompts.AGENT_B_REDUCE_TEMPLATE
        description = schemas.EventAnalysisReport.model_fields[
            "event_overview"
        ].description
        self.assertIn("自然段", template)
        self.assertIn("不要写成“研判周期：”“核心事实：”", template)
        self.assertIn("关键节点与处置：", template)
        self.assertIn("讨论点包括：", template)
        self.assertIn("媒体与平台态度：", template)
        self.assertIn("不要使用“事件概况：”开头", description)
        self.assertIn("输出为1-2段连贯文字", description)

    def test_deep_read_reduce_requires_timeline_digest_and_narrative_progression(self):
        template = prompts.AGENT_B_REDUCE_TEMPLATE
        self.assertIn("timeline_digest", template)
        self.assertIn("事件发展还原", template)
        self.assertIn("先写触发点", template)
        self.assertIn("再写放大过程", template)
        self.assertIn("再写争议外溢", template)
        self.assertIn("最后写截至本周期的状态", template)
        self.assertIn("禁止按“争议点A、争议点B、争议点C”横向罗列信息", template)
        self.assertIn("若给定时间线混乱、互相冲突或信息不足，必须主动自组织", template)
        self.assertIn("不得硬凑伪时间线", template)
        self.assertIn("坏句式黑名单", template)
        self.assertIn("事件概况如下", template)

        overview_desc = schemas.EventAnalysisReport.model_fields[
            "event_overview"
        ].description
        self.assertIn("若时间线混乱、冲突或缺失", overview_desc)
        self.assertIn("自组织成合理段落", overview_desc)

    def test_deep_read_opinion_prefix_and_depth_non_repetition_constraints(self):
        template = prompts.AGENT_B_REDUCE_TEMPLATE
        self.assertIn("第1条必须以“主流声浪：”开头", template)
        self.assertIn("第2条必须以“次生质疑：”开头", template)
        self.assertIn("第3条必须以“深层情绪：”开头", template)
        self.assertIn("第4条必须以“对立博弈：”开头", template)
        self.assertIn("不得重复出现具体时间点", template)

        opinions_desc = schemas.EventAnalysisReport.model_fields[
            "public_opinions"
        ].description
        depth_desc = schemas.EventAnalysisReport.model_fields[
            "depth_analysis"
        ].description
        self.assertIn("主流声浪：", opinions_desc)
        self.assertIn("对立博弈：", opinions_desc)
        self.assertIn("不得重复具体时间点", depth_desc)

    def test_map_schema_includes_trigger_and_propagation_fields(self):
        self.assertIn("trigger_summary", schemas.PostOpinionSummary.model_fields)
        self.assertIn("propagation_hint", schemas.PostOpinionSummary.model_fields)

    def test_legacy_prompts_are_explicitly_marked_unused(self):
        self.assertEqual(
            prompts.AGENT_C_ANALYSIS_TEMPLATE, prompts.LEGACY_UNUSED_PROMPT
        )
        self.assertEqual(prompts.AGENT_C_BATCH_TEMPLATE, prompts.LEGACY_UNUSED_PROMPT)
        self.assertEqual(prompts.AGENT_C_SCREEN_TEMPLATE, prompts.LEGACY_UNUSED_PROMPT)
        self.assertEqual(
            prompts.AGENT_D_REACT_SYSTEM_PROMPT, prompts.LEGACY_UNUSED_PROMPT
        )
        self.assertNotEqual(
            prompts.AGENT_C_EVIDENCE_TEMPLATE, prompts.LEGACY_UNUSED_PROMPT
        )


if __name__ == "__main__":
    unittest.main()

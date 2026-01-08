import os
from datetime import datetime
from typing import Dict, Any, List

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.core.logger import logger
from app.core.schemas import PrefaceSection
from app.core.prompts import AGENT_E_PREFACE_TEMPLATE


class AgentReport:
    """
    Agent E: 报告总编
    职责：撰写前言 -> 生成热点榜单表格 -> 组装全文 -> 生成 Markdown
    """

    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            openai_api_key=settings.ZHIPU_API_KEY,
            openai_api_base=settings.LLM_BASE_URL,
            temperature=0.5,
        )
        # self.preface_parser = JsonOutputParser(pydantic_object=PrefaceSection) (已弃用)

    def generate_full_report(self, state_data: Dict[str, Any]) -> Dict[str, str]:
        """
        生成报告全流程
        """
        logger.info("📝 [Agent E] 正在统筹全篇，撰写舆情报告...")

        # 0. 研判周期（强制使用用户输入，禁止模型杜撰年份）
        start_date = (state_data.get("start_date") or "").strip()
        end_date = (state_data.get("end_date") or "").strip()
        if start_date and end_date:
            report_period = f"{start_date} 至 {end_date}"
        elif start_date or end_date:
            report_period = (
                f"{start_date or '开始时间未知'} 至 {end_date or '结束时间未知'}"
            )
        else:
            report_period = "本期（默认最近24小时）"

        # 1. 准备素材
        # 🔥 获取 Agent A 的完整榜单 (用于生成表格)
        core_events = state_data.get("core_events", [])

        # 🔥 获取 Agent B 分析完的事件 (现在 Nodes.py 改完后这里会有 5 个)
        analyzed_events = state_data.get("analyzed_events", [])

        audit_results = state_data.get("audit_results", [])
        trend_report = state_data.get("trend_forecast", {})

        # 2. 生成前言 (更高密度的素材摘要：事件榜单 + 少量深读摘要)
        top_events_lines = []
        for i, e in enumerate(core_events[:15]):
            name = e.get("event_name") or e.get("topic") or "未知"
            heat = e.get("total_heat", 0)
            kws = e.get("related_keywords") or e.get("keywords") or []
            kw_preview = "、".join([str(x) for x in kws[:4]])
            top_events_lines.append(f"{i+1}. {name}（热度{heat}） 关键词: {kw_preview}")
        top_events_str = (
            "\n".join(top_events_lines) if top_events_lines else "（无事件榜单数据）"
        )

        deep_read_lines = []
        for i, e in enumerate(analyzed_events[:8]):
            name = e.get("event_name") or e.get("topic") or "未知"
            overview = (e.get("opinion_report") or {}).get("event_overview")
            overview = (overview or "").strip()
            if overview:
                deep_read_lines.append(f"- {name}: {overview}")
        deep_read_str = (
            "\n".join(deep_read_lines) if deep_read_lines else "（无深读摘要）"
        )

        events_str = (
            f"【研判周期】{report_period}\n"
            f"【热点榜单Top15】\n{top_events_str}\n\n"
            f"【重点深读摘要Top8】\n{deep_read_str}"
        )

        # 当 LLM 未标记为违规但 RAG 命中条款（matched_laws）时，也应当纳入报告展示。
        violations = []
        for r in audit_results:
            info = r.get("violation_info") or {}
            evidence = info.get("evidence_report") or {}
            # 判断为需展示的违规项的条件：
            # 1) 明确标记为违规（is_violation）
            # 2) 或者 RAG 命中条款（matched_laws 非空）
            # 3) 或者 LLM 生成了证据推理(reasoining) or disposal_suggestion
            if (
                r.get("is_violation")
                or (info.get("matched_laws") or [])
                or evidence.get("reasoning")
                or evidence.get("disposal_suggestion")
            ):
                violations.append(r)

        # 🔥 升级：生成更丰富的合规摘要，供 Agent E 写前言
        if not violations:
            audit_str = "本期未发现高风险违规内容，舆论场整体平稳。"
        else:
            # 统计违规类型
            cat_counts = {}
            for v in violations:
                info = v.get("violation_info", {})
                # 统计主贴
                if info.get("is_post_violated"):
                    cat = info.get("category", "其他")
                    cat_counts[cat] = cat_counts.get(cat, 0) + 1
                # 统计评论
                for c in info.get("violated_comments", []):
                    cat = c.get("category", "其他")
                    cat_counts[cat] = cat_counts.get(cat, 0) + 1

            top_cats = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            cat_str = "、".join([f"{k}({v}条)" for k, v in top_cats])

            audit_str = f"共发现违规内容 {len(violations)} 条。主要集中在：{cat_str}。"

            # 摘录典型案例
            if violations:
                typical = violations[0].get("violation_info", {})
                reason = typical.get("reasoning") or "涉及敏感内容"
                audit_str += f" 典型案例涉及：{reason}。"

        # 🔥 适配新版 TrendForecastReport (topics 列表)
        topics = trend_report.get("topics", [])
        if topics:
            # 提取每个议题的标题作为摘要
            topic_titles = [t.get("topic_name", "未知议题") for t in topics]
            trend_str = f"下月重点关注议题：{'; '.join(topic_titles)}。"
        else:
            trend_str = "下月定调: 暂无明确预测数据"

        preface = self._generate_preface(
            report_period=report_period,
            start_date=start_date,
            end_date=end_date,
            e_str=events_str,
            a_str=audit_str,
            t_str=trend_str,
        )

        # 二次兜底：强制覆盖 report_period，避免模型乱写年份
        try:
            preface.report_period = report_period
        except Exception:
            pass

        # 3. 组装 Markdown (传入 core_events 用于表格)
        category = state_data.get("category", "综合")
        md_content = self._assemble_markdown(
            preface, core_events, analyzed_events, violations, trend_report, category
        )

        # 4. 保存 Markdown 文件 (不再生成 PDF，建议用 Typora 等工具打开 .md 导出)
        md_filename = f"舆情研判_{category}_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        md_path = self._save_markdown(md_content, md_filename)

        return {"markdown": md_content, "md_path": md_path}

    def _generate_preface(
        self,
        report_period: str,
        start_date: str,
        end_date: str,
        e_str: str,
        a_str: str,
        t_str: str,
    ) -> PrefaceSection:
        """调用 LLM 生成前言"""
        try:
            # 🔥 升级：使用 with_structured_output
            structured_llm = self.llm.with_structured_output(PrefaceSection)
            prompt = ChatPromptTemplate.from_template(AGENT_E_PREFACE_TEMPLATE)

            chain = prompt | structured_llm

            return chain.invoke(
                {
                    "report_period": report_period,
                    "start_date": start_date,
                    "end_date": end_date,
                    "events_summary": e_str,
                    "audit_summary": a_str,
                    "trend_forecast": t_str,
                }
            )
        except Exception as e:
            logger.error(f"❌ 前言生成失败: {e}")
            return PrefaceSection(
                report_period="本期",
                overview="（生成异常）",
                characteristics=["（生成异常）"],
                compliance_perspective="（生成异常）",
                trend_connection="（生成异常）",
                conclusion="（生成异常）",
            )

    def _assemble_markdown(
        self,
        p: PrefaceSection,
        core_events: List,
        b_events: List,
        c_violations: List,
        d_trend: Dict,
        category: str = "综合",
    ) -> str:
        """
        拼装最终报告 (Markdown 格式)
        """
        date_str = datetime.now().strftime("%Y年%m月%d日")

        def _normalize_body_text(s: Any) -> str:
            """归一化 LLM 输出，避免字面量 \\n 导致 Markdown 分段失效。"""
            if s is None:
                return ""
            text = str(s)
            # 统一真实换行
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            # 将字面量 "\\n" 还原成真实换行
            text = text.replace("\\n", "\n")
            # 清理制表符，避免渲染器异常（正文中用空格即可）
            text = text.replace("\t", "    ")
            # 过滤其余 ASCII 控制字符（保留换行）
            text = "".join(
                ch for ch in text if (ch == "\n" or (ch >= " " and ch != "\x7f"))
            )
            # 🔥 二次去emoji（保险起见）
            # (这里可以加正则去 emoji，暂时先不加以免引入额外依赖，依靠 Prompt 约束)
            return text.strip()

        # ==============================================================================
        # 内嵌样式（使 Markdown 在各种渲染器中都有良好的表格显示效果）
        # ==============================================================================
        css_style = """<style>
/* 内容安全审核报告样式 */
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif; line-height: 1.8; color: #333; max-width: 1200px; margin: 0 auto; padding: 32px; }
h1 { font-size: 26px; font-weight: 700; color: #1a1a1a; text-align: center; margin: 24px 0; padding-bottom: 16px; border-bottom: 2px solid #2563eb; }
h2 { font-size: 20px; font-weight: 600; color: #1a1a1a; margin: 40px 0 20px; padding: 10px 14px; background: #f0f7ff; border-left: 4px solid #2563eb; border-radius: 0 6px 6px 0; }
h3 { font-size: 17px; font-weight: 600; color: #333; margin: 32px 0 16px; padding-bottom: 8px; border-bottom: 1px solid #e5e7eb; }
h4 { font-size: 16px; font-weight: 600; color: #1f2937; margin: 28px 0 14px; }
blockquote { background: #fafafa; border-left: 3px solid #ddd; padding: 14px 20px; margin: 16px 0; border-radius: 0 6px 6px 0; color: #555; }
hr { border: none; border-top: 1px solid #e0e0e0; margin: 32px 0; }
/* 表格 */
table { width: 100%; border-collapse: collapse; margin: 16px 0 28px; font-size: 13px; border: 1px solid #d1d5db; }
thead { background: #475569; }
th { padding: 10px 12px; text-align: left; font-weight: 600; font-size: 13px; color: #fff; border: 1px solid #475569; white-space: nowrap; }
tbody tr:nth-child(odd) { background: #fff; }
tbody tr:nth-child(even) { background: #f8fafc; }
td { padding: 10px 12px; text-align: left; color: #374151; vertical-align: top; line-height: 1.5; border: 1px solid #e5e7eb; }
strong { color: #1a1a1a; }
em { color: #666; }
@media print { body { padding: 16px; font-size: 12px; } table { page-break-inside: avoid; font-size: 11px; } th, td { padding: 6px 8px; } }
</style>

"""

        # ==============================================================================
        # 1. 封面与前言 (Cover & Preface)
        # ==============================================================================
        title_suffix = f"（{category}）" if category and category != "综合" else ""
        md = css_style
        md += f"# 内容安全审核与分析报告{title_suffix}\n\n"
        md += f"**报告日期**：{date_str}\n\n"
        md += f"**研判周期**：{p.report_period}\n\n"
        md += "---\n\n"

        md += "## 前言：舆情态势综述\n\n"

        # (1) 开篇综述
        md += f"{_normalize_body_text(p.overview)}\n\n"

        # (2) 核心特征 (段落渲染)
        md += "**总体来看，当下舆情生态呈现以下核心特征：**\n\n"
        for i, char_text in enumerate(p.characteristics):
            prefix = ["其一", "其二", "其三", "其四", "其五"]
            label = prefix[i] if i < len(prefix) else f"特征{i+1}"
            # 移除可能重复的 "其一，" 前缀
            clean_text = char_text.replace(f"{label}，", "").replace(f"{label}：", "")
            # 🔥 改为段落式，而非列表
            md += f"**{label}，{clean_text}**\n\n"
        md += "\n"

        # (3) 违规透视
        md += f"**【违规风险透视】**\n\n{_normalize_body_text(p.compliance_perspective)}\n\n"

        # (4) 时空承接
        md += f"**【时空趋势承接】**\n\n{_normalize_body_text(p.trend_connection)}\n\n"

        # (5) 结语
        md += f"**{_normalize_body_text(p.conclusion)}**\n\n"

        md += "<div style='page-break-after: always;'></div>\n\n"  # 强制分页

        # ==============================================================================
        # 2. 本期热点舆情总览 (Overview Table)
        # ==============================================================================
        md += "## 第一部分：本期热点舆情总览\n\n"
        md += f"基于全网大数据监测，本期（{p.report_period}）核心热点事件汇总如下：\n\n"

        md += "| 序号 | 时间 | 事件名称 | 热度值 |\n"
        md += "| :---: | :---: | :--- | :---: |\n"

        # 🔥 辅助函数：清理 # 号
        def _clean_hashtag(s: str) -> str:
            """清理字符串中的 # 号"""
            if not s:
                return s
            return s.strip().strip("#").strip()

        if not core_events:
            md += "| - | - | 暂无数据 | - |\n"
        else:
            # 🔥 去重：按 event_name 去重，保留首次出现的（热度最高的）
            seen_names = set()
            unique_events = []
            for evt in core_events:
                event_name = evt.get("event_name") or evt.get("topic") or "未知"
                # 清理 # 号后再去重
                event_name_clean = _clean_hashtag(event_name)
                if event_name_clean not in seen_names:
                    seen_names.add(event_name_clean)
                    unique_events.append(evt)

            # 取前 20 条展示（若不足 20 条则展示全部）
            for i, evt in enumerate(unique_events[:20]):
                raw_time = str(evt.get("created_at", ""))[:10]
                heat_val = evt.get("total_heat", 0)
                heat_str = (
                    f"{heat_val/10000:.1f}万" if heat_val > 10000 else str(heat_val)
                )
                # 🔥 直接使用热搜标题，清理 # 号
                event_title = _clean_hashtag(
                    evt.get("event_name") or evt.get("topic") or "未知"
                )

                # 表格内容转义，防止 Markdown 错乱
                event_title = event_title.replace("|", r"\|")

                md += f"| {i+1} | {raw_time} | {event_title} | {heat_str} |\n"

        md += "<div style='page-break-after: always;'></div>\n\n"

        # ==============================================================================
        # 3. 重点舆情深读 (Deep Analysis)
        # ==============================================================================
        md += "## 第二部分：重点舆情深读\n\n"
        if not b_events:
            md += "（本期无重点事件）\n"

        # 🔥 去重：按 event_name 去重
        seen_b_names = set()
        unique_b_events = []
        for e in b_events:
            event_name = e.get("event_name") or e.get("topic") or "未知"
            if event_name not in seen_b_names:
                seen_b_names.add(event_name)
                unique_b_events.append(e)

        for i, e in enumerate(unique_b_events):
            r = e.get("opinion_report", {})
            # 🔥 优先使用原始热搜标题 raw_title，否则使用 event_name
            event_title = _clean_hashtag(
                e.get("raw_title") or e.get("event_name") or e.get("topic") or "未知"
            )

            md += f"### {i+1}. 事件：《{event_title}》\n\n"

            # (1) 事件概况 - 🔥 改为 h4 + 段落，与其他部分样式一致
            md += f"#### 事件概况\n\n"
            md += f"{_normalize_body_text(r.get('event_overview', '暂无概况'))}\n\n"

            # (2) 舆论观点画像
            md += f"#### 舆论观点画像\n\n"
            ops = r.get("public_opinions", [])
            if isinstance(ops, list):
                for op in ops:
                    md += f"- {_normalize_body_text(op)}\n"
            else:
                md += f"{_normalize_body_text(ops)}\n"
            md += "\n"

            # (3) 深度研判
            md += f"#### 深度研判\n\n"
            md += f"{_normalize_body_text(r.get('depth_analysis', '暂无分析'))}\n\n"

            md += "---\n\n"

        md += "<div style='page-break-after: always;'></div>\n\n"

        # ==============================================================================
        # 4. 未来趋势与战略预警 (Forecast)
        # ==============================================================================
        md += "## 第三部分：未来趋势与战略预警\n\n"

        # 适配新版 Schema (TrendForecastReport: target_month, topics)
        topics = d_trend.get("topics", [])

        if topics:
            md += f"**研判周期**：{d_trend.get('target_month', '下月')}\n\n"

            for i, topic in enumerate(topics):
                title = topic.get("topic_name", "重点议题")
                md += f"### {i+1}. {title}\n\n"

                # 背景
                bg = topic.get("background")
                if bg:
                    md += f"> **背景导语**：{_normalize_body_text(bg)}\n\n"

                # 风险点
                points = topic.get("points", [])
                for point in points:
                    sub = point.get("subtitle", "")
                    content = point.get("content", "")
                    # 移除可能重复的编号
                    md += f"#### {sub}\n"
                    md += f"{_normalize_body_text(content)}\n\n"
        else:
            md += "（暂无预测数据）\n"

        md += "\n<div style='page-break-after: always;'></div>\n\n"

        # ==============================================================================
        # 5. 附录：违规数据监测 (Appendix)
        # ==============================================================================
        md += "## 附录：违规数据监测\n\n"
        if not c_violations:
            md += "本期未检出需要处置的违规内容。\n"
            return md

        def _esc_cell(s: Any) -> str:
            if s is None:
                return ""

            # Markdown 表格单元格净化：
            # - 转义竖线，避免意外拆列
            # - 将所有换行统一为 <br>，避免意外断行
            # - 移除/替换控制字符（尤其是 \r、\t），避免渲染器异常
            text = str(s)

            # 先统一换行
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            text = text.replace("\n", "<br>")

            # 制表符会导致“看起来像 TSV/表格行”并影响渲染
            text = text.replace("\t", " ")

            # 转义 Markdown 表格分隔符
            text = text.replace("|", r"\|")

            # 过滤其余 ASCII 控制字符（保留常用空格）
            text = "".join(ch for ch in text if (ch >= " " and ch != "\x7f"))

            return text.strip()

        total_posts = len(c_violations)
        total_violated_comments = 0
        risk_counts: Dict[str, int] = {}
        category_counts: Dict[str, int] = {}
        event_post_counts: Dict[str, int] = {}
        event_comment_counts: Dict[str, int] = {}
        law_counts: Dict[str, int] = {}
        suggestion_counts: Dict[str, int] = {}

        for v in c_violations:
            info = v.get("violation_info") or {}
            event_name = v.get("event_name") or "未知"

            violated_comments = info.get("violated_comments") or []
            total_violated_comments += len(violated_comments)

            overall_risk = (
                info.get("overall_risk_level")
                or (info.get("evidence_report") or {}).get("overall_risk_level")
                or "Low"
            )
            risk_counts[overall_risk] = risk_counts.get(overall_risk, 0) + 1

            event_post_counts[event_name] = event_post_counts.get(event_name, 0) + 1
            event_comment_counts[event_name] = event_comment_counts.get(
                event_name, 0
            ) + len(violated_comments)

            # 违规类别统计：优先用 evidence_report.violated_categories（更稳定），否则退化到评论项
            violated_cats = (info.get("evidence_report") or {}).get(
                "violated_categories"
            )
            if isinstance(violated_cats, list) and violated_cats:
                for cat in violated_cats:
                    if not cat:
                        continue
                    category_counts[cat] = category_counts.get(cat, 0) + 1
            else:
                for it in violated_comments:
                    cat = (it or {}).get("category") or "其他"
                    category_counts[cat] = category_counts.get(cat, 0) + 1

            # 条款引用统计：强制使用检索到的数据库 metadata (matched_laws)，不使用 LLM 生成的 evidence_report.cited_laws
            for law in info.get("matched_laws") or []:
                cat = (law or {}).get("category") or "未知标签"
                article = (law or {}).get("article") or "未知条款"
                key = f"{cat} / {article}"
                law_counts[key] = law_counts.get(key, 0) + 1

            suggestion = (info.get("evidence_report") or {}).get("disposal_suggestion")
            if suggestion:
                s = _esc_cell(suggestion)
                suggestion_counts[s] = suggestion_counts.get(s, 0) + 1

        md += f"本期共检出疑似违规帖子 **{total_posts}** 条，涉及违规评论 **{total_violated_comments}** 条。\n\n"

        # --- 违规态势总结 ---
        md += "### 违规态势概述\n\n"

        # 风险等级分析
        high_cnt = risk_counts.get("High", 0)
        medium_cnt = risk_counts.get("Medium", 0)
        low_cnt = risk_counts.get("Low", 0)

        if high_cnt > 0:
            risk_summary = (
                f"本期违规内容中，**高风险(High)**占 {high_cnt} 条，需重点关注处置；"
            )
        else:
            risk_summary = "本期未检出高风险(High)级别违规内容；"

        if medium_cnt > 0:
            risk_summary += f"**中风险(Medium)**占 {medium_cnt} 条；"
        if low_cnt > 0:
            risk_summary += f"**低风险(Low)**占 {low_cnt} 条。"

        md += f"{risk_summary}\n\n"

        # 主要违规领域分析
        if category_counts:
            top3_cats = sorted(
                category_counts.items(), key=lambda x: x[1], reverse=True
            )[:3]
            cat_analysis = (
                "从违规类型分布来看，主要集中在："
                + "、".join([f"**{cat}**({cnt}次)" for cat, cnt in top3_cats])
                + "。"
            )
            md += f"{cat_analysis}\n\n"

        # 主要涉事事件分析
        if event_post_counts:
            top3_events = sorted(
                event_post_counts.items(), key=lambda x: x[1], reverse=True
            )[:3]
            event_analysis = (
                "违规内容主要涉及以下事件："
                + "、".join([f"**{ename}**({cnt}条)" for ename, cnt in top3_events])
                + "。"
            )
            md += f"{event_analysis}\n\n"

        md += "---\n\n"

        # (1) 风险等级分布
        md += "### 1) 风险等级分布\n\n"
        md += "| 风险等级 | 帖子数 |\n| :---: | :---: |\n"
        for level in ["High", "Medium", "Low"]:
            md += f"| {level} | {risk_counts.get(level, 0)} |\n"
        other_levels = sorted(
            [k for k in risk_counts.keys() if k not in {"High", "Medium", "Low"}]
        )
        for level in other_levels:
            md += f"| {_esc_cell(level)} | {risk_counts.get(level, 0)} |\n"
        md += "\n"

        # (2) 违规类别分布（全量）
        md += "### 2) 违规类别分布（全量）\n\n"
        md += "| 违规类别 | 次数 |\n| :--- | :---: |\n"
        for cat, cnt in sorted(
            category_counts.items(), key=lambda x: x[1], reverse=True
        ):
            md += f"| {_esc_cell(cat)} | {cnt} |\n"
        md += "\n"

        # (3) 涉及事件分布（全量）
        md += "### 3) 涉及事件分布（全量）\n\n"
        md += "| 事件名称 | 违规帖子数 | 违规评论数 |\n| :--- | :---: | :---: |\n"
        for ename, cnt in sorted(
            event_post_counts.items(), key=lambda x: x[1], reverse=True
        ):
            md += f"| {_esc_cell(ename)} | {cnt} | {event_comment_counts.get(ename, 0)} |\n"
        md += "\n"

        # (4) 引用条款分布（全量）
        md += "### 4) 引用条款分布（全量）\n\n"
        if law_counts:
            md += "| 条款（标签 / 条款） | 次数 |\n| :--- | :---: |\n"
            for key, cnt in sorted(
                law_counts.items(), key=lambda x: x[1], reverse=True
            ):
                md += f"| {_esc_cell(key)} | {cnt} |\n"
            md += "\n"
        else:
            md += "（本期未生成可统计的条款引用数据）\n\n"

        # (5) 案例明细（按事件分组展示）
        md += "### 5) 案例明细（按事件分组）\n\n"

        # 按事件分组
        events_violations: Dict[str, List] = {}
        for v in c_violations:
            ename = v.get("event_name") or "未知"
            if ename not in events_violations:
                events_violations[ename] = []
            events_violations[ename].append(v)

        event_num = 0  # 事件序号
        case_num = 0  # 全局案例序号
        for event_name, violations in events_violations.items():
            event_num += 1
            md += f"#### {event_num}. {_esc_cell(event_name)}\n\n"
            # 6列表格：序号 | 风险 | 违规内容 | 判定理由 | 违反条款 | 处置建议
            md += "| 序号 | 风险 | 违规内容 | 判定理由 | 违反条款 | 处置建议 |\n"
            md += "| :---: | :---: | :--- | :--- | :--- | :--- |\n"

            for v in violations:
                case_num += 1
                info = v.get("violation_info") or {}
                if info is None:
                    continue

                risk = (
                    info.get("overall_risk_level")
                    or (info.get("evidence_report") or {}).get("overall_risk_level")
                    or "Low"
                )

                evidence_report = info.get("evidence_report") or {}

                # 违规内容
                violation_text_parts = []
                post_content = v.get("post_content", "")
                is_post_violated = info.get("is_post_violated", False)
                if is_post_violated and post_content:
                    truncated = post_content.strip()[:60]
                    if len(post_content.strip()) > 60:
                        truncated += "..."
                    violation_text_parts.append(f"【帖】{_esc_cell(truncated)}")

                violated_comment_originals = v.get("violated_comment_originals", [])
                seen_comments = set()
                if violated_comment_originals:
                    for vc in violated_comment_originals:
                        content = (vc.get("content") or "").strip()
                        # 保留所有去重后的评论（取消任何后端长度限制），前端负责展示与截断
                        if content and content not in seen_comments:
                            seen_comments.add(content)
                            violation_text_parts.append(f"【评】{_esc_cell(content)}")

                violation_cell = (
                    "<br>".join(violation_text_parts) if violation_text_parts else "-"
                )

                # 判定理由
                evidence_reasoning = evidence_report.get("reasoning")
                if evidence_reasoning:
                    reasoning_cell = evidence_reasoning.strip()[:80]
                    if len(evidence_reasoning.strip()) > 80:
                        reasoning_cell += "..."
                    reasoning_cell = _esc_cell(reasoning_cell)
                else:
                    reasoning_cell = "-"

                # 违反条款：使用 matched_laws 的 metadata，格式：《《微博社区公约》》+article：+ category+behavior
                law_parts = []
                for law in info.get("matched_laws") or []:
                    if not law:
                        continue
                    art = law.get("article", "")
                    cat = law.get("category", "")
                    behavior = law.get("full_desc", "")
                    text = f"《《微博社区公约》》{art}：{cat}\n{behavior}".strip()
                    law_parts.append(text)
                law_cell = _esc_cell("、".join(law_parts)) if law_parts else "-"

                # 处置建议
                suggestion = evidence_report.get("disposal_suggestion")
                if suggestion:
                    suggestion_cell = suggestion.strip()[:40]
                    if len(suggestion.strip()) > 40:
                        suggestion_cell += "..."
                    suggestion_cell = _esc_cell(suggestion_cell)
                else:
                    suggestion_cell = "-"

                md += f"| {case_num} | {_esc_cell(risk)} | {violation_cell} | {reasoning_cell} | {law_cell} | {suggestion_cell} |\n"

            md += "\n"

        return md

    def _save_markdown(self, md_content: str, filename: str) -> str:
        """
        保存 Markdown 文件
        🔥 不再生成 PDF（xhtml2pdf 中文支持差），建议用 Typora/VS Code 打开 .md 导出
        """
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)

        md_path = os.path.join(output_dir, filename)
        try:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            logger.info(f"✅ Markdown 报告已保存: {md_path}")
            return md_path
        except Exception as e:
            logger.error(f"❌ Markdown 保存失败: {e}")
            return ""


agent_report = AgentReport()

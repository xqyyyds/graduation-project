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

        violations = [r for r in audit_results if r.get("is_violation")]

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
        md_content = self._assemble_markdown(
            preface, core_events, analyzed_events, violations, trend_report
        )

        # 4. 保存 Markdown 文件 (不再生成 PDF，建议用 Typora 等工具打开 .md 导出)
        md_filename = f"舆情研判_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
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
    ) -> str:
        """
        拼装最终报告 (Markdown 格式)
        """
        date_str = datetime.now().strftime("%Y年%m月%d日")

        # ==============================================================================
        # 1. 封面与前言 (Cover & Preface)
        # ==============================================================================
        md = f"# 内容安全审核与分析报告\n\n"
        md += f"**报告日期**：{date_str}\n\n"
        md += f"**研判周期**：{p.report_period}\n\n"
        md += "---\n\n"

        md += "## 💡 前言：舆情态势综述\n\n"

        # (1) 开篇综述
        md += f"{p.overview}\n\n"

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
        md += f"**【违规风险透视】**\n\n{p.compliance_perspective}\n\n"

        # (4) 时空承接
        md += f"**【时空趋势承接】**\n\n{p.trend_connection}\n\n"

        # (5) 结语
        md += f"**{p.conclusion}**\n\n"

        md += "<div style='page-break-after: always;'></div>\n\n"  # 强制分页

        # ==============================================================================
        # 2. 本期热点舆情总览 (Overview Table)
        # ==============================================================================
        md += "## 📊 第一部分：本期热点舆情总览\n\n"
        md += f"基于全网大数据监测，本期（{p.report_period}）核心热点事件汇总如下：\n\n"

        md += "| 序号 | 📅 时间 | 🔥 事件名称 | 🏷️ 核心标签 | 🌡️ 热度值 |\n"
        md += "| :---: | :--- | :--- | :---: | :---: |\n"

        # 🔥 辅助函数：清理 # 号
        def _clean_hashtag(s: str) -> str:
            """清理字符串中的 # 号"""
            if not s:
                return s
            return s.strip().strip("#").strip()

        if not core_events:
            md += "| - | - | 暂无数据 | - | - |\n"
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
                related_keywords = (
                    evt.get("related_keywords") or evt.get("keywords") or []
                )
                # 🔥 清理核心标签的 # 号
                category = (
                    _clean_hashtag(related_keywords[0]) if related_keywords else "综合"
                )
                heat_val = evt.get("total_heat", 0)
                heat_str = (
                    f"{heat_val/10000:.1f}万" if heat_val > 10000 else str(heat_val)
                )
                # 🔥 清理事件名称的 # 号
                event_title = _clean_hashtag(
                    evt.get("event_name") or evt.get("topic") or "未知"
                )

                # 表格内容转义，防止 Markdown 错乱
                event_title = event_title.replace("|", r"\|")
                category = category.replace("|", r"\|")

                md += f"| {i+1} | {raw_time} | {event_title} | {category} | {heat_str} |\n"

        md += "\n<div style='page-break-after: always;'></div>\n\n"

        # ==============================================================================
        # 3. 重点舆情深读 (Deep Analysis)
        # ==============================================================================
        md += "## 🔥 第二部分：重点舆情深读\n\n"
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
            event_title = e.get("event_name") or e.get("topic") or "未知"

            md += f"### {i+1}. 事件：《{event_title}》\n\n"

            # (1) 事件概况 (引用块)
            md += f"> **事件概况**\n>\n> {r.get('event_overview', '暂无概况')}\n\n"

            # (2) 舆论观点画像 (段落/引用块渲染)
            md += f"#### 🗣️ 舆论观点画像\n\n"
            ops = r.get("public_opinions", [])
            if isinstance(ops, list):
                for op in ops:
                    # 🔥 改为引用块或段落，增加叙事感
                    md += f"> {op}\n>\n"
            else:
                md += f"> {ops}\n"
            md += "\n"

            # (3) 深度研判 (正文)
            md += f"#### 🧠 深度研判\n\n"
            md += f"{r.get('depth_analysis', '暂无分析')}\n\n"

            md += "---\n\n"

        md += "<div style='page-break-after: always;'></div>\n\n"

        # ==============================================================================
        # 4. 未来趋势与战略预警 (Forecast)
        # ==============================================================================
        md += "## 🔮 第三部分：未来趋势与战略预警\n\n"

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
                    md += f"> **背景导语**：{bg}\n\n"

                # 风险点
                points = topic.get("points", [])
                for point in points:
                    sub = point.get("subtitle", "")
                    content = point.get("content", "")
                    # 移除可能重复的编号
                    md += f"#### {sub}\n"
                    md += f"{content}\n\n"
        else:
            md += "（暂无预测数据）\n"

        md += "\n<div style='page-break-after: always;'></div>\n\n"

        # ==============================================================================
        # 5. 附录：违规数据监测 (Appendix)
        # ==============================================================================
        md += "## 🛡️ 附录：违规数据监测\n\n"
        if not c_violations:
            md += "本期未检出需要处置的违规内容。\n"
            return md

        def _esc_cell(s: Any) -> str:
            return (
                str(s)
                .replace("|", r"\|")
                .replace("\r\n", "<br>")
                .replace("\n", "<br>")
                .strip()
            )

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

            # 条款引用统计：优先 evidence_report.cited_laws（核心依据），否则退化到 matched_laws
            cited_laws = (info.get("evidence_report") or {}).get("cited_laws") or []
            if isinstance(cited_laws, list) and cited_laws:
                for law in cited_laws:
                    cat = (law or {}).get("category") or "未知标签"
                    article = (law or {}).get("article") or "未知条款"
                    key = f"{cat} / {article}"
                    law_counts[key] = law_counts.get(key, 0) + 1
            else:
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
        # 🔥 重构：7 列表格，包含证据链
        md += "### 5) 案例明细（按事件分组）\n\n"

        # 按事件分组
        events_violations: Dict[str, List] = {}
        for v in c_violations:
            ename = v.get("event_name") or "未知"
            if ename not in events_violations:
                events_violations[ename] = []
            events_violations[ename].append(v)

        for event_name, violations in events_violations.items():
            md += f"#### 📌 {_esc_cell(event_name)}\n\n"
            # 🔥 7 列表格：note_id | 风险 | 违规原文 | 判定理由 | 核心条款 | 建议 | 证据链
            md += (
                "| note_id | 风险 | 违规原文 | 判定理由 | 核心条款 | 建议 | 证据链 |\n"
            )
            md += "| :--- | :---: | :--- | :--- | :--- | :--- | :--- |\n"

            for v in violations:
                note_id = v.get("note_id") or ""
                info = v.get("violation_info") or {}
                if info is None:
                    continue

                risk = (
                    info.get("overall_risk_level")
                    or (info.get("evidence_report") or {}).get("overall_risk_level")
                    or "Low"
                )

                evidence_report = info.get("evidence_report") or {}

                # ========================================
                # 🔥 违规原文：优先使用保存的原始内容
                # ========================================
                violation_text_parts = []

                # 1. 帖子原文（如果帖子本身违规）
                post_content = v.get("post_content", "")
                is_post_violated = info.get("is_post_violated", False)
                if is_post_violated and post_content:
                    post_excerpt = post_content[:80].strip()
                    if len(post_content) > 80:
                        post_excerpt += "..."
                    violation_text_parts.append(f"【帖】{_esc_cell(post_excerpt)}")

                # 2. 违规评论原文
                violated_comment_originals = v.get("violated_comment_originals", [])
                if violated_comment_originals:
                    for vc in violated_comment_originals[:2]:
                        content = vc.get("content", "")
                        if content:
                            comment_excerpt = content[:60].strip()
                            if len(content) > 60:
                                comment_excerpt += "..."
                            violation_text_parts.append(
                                f"【评】{_esc_cell(comment_excerpt)}"
                            )

                # 如果没有原始内容，退化到 evidence_chain
                if not violation_text_parts:
                    chain = evidence_report.get("evidence_chain")
                    if chain:
                        if isinstance(chain, list):
                            for item in chain[:2]:
                                violation_text_parts.append(_esc_cell(str(item)[:60]))
                        elif isinstance(chain, str):
                            violation_text_parts.append(_esc_cell(chain[:80]))

                violation_cell = (
                    "<br>".join(violation_text_parts)
                    if violation_text_parts
                    else "（无）"
                )

                # ========================================
                # 判定理由
                # ========================================
                evidence_reasoning = evidence_report.get("reasoning")
                if evidence_reasoning:
                    # 截取前 80 字
                    reasoning_excerpt = evidence_reasoning[:80].strip()
                    if len(evidence_reasoning) > 80:
                        reasoning_excerpt += "..."
                    reasoning_cell = _esc_cell(reasoning_excerpt)
                else:
                    reasoning_cell = "（无）"

                # ========================================
                # 🔥 核心条款：加入法规原文
                # ========================================
                cited = evidence_report.get("cited_laws") or []
                law_cell_parts = []

                if isinstance(cited, list) and cited:
                    for law in cited[:2]:
                        if not law:
                            continue
                        cat = law.get("category", "")
                        art = law.get("article", "")
                        rule_text = (
                            law.get("rule", "")
                            or law.get("content", "")
                            or law.get("text", "")
                        )

                        if cat and art:
                            law_header = f"**{_esc_cell(cat)} {_esc_cell(art)}**"
                        elif cat:
                            law_header = f"**{_esc_cell(cat)}**"
                        elif art:
                            law_header = f"**{_esc_cell(art)}**"
                        else:
                            law_header = ""

                        if rule_text:
                            rule_excerpt = rule_text[:50].strip()
                            if len(rule_text) > 50:
                                rule_excerpt += "..."
                            if law_header:
                                law_cell_parts.append(
                                    f"{law_header}: {_esc_cell(rule_excerpt)}"
                                )
                            else:
                                law_cell_parts.append(_esc_cell(rule_excerpt))
                        elif law_header:
                            law_cell_parts.append(law_header)

                # 如果 cited_laws 为空，尝试从 matched_laws 获取
                if not law_cell_parts:
                    ml = info.get("matched_laws") or []
                    for law in ml[:2]:
                        if not law:
                            continue
                        cat = law.get("category", "")
                        art = law.get("article", "")
                        rule_text = (
                            law.get("rule", "")
                            or law.get("content", "")
                            or law.get("text", "")
                        )

                        if cat or art:
                            law_header = (
                                f"**{_esc_cell(cat)} {_esc_cell(art)}**".strip()
                            )
                            if rule_text:
                                rule_excerpt = rule_text[:50].strip()
                                if len(rule_text) > 50:
                                    rule_excerpt += "..."
                                law_cell_parts.append(
                                    f"{law_header}: {_esc_cell(rule_excerpt)}"
                                )
                            else:
                                law_cell_parts.append(law_header)

                law_cell = "<br>".join(law_cell_parts) if law_cell_parts else "（无）"

                # ========================================
                # 建议
                # ========================================
                suggestion = evidence_report.get("disposal_suggestion")
                if suggestion:
                    suggestion_excerpt = suggestion[:60].strip()
                    if len(suggestion) > 60:
                        suggestion_excerpt += "..."
                    suggestion_cell = _esc_cell(suggestion_excerpt)
                else:
                    suggestion_cell = "（无）"

                # ========================================
                # 🔥 证据链（新增列）
                # ========================================
                chain_obj = evidence_report.get("evidence_chain")
                evidence_cell_parts = []
                if chain_obj:
                    if isinstance(chain_obj, list):
                        for i, item in enumerate(chain_obj[:3]):  # 最多 3 条
                            item_text = str(item)[:50].strip()
                            if len(str(item)) > 50:
                                item_text += "..."
                            evidence_cell_parts.append(f"{i+1}. {_esc_cell(item_text)}")
                    elif isinstance(chain_obj, str):
                        chain_excerpt = chain_obj[:100].strip()
                        if len(chain_obj) > 100:
                            chain_excerpt += "..."
                        evidence_cell_parts.append(_esc_cell(chain_excerpt))

                evidence_cell = (
                    "<br>".join(evidence_cell_parts)
                    if evidence_cell_parts
                    else "（无）"
                )

                # 输出 7 列表格行
                md += f"| {_esc_cell(note_id)} | {_esc_cell(risk)} | {violation_cell} | {reasoning_cell} | {law_cell} | {suggestion_cell} | {evidence_cell} |\n"

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

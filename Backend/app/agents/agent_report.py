import os
import markdown
from xhtml2pdf import pisa
from datetime import datetime
from typing import Dict, Any, List

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from app.core.config import settings
from app.core.logger import logger
from app.core.schemas import PrefaceSection
from app.core.prompts import AGENT_E_PREFACE_TEMPLATE


class AgentReport:
    """
    Agent E: 报告总编
    职责：撰写三段式前言 -> 生成热点榜单表格 -> 组装全文 -> 生成 PDF
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

        # 1. 准备素材
        # 🔥 获取 Agent A 的完整榜单 (用于生成表格)
        core_events = state_data.get("core_events", [])

        # 🔥 获取 Agent B 分析完的事件 (现在 Nodes.py 改完后这里会有 5 个)
        analyzed_events = state_data.get("analyzed_events", [])

        audit_results = state_data.get("audit_results", [])
        trend_report = state_data.get("trend_forecast", {})

        # 2. 生成前言 (压缩素材逻辑)
        events_str = "\n".join(
            [
                f"- {(e.get('event_name') or e.get('topic'))}: {e.get('opinion_report', {}).get('event_overview')}"
                for e in analyzed_events
            ]
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

        preface = self._generate_preface(events_str, audit_str, trend_str)

        # 3. 组装 Markdown (传入 core_events 用于表格)
        md_content = self._assemble_markdown(
            preface, core_events, analyzed_events, violations, trend_report
        )

        # 4. 生成 PDF
        pdf_filename = f"舆情研判_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        pdf_path = self._convert_to_pdf(md_content, pdf_filename)

        return {"markdown": md_content, "pdf_path": pdf_path}

    def _generate_preface(self, e_str, a_str, t_str) -> PrefaceSection:
        """调用 LLM 生成前言"""
        try:
            # 🔥 升级：使用 with_structured_output
            structured_llm = self.llm.with_structured_output(PrefaceSection)
            prompt = ChatPromptTemplate.from_template(AGENT_E_PREFACE_TEMPLATE)

            chain = prompt | structured_llm

            return chain.invoke(
                {
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
        md = f"# 每日网络舆情研判报告\n\n"
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

        if not core_events:
            md += "| - | - | 暂无数据 | - | - |\n"
        else:
            # 取前 20 条展示（若不足 20 条则展示全部）
            for i, evt in enumerate(core_events[:20]):
                raw_time = str(evt.get("created_at", ""))[:10]
                related_keywords = (
                    evt.get("related_keywords") or evt.get("keywords") or []
                )
                category = related_keywords[0] if related_keywords else "综合"
                heat_val = evt.get("total_heat", 0)
                heat_str = (
                    f"{heat_val/10000:.1f}万" if heat_val > 10000 else str(heat_val)
                )
                event_title = evt.get("event_name") or evt.get("topic") or "未知"

                # 表格内容转义，防止 Markdown 错乱
                event_title = event_title.replace("|", r"\|")

                md += f"| {i+1} | {raw_time} | {event_title} | {category} | {heat_str} |\n"

        md += "\n<div style='page-break-after: always;'></div>\n\n"

        # ==============================================================================
        # 3. 重点舆情深读 (Deep Analysis)
        # ==============================================================================
        md += "## 🔥 第二部分：重点舆情深读\n\n"
        if not b_events:
            md += "（本期无重点事件）\n"

        for i, e in enumerate(b_events):
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
        md += f"本次共发现高风险违规内容 **{len(c_violations)}** 条。\n\n"

        if c_violations:
            md += "| 事件名称 | 风险等级 | 违规详情 |\n"
            md += "| :--- | :---: | :--- |\n"

            for v in c_violations:
                event_name = v.get("event_name", "未知").replace("|", r"\|")
                info = v.get("violation_info", {})
                risk = info.get("overall_risk_level", "Low")

                # 构建详情描述 (HTML 列表)
                details_html = "<ul>"

                # 1. 主贴违规
                if info.get("is_post_violated"):
                    details_html += "<li>❌ <b>[主贴]</b> 内容违规</li>"

                # 2. 评论违规
                comments = info.get("violated_comments", [])
                if comments:
                    details_html += (
                        f"<li>⚠️ <b>[评论]</b> 发现 {len(comments)} 条违规</li>"
                    )
                    # 仅展示前3条
                    for c in comments[:3]:
                        reason = c.get("reasoning", "未知原因")
                        quote = c.get("quote", "")
                        item_text = f"{reason}"
                        if quote:
                            item_text += f" (摘录: {quote})"
                        details_html += f"<li><small>评论#{c.get('index')}: {item_text}</small></li>"

                    if len(comments) > 3:
                        details_html += (
                            f"<li><small>...等共{len(comments)}条</small></li>"
                        )

                # 3. 处置建议
                suggestion = info.get("evidence_report", {}).get("disposal_suggestion")
                if suggestion:
                    details_html += f"<li>💡 <b>[建议]</b> {suggestion}</li>"

                details_html += "</ul>"

                md += f"| {event_name} | {risk} | {details_html} |\n"

        return md

    def _convert_to_pdf(self, md_content: str, filename: str) -> str:
        """
        生成 PDF
        """
        # 🔥 关键：启用表格扩展 'tables'
        html_body = markdown.markdown(md_content, extensions=["tables"])

        css = """
        <style>
            @page { size: A4; margin: 2.5cm; }
            body { 
                font-family: "SimSun", "SimHei", "Microsoft YaHei", sans-serif;
                line-height: 1.6;
                font-size: 11pt;
            }
            /* 表格样式 */
            table { width: 100%; border-collapse: collapse; margin: 15px 0; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; color: #333; font-weight: bold; }
            tr:nth-child(even) { background-color: #f9f9f9; }
            
            h1 { text-align: center; color: #2c3e50; border-bottom: 2px solid #2c3e50; padding-bottom: 10px; }
            h2 { color: #2980b9; background-color: #f0f7fb; padding: 5px 10px; border-left: 5px solid #2980b9; margin-top: 20px; }
            h3 { color: #e67e22; margin-top: 15px; border-bottom: 1px dashed #ddd; }
            blockquote { background: #f9f9f9; border-left: 5px solid #ccc; margin: 1.5em 10px; padding: 0.5em 10px; color: #555; }
            strong { color: #c0392b; }
        </style>
        """

        full_html = f"<html><head><meta charset='utf-8'>{css}</head><body>{html_body}</body></html>"

        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        pdf_path = os.path.join(output_dir, filename)

        try:
            with open(pdf_path, "wb") as f:
                pisa_status = pisa.CreatePDF(full_html, dest=f)

            if pisa_status.err:
                logger.error("⚠️ PDF 生成发生错误")
                return ""
            return pdf_path
        except Exception as e:
            logger.error(f"❌ PDF 保存失败: {e}")
            return ""


agent_report = AgentReport()

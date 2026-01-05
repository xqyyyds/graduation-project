import os
import markdown
from xhtml2pdf import pisa
from datetime import datetime
from typing import Dict, Any, List

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from app.core.config import settings
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
        self.preface_parser = JsonOutputParser(pydantic_object=PrefaceSection)

    def generate_full_report(self, state_data: Dict[str, Any]) -> Dict[str, str]:
        """
        生成报告全流程
        """
        print("📝 [Agent E] 正在统筹全篇，撰写舆情报告...")

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
        audit_str = f"发现违规{len(violations)}条。"
        if violations:
            audit_str += (
                f" 典型: {violations[0].get('violation_info', {}).get('reasoning')}"
            )

        trend_str = f"下月定调: {trend_report.get('overall_judgment', '暂无')}"

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
            prompt = ChatPromptTemplate.from_template(AGENT_E_PREFACE_TEMPLATE).partial(
                format_instructions=self.preface_parser.get_format_instructions()
            )
            chain = prompt | self.llm | self.preface_parser
            return chain.invoke(
                {
                    "events_summary": e_str,
                    "audit_summary": a_str,
                    "trend_forecast": t_str,
                }
            )
        except Exception as e:
            print(f"❌ 前言生成失败: {e}")
            return PrefaceSection(
                report_period="本期",
                macro_phenomenon="（生成异常）",
                compliance_analysis="（生成异常）",
                future_abstraction="（生成异常）",
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
        拼装最终报告
        """
        date_str = datetime.now().strftime("%Y年%m月%d日")

        # --- 头部 ---
        md = f"# 每日网络舆情研判报告\n"
        md += f"**报告日期**：{date_str}\n"
        md += f"**研判周期**：{p.report_period}\n\n"

        # --- 💡 前言 ---
        md += "## 💡 前言：舆情态势综述\n\n"
        md += f"**【宏观现象】**\n{p.macro_phenomenon}\n\n"
        md += f"**【违规透视】**\n{p.compliance_analysis}\n\n"
        md += f"**【趋势承接】**\n{p.future_abstraction}\n\n"
        md += "---\n\n"

        # --- 📊 第一部分：今日热点舆情总览 (Table) ---
        md += "## 📊 第一部分：今日热点舆情总览\n"
        md += "基于全网大数据监测，今日核心热点事件汇总如下：\n\n"

        md += "| 序号 | 📅 时间 | 🔥 事件名称 | 🏷️ 核心标签 | 🌡️ 热度值 |\n"
        md += "| :--- | :--- | :--- | :--- | :--- |\n"

        # 展示 Top 20 榜单
        if not core_events:
            md += "| - | - | 暂无数据 | - | - |\n"
        else:
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
                md += f"| {i+1} | {raw_time} | {event_title} | {category} | {heat_str} |\n"

        md += "\n---\n\n"

        # --- 🔥 第二部分：重点舆情深读 (这里会自动处理 5 个事件) ---
        md += "## 🔥 第二部分：重点舆情深读\n"
        if not b_events:
            md += "（今日无重点事件）\n"

        for i, e in enumerate(b_events):
            r = e.get("opinion_report", {})
            event_title = e.get("event_name") or e.get("topic") or "未知"
            md += f"### {i+1}. 事件：《{event_title}》\n"

            # 1. 概述 (Agent B 已经查好并写好了)
            md += f"> **事件概况**：{r.get('event_overview')}\n\n"

            # 2. 观点 (Agent B 已经分类好了)
            md += f"**【舆论观点画像】**\n"
            ops = r.get("public_opinions", [])
            if isinstance(ops, list):
                # 如果是列表，分条显示
                for op in ops:
                    md += f"- {op}\n"
            else:
                md += f"{ops}\n"
            md += "\n"

            # 3. 深度分析
            md += f"**【深度研判】**\n{r.get('depth_analysis')}\n\n"

        md += "---\n\n"

        # --- 🔮 第三部分：未来趋势与预警 ---
        md += "## 🔮 第三部分：未来趋势与战略预警\n"
        if d_trend and "overall_judgment" in d_trend:
            md += f"**研判周期**：{d_trend.get('target_month')}\n\n"
            md += f"**1. 总体定调**：\n{d_trend.get('overall_judgment')}\n\n"

            md += "**2. 重点风险前瞻**：\n"
            for risk in d_trend.get("top_risks", []):
                md += f"- **⚠️ {risk.get('domain')}**：{risk.get('deduction_logic')}\n"
                md += f"  *(高敏词: {', '.join(risk.get('warning_keywords', []))})*\n"

            md += "\n**3. 决策锦囊**：\n"
            for adv in d_trend.get("strategic_advice", []):
                md += f"- ✅ {adv}\n"
        else:
            md += "（暂无预测数据）\n"

        md += "\n---\n\n"

        # --- 🛡️ 附录 ---
        md += "## 🛡️ 附录：违规数据监测\n"
        md += f"本次共发现高风险违规内容 **{len(c_violations)}** 条。\n"

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
                print("⚠️ PDF 生成发生错误")
                return ""
            return pdf_path
        except Exception as e:
            print(f"❌ PDF 保存失败: {e}")
            return ""


agent_report = AgentReport()

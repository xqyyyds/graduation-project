import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from langchain_core.prompts import ChatPromptTemplate

from app.core.logger import logger
from app.core.schemas import PrefaceSection
from app.core.prompts import AGENT_E_PREFACE_TEMPLATE
from app.core.llm_factory import get_main_llm

# 工具：归一化违规类别文本，避免细微差异拆桶
from app.services.utils import normalize_category
from app.services.report_document import (
    REPORT_RENDER_VERSION,
    _compose_forecast_summary_paragraph,
    build_report_document,
)
from app.services.render_html import save_report_html
from app.services.render_pdf import save_report_pdf


def _law_entry_text(law: Any) -> str:
    if not law:
        return ""
    if isinstance(law, str):
        return law.strip()
    if isinstance(law, dict):
        art = law.get("article", "")
        cat = law.get("category", "")
        behavior = law.get("full_desc", "")
        return f"《《微博社区公约》》{art}：{cat}\n{behavior}".strip()
    return str(law).strip()


def _law_entry_bucket(law: Any) -> str:
    if not law:
        return "未知条款"
    if isinstance(law, str):
        return law.strip() or "未知条款"
    if isinstance(law, dict):
        cat = law.get("category") or "未知标签"
        article = law.get("article") or "未知条款"
        return f"{cat} / {article}"
    return str(law).strip() or "未知条款"


def render_markdown_from_report_doc(report_doc: Dict[str, Any]) -> str:
    """从 report_json 派生 Markdown，避免 Markdown 成为第二事实源。"""

    def body(text: Any) -> str:
        return str(text or "").strip()

    def cell(text: Any) -> str:
        return body(text).replace("|", r"\|")

    meta = report_doc.get("meta") or {}
    preface = report_doc.get("preface") or {}
    compliance = report_doc.get("compliance") or {}
    compliance_summary = compliance.get("summary") or {}
    forecast = report_doc.get("forecast") or {}
    appendix_stats = report_doc.get("appendix_stats") or {}

    lines: List[str] = []
    lines.append(f"# {body(meta.get('title') or '舆情研判报告')}")
    lines.append("")
    lines.append(f"- 类别：{body(meta.get('category') or '综合')}")
    lines.append(f"- 生成时间：{body(meta.get('generated_at'))}")
    lines.append(f"- 研判周期：{body(meta.get('report_period'))}")
    lines.append(
        f"- 渲染版本：{body(meta.get('render_version') or REPORT_RENDER_VERSION)}"
    )
    lines.append("")

    lines.append("## 前言：舆情态势综述")
    lines.append("")
    preface_paragraphs = preface.get("paragraphs") or []
    if preface_paragraphs:
        for para in preface_paragraphs:
            lines.append(body(para))
            lines.append("")
    else:
        lines.append("（前言生成异常）")
        lines.append("")

    lines.append("## 第一部分：本期热点舆情总览")
    lines.append("")
    lines.append("| 序号 | 时间 | 事件名称 | 热度值 |")
    lines.append("| :---: | :---: | :--- | :---: |")
    for row in report_doc.get("overview_table") or []:
        lines.append(
            f"| {row.get('seq', '')} | {body(row.get('time'))} | {cell(row.get('event_name'))} | {body(row.get('heat_value'))} |"
        )
    lines.append("")

    lines.append("## 第二部分：重点舆情深读")
    lines.append("")
    for idx, item in enumerate(report_doc.get("deep_reads") or [], start=1):
        lines.append(
            f"### {idx}. {body(item.get('editorial_title') or item.get('event_name') or '重点舆情')}"
        )
        lines.append("")
        if item.get("one_line_verdict"):
            lines.append(f"**一句话判断**：{body(item.get('one_line_verdict'))}")
            lines.append("")
        if item.get("event_overview"):
            lines.append("#### 事件概况")
            lines.append(body(item.get("event_overview")))
            lines.append("")
        if item.get("public_opinions"):
            lines.append("#### 舆论观点画像")
            for opinion in item.get("public_opinions") or []:
                lines.append(f"- {body(opinion)}")
            lines.append("")
        if item.get("depth_analysis"):
            lines.append("#### 深度研判")
            lines.append(body(item.get("depth_analysis")))
            lines.append("")
        if item.get("key_quotes"):
            lines.append("#### 关键引用")
            for quote in item.get("key_quotes") or []:
                lines.append(f"> {body(quote)}")
            lines.append("")

    lines.append("## 第三部分：违规风险透视")
    lines.append("")
    total_cases = compliance_summary.get("total_cases", 0)
    event_count = compliance_summary.get("event_count", 0)
    lines.append(
        f"本期共确认违规案例 **{total_cases}** 条，涉及事件 **{event_count}** 个。"
    )
    lines.append("")
    phase_summary = body(compliance_summary.get("phase_summary"))
    if phase_summary:
        lines.append("### 本期违规态势总结")
        lines.append("")
        lines.append(phase_summary)
        lines.append("")
    lines.append("### 风险等级分布")
    lines.append("")
    lines.append("| 风险等级 | 次数 |")
    lines.append("| :---: | :---: |")
    for item in compliance_summary.get("risk_levels") or []:
        lines.append(f"| {body(item.get('label'))} | {item.get('count', 0)} |")
    lines.append("")
    lines.append("### 主要违规类别")
    lines.append("")
    lines.append("| 违规类别 | 次数 |")
    lines.append("| :--- | :---: |")
    for item in (compliance_summary.get("categories") or [])[:8]:
        lines.append(f"| {cell(item.get('label'))} | {item.get('count', 0)} |")
    lines.append("")

    lines.append("## 第四部分：未来趋势与战略预警")
    lines.append("")
    target_period = body(forecast.get("target_period"))
    if target_period:
        lines.append(f"**研判周期**：{target_period}")
        lines.append("")
    for idx, topic in enumerate(forecast.get("topics") or [], start=1):
        lines.append(f"### {idx}. {body(topic.get('topic_name') or '重点议题')}")
        lines.append("")
        if topic.get("background"):
            lines.append(body(topic.get("background")))
            lines.append("")
        summary_parts = []
        if topic.get("main_tension"):
            summary_parts.append(f"核心矛盾：{body(topic.get('main_tension'))}")
        topic_audience = topic.get("audience")
        topic_scene = topic.get("scene_opening")
        points = topic.get("points") or []
        if not topic_audience:
            topic_audience = next(
                (point.get("audience") for point in points if point.get("audience")),
                "",
            )
        if not topic_scene:
            topic_scene = next(
                (point.get("scene") for point in points if point.get("scene")),
                "",
            )
        if topic_audience:
            summary_parts.append(f"涉及人群：{body(topic_audience)}")
        if topic_scene:
            summary_parts.append(f"典型场景：{body(topic_scene)}")
        if summary_parts:
            lines.append(f"**预警摘要**：{'；'.join(summary_parts)}")
            lines.append("")
        for point in points:
            lines.append(f"#### {body(point.get('subtitle') or '风险点')}")
            lines.append(body(_compose_forecast_summary_paragraph(point)))
            lines.append("")

    lines.append("## 附录：违规数据监测")
    lines.append("")
    for title, rows, label in [
        ("风险等级分布", appendix_stats.get("risk_levels") or [], "风险等级"),
        ("违规类别分布", appendix_stats.get("categories") or [], "违规类别"),
        ("依据条款分布", appendix_stats.get("laws") or [], "条款"),
    ]:
        lines.append(f"### {title}")
        lines.append("")
        lines.append(f"| {label} | 次数 |")
        lines.append("| :--- | :---: |")
        for item in rows:
            lines.append(f"| {cell(item.get('label'))} | {item.get('count', 0)} |")
        lines.append("")

    appendix_cases = report_doc.get("appendix_cases") or []
    if appendix_cases:
        lines.append("### 违规案例明细")
        lines.append("")
        for event_idx, event in enumerate(appendix_cases, start=1):
            lines.append(
                f"#### {event_idx}. {body(event.get('event_name') or '未知事件')}"
            )
            lines.append("")
            for case_idx, case in enumerate(event.get("cases") or [], start=1):
                lines.append(f"**案例 {case_idx}**")
                lines.append("")
                lines.append(f"**来源类型**：{body(case.get('source_type'))}")
                lines.append("")
                lines.append(f"**来源ID**：{body(case.get('source_id'))}")
                lines.append("")
                lines.append(f"**序号**：{body(case.get('index'))}")
                lines.append("")
                lines.append(f"**所属事件**：{body(event.get('event_name'))}")
                lines.append("")
                lines.append(f"**违规类别**：{body(case.get('category'))}")
                lines.append("")
                lines.append(f"**风险等级**：{body(case.get('risk_level'))}")
                lines.append("")
                lines.append(f"**违规摘录**：{body(case.get('quote'))}")
                lines.append("")
                lines.append(f"**判定理由**：{body(case.get('reasoning'))}")
                lines.append("")
                lines.append(f"**主要依据**：{body(case.get('primary_law'))}")
                lines.append("")
                lines.append(f"**证据链**：{body(case.get('evidence_chain'))}")
                lines.append("")
                lines.append(f"**处置建议**：{body(case.get('disposal_suggestion'))}")
                lines.append("")
                law_reason = body(case.get("law_reason"))
                if law_reason:
                    lines.append(f"**法规说明**：{law_reason}")
                    lines.append("")
                lines.append("---")
                lines.append("")

    return "\n".join(lines).strip() + "\n"


def _assemble_markdown_from_report_doc(report_doc: Dict[str, Any]) -> str:
    """兼容测试与旧调用口径，统一从 report_json 渲染 Markdown。"""
    return render_markdown_from_report_doc(report_doc)


class AgentReport:
    """
    Agent E: 报告总编
    职责：撰写前言 -> 生成热点榜单表格 -> 组装全文 -> 生成 Markdown
    """

    def __init__(self):
        self.llm = get_main_llm(temperature=0.5)
        # self.preface_parser = JsonOutputParser(pydantic_object=PrefaceSection) (已弃用)

    def _compute_stats(
        self, core_events: List, audit_results: List, analyzed_events: List
    ) -> Dict[str, int]:
        """计算报告统计数据，作为 Source of Truth"""
        violation_list = [r for r in audit_results if r.get("is_violation")]
        high_risk_list = [
            r
            for r in audit_results
            if (r.get("violation_info") or {}).get("overall_risk_level") == "High"
        ]

        return {
            "total_events": len(core_events),
            "analyzed_count": len(analyzed_events),
            "violation_count": len(violation_list),
            "high_risk_count": len(high_risk_list),
        }

    def _validate_preface_numbers(
        self, preface_text: str, stats: Dict[str, int]
    ) -> tuple:
        """
        校验前言中的数字是否与统计数据一致
        返回: (是否通过, 错误信息)
        """
        import re

        # 提取前言中的所有数字
        numbers_in_text = [int(n) for n in re.findall(r"\d+", preface_text)]
        expected_numbers = set(stats.values())

        errors = []
        for num in numbers_in_text:
            if 1900 <= num <= 2100:
                continue
            # 仅校验看起来像“统计数字”的量级，跳过热度值等大数字
            if 100 < num <= 1000 and num not in expected_numbers:
                errors.append(f"检测到可疑数字: {num}")

        if errors:
            return False, "; ".join(errors)
        return True, ""

    def generate_full_report(self, state_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成报告全流程
        """
        logger.info(" [Agent E] 正在统筹全篇，撰写舆情报告...")

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
        #  获取 Agent A 的完整榜单 (用于生成表格)
        core_events = state_data.get("core_events", [])

        #  获取 Agent B 分析完的事件 (现在 Nodes.py 改完后这里会有 5 个)
        analyzed_events = state_data.get("analyzed_events", [])

        audit_results = state_data.get("audit_results", [])
        trend_report = state_data.get("trend_forecast", {})

        #  生成结构化违规统计（主贴 + 评论）供持久化与 API 使用
        # 使其与附录表格（_assemble_markdown 中的 category_counts）保持一致：
        # 优先使用 evidence_report.violated_categories（若存在且为 list），否则退化为逐条统计 violated_comments 中的 category。
        violation_stats: Dict[str, int] = {}
        total_violated_posts = 0
        total_violated_comments = 0

        for r in audit_results:
            info = r.get("violation_info") or {}

            # 统计主贴/评论的数量（用于 totals）
            if info.get("is_post_violated"):
                total_violated_posts += 1

            violated_comments = info.get("violated_comments") or []
            total_violated_comments += len(violated_comments)

            # 优先使用 evidence_report.violated_categories
            violated_cats = (info.get("evidence_report") or {}).get(
                "violated_categories"
            )
            if isinstance(violated_cats, list) and violated_cats:
                for cat_raw in violated_cats:
                    if not cat_raw:
                        continue
                    cat = normalize_category(cat_raw)
                    violation_stats[cat] = violation_stats.get(cat, 0) + 1
            else:
                # 回退：使用评论里的 category 字段逐条计数
                for c in violated_comments:
                    cat = normalize_category((c or {}).get("category") or "其他")
                    violation_stats[cat] = violation_stats.get(cat, 0) + 1

        # 2. 生成前言（压缩素材：只给定调所需摘要，避免模型把前言写成半篇正文）
        top_events_lines = []
        for i, e in enumerate(core_events[:20]):
            name = e.get("event_name") or e.get("topic") or "未知"
            heat = e.get("total_heat", 0)
            top_events_lines.append(f"{i+1}. {name}（热度{heat}）")
        top_events_str = (
            "\n".join(top_events_lines) if top_events_lines else "（无事件榜单数据）"
        )

        deep_read_lines = []
        for i, e in enumerate(analyzed_events[:3]):
            name = e.get("event_name") or e.get("topic") or "未知"
            report = e.get("opinion_report") or {}
            verdict = (
                report.get("one_line_verdict") or report.get("event_overview") or ""
            ).strip()
            if verdict:
                deep_read_lines.append(f"- {name}: {verdict[:60]}")
        deep_read_str = (
            "\n".join(deep_read_lines) if deep_read_lines else "（无深读摘要）"
        )

        events_str = (
            f"【研判周期】{report_period}\n"
            f"【热点榜单Top20】\n{top_events_str}\n\n"
            f"【重点深读摘要Top3】\n{deep_read_str}"
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

        #  升级：生成更丰富的合规摘要，供 Agent E 写前言
        # 初始化 cat_counts，确保即使无违规也有此变量
        cat_counts = {}

        if not violations:
            audit_str = "本期未发现高风险违规内容，舆论场整体平稳。"
        else:
            # 统计违规类型
            for v in violations:
                info = v.get("violation_info", {})
                # 统计主贴
                if info.get("is_post_violated"):
                    cat_raw = info.get("category", "其他")
                    cat = normalize_category(cat_raw)
                    cat_counts[cat] = cat_counts.get(cat, 0) + 1
                # 统计评论
                for c in info.get("violated_comments", []):
                    cat_raw = (c or {}).get("category", "其他")
                    cat = normalize_category(cat_raw)
                    cat_counts[cat] = cat_counts.get(cat, 0) + 1

            top_cats = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            cat_str = "、".join([f"{k}({v}条)" for k, v in top_cats])

            audit_str = f"共发现违规内容 {len(violations)} 条，主要集中在：{cat_str}。"

            # 摘录典型案例
            if violations:
                typical = violations[0].get("violation_info", {})
                reason = typical.get("reasoning") or "涉及敏感内容"
                audit_str += f" 典型风险表现为：{reason[:32]}。"

        #  适配新版 TrendForecastReport (topics 列表)
        topics = trend_report.get("topics", [])
        if topics:
            topic_titles = [t.get("topic_name", "未知议题") for t in topics[:2]]
            trend_str = f"下阶段重点风险主线：{'；'.join(topic_titles)}。"
        else:
            trend_str = "下月定调: 暂无明确预测数据"

        # 计算数据锚定统计
        stats = self._compute_stats(
            core_events=core_events,
            analyzed_events=analyzed_events,
            audit_results=audit_results,
        )
        logger.debug(f"[Agent E] 数据锚定统计: {stats}")

        preface = self._generate_preface(
            report_period=report_period,
            start_date=start_date,
            end_date=end_date,
            e_str=events_str,
            a_str=audit_str,
            t_str=trend_str,
            category=state_data.get("category", "综合"),
            stats=stats,
        )

        # 二次兜底：强制覆盖 report_period，避免模型乱写年份
        try:
            preface.report_period = report_period
        except Exception:
            pass

        # 校验前言数字一致性（仅日志记录）
        preface_text = (
            " ".join(
                [text for text in (getattr(preface, "paragraphs", None) or []) if text]
            )
            or ""
        )
        is_valid, mismatch_msg = self._validate_preface_numbers(preface_text, stats)
        if not is_valid:
            logger.warning(f"[Agent E] 前言数字校验不一致: {mismatch_msg}")
        else:
            logger.debug("[Agent E] 前言数字校验通过")

        # 3. 组装结构化报告对象（单一事实源）
        category = state_data.get("category", "综合")
        report_doc = build_report_document(
            state_data=state_data,
            preface=preface,
        )

        # 4. 所有导出格式从 report_json 派生
        md_content = _assemble_markdown_from_report_doc(report_doc)

        # 5. 保存多格式产物
        md_filename = f"舆情研判_{category}_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        md_path = self._save_markdown(md_content, md_filename)
        stem_path = os.path.splitext(md_path)[0]
        json_path = self._save_json(report_doc, f"{stem_path}.json")
        html_path = self._save_html(report_doc, f"{stem_path}.html")
        pdf_path = self._save_pdf(report_doc, f"{stem_path}.pdf")

        #  返回违规统计数据，供下游写入 Session
        return {
            "markdown": md_content,
            "md_path": md_path,
            "json_path": json_path,
            "html_path": html_path,
            "pdf_path": pdf_path,
            "report_json": report_doc,
            "violation_stats": violation_stats,
            "total_violated_posts": total_violated_posts,
            "total_violated_comments": total_violated_comments,
        }

    def _generate_preface(
        self,
        report_period: str,
        start_date: str,
        end_date: str,
        e_str: str,
        a_str: str,
        t_str: str,
        category: str = "综合",
        stats: Dict[str, int] = None,
        improvement_hint: str = "",
    ) -> PrefaceSection:
        """调用 LLM 生成前言"""
        try:
            #  升级：使用 with_structured_output
            category = category if category not in ["综合", "其他"] else "全部"
            structured_llm = self.llm.with_structured_output(PrefaceSection)
            prompt = ChatPromptTemplate.from_template(AGENT_E_PREFACE_TEMPLATE)

            # 构造数据锚定字符串
            if stats:
                stats_str = f"""
- 热点事件总数: {stats['total_events']}
- 深度分析事件数: {stats['analyzed_count']}
- 违规内容数: {stats['violation_count']}
- 高风险数: {stats['high_risk_count']}

**重要约束**: 文中出现的数据必须与上述数据完全一致，严禁杜撰其他数字。
"""
            else:
                stats_str = "（无统计数据）"

            chain = prompt | structured_llm

            return chain.invoke(
                {
                    "report_period": report_period,
                    "start_date": start_date,
                    "end_date": end_date,
                    "events_summary": e_str,
                    "audit_summary": a_str,
                    "trend_forecast": t_str,
                    "category": category,
                    "stats": stats_str,
                    "improvement_hint": improvement_hint,
                }
            )
        except Exception as e:
            logger.error(f" 前言生成失败: {e}")
            return PrefaceSection(
                report_period="本期",
                paragraphs=["（生成异常）"],
            )

    def _assemble_markdown(
        self,
        p: PrefaceSection,
        core_events: List,
        b_events: List,
        c_violations: List,
        d_trend: Dict,
        category: str = "综合",
        historical_events: Optional[Dict] = None,
    ) -> str:
        """
        Legacy 兼容入口。
        统一短路到 report_json -> markdown 渲染链，避免再落回旧版双源拼装逻辑。
        """
        logger.warning(
            " [Agent E] 调用了 legacy _assemble_markdown 入口，已自动切换到 report_json 单一事实源渲染链。"
        )
        report_doc = build_report_document(
            {
                "core_events": core_events,
                "analyzed_events": b_events,
                "audit_results": c_violations,
                "trend_forecast": d_trend,
                "category": category,
            },
            preface=p,
        )
        return render_markdown_from_report_doc(report_doc)

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
            #  二次去emoji（保险起见）
            # (这里可以加正则去 emoji，暂时先不加以免引入额外依赖，依靠 Prompt 约束)
            return text.strip()

        # ==============================================================================
        # 内嵌样式（使 Markdown 在各种渲染器中都有良好的表格显示效果）
        # ==============================================================================
        css_style = """<style>
* {
    box-sizing: border-box;
}
/* 严格复刻前端 ReportDetail.vue 样式 (已针对下载优化) */
body { 
    font-family: "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
    font-size: 15px; 
    line-height: 1.8; 
    color: #374151; 
    max-width: 2000px; 
    margin: 0 auto !important; /* 强制居中 */
    padding: 20px;
    box-sizing: border-box;
    width: 100% !important; /* 确保宽度100% */
}

/* 标题样式 */
h1 { font-size: 24px; font-weight: 700; color: #111827; margin: 32px 0 20px; padding-bottom: 12px; border-bottom: 2px solid #2563eb; text-align: center; }
h2 { font-size: 20px; font-weight: 600; color: #1f2937; margin: 36px 0 18px; padding: 10px 14px; background: #f0f7ff; border-left: 4px solid #2563eb; border-radius: 0 6px 6px 0; line-height: 1.4; }
h3 { font-size: 17px; font-weight: 600; color: #374151; margin: 28px 0 14px; padding-bottom: 8px; border-bottom: 1px solid #e5e7eb; line-height: 1.4; }
h4 { font-size: 16px; font-weight: 600; color: #1f2937; margin: 32px 0 16px; padding: 8px 12px; background: #f8fafc; border-radius: 6px; line-height: 1.4; }
h5, h6 { font-size: 14px; font-weight: 600; color: #6b7280; margin: 16px 0 8px; line-height: 1.4; }

/* 正文与排版 */
p { margin: 12px 0; text-align: justify; }
ul, ol { margin: 12px 0; padding-left: 24px; }
li { margin: 8px 0; }

/* 引用块 */
blockquote { margin: 16px 0; padding: 12px 20px; background: #f9fafb; border-radius: 8px; color: #4b5563; }
blockquote h2, blockquote h5 { border-left: none; padding-left: 0; }

/* 强调与代码 */
strong { color: #111827; font-weight: 600; }
em { color: #6b7280; font-style: italic; }
code { background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 14px; }
pre { background: #1f2937; color: #f9fafb; padding: 16px; border-radius: 8px; overflow-x: auto; }
pre code { background: transparent; padding: 0; }

/* -------------------------------------------------------
   【修复】消除表格横向滚动条，强制文字换行
   ------------------------------------------------------- */
table {
    width: 100% !important;
    table-layout: fixed; /* 关键：强制表格遵循列宽定义，而不是被内容撑开 */
    border-collapse: collapse;
}

td, th {
    word-wrap: break-word; /* 允许长单词换行 */
    word-break: break-all; /* 强制在任意字符间换行（针对长英文或URL） */
    white-space: normal !important; /* 强制允许换行 */
    overflow-wrap: break-word;
    vertical-align: top; /* 内容对齐到顶部，视觉更整齐 */
}

/* 针对主要的大表（违规数据监测）做针对性优化 */
table:nth-of-type(n+6) {
    display: table !important; /* 防止被变成 block 导致宽度失效 */
}

table:nth-of-type(1) th:nth-child(1) { width: 15%; }
table:nth-of-type(1) th:nth-child(2) { width: 15%; }
table:nth-of-type(1) th:nth-child(3) { width: 50%; }
/* table:nth-of-type(1) th:nth-child(2) { 留空，自动填满 } */


table:nth-of-type(2) th:nth-child(1) { width: 50%; }


table:nth-of-type(3) th:nth-child(1) { width: 70%; }

table:nth-of-type(4) th:nth-child(1) { width: 70%; }
table:nth-of-type(4) th:nth-child(2) { width: 15%; }

table:nth-of-type(5) th:nth-child(1) { width: 70%; }


table:nth-of-type(n+6) th:nth-child(1) { width: 6%; }  /* 序号 */
table:nth-of-type(n+6) th:nth-child(2) { width: 10%; } /* 风险等级 */
/* table:nth-of-type(n+4) th:nth-child(3) { 违规内容 - 留空，它会吃掉所有剩余空间！ } */
table:nth-of-type(n+6) th:nth-child(4) { width: 22%; } /* 判定理由 */
table:nth-of-type(n+6) th:nth-child(5) { width: 20%; } /* 违反条款 */
table:nth-of-type(n+6) th:nth-child(6) { width: 15%; } /* 处置建议 */


/* 对齐微调 */
table:nth-of-type(n+6) td:nth-child(1),
table:nth-of-type(n+6) td:nth-child(2) { text-align: center !important; }

table:nth-of-type(n+6) td:nth-child(3),
table:nth-of-type(n+6) td:nth-child(4),
table:nth-of-type(n+6) td:nth-child(5),
table:nth-of-type(n+6) td:nth-child(6) { text-align: left !important; }


/* -------------------------------------------------------
   【修复】强制展开被折叠的内容
   ------------------------------------------------------- */
.truncated-cell { 
    cursor: auto; 
    max-height: none !important;
    overflow: visible !important;
}
.truncated-cell::after { display: none !important; }
.truncated-cell:hover { background: inherit !important; }

/* 链接与分割线 */
a { color: #2563eb; text-decoration: none; border-bottom: 1px solid transparent; transition: border-color 0.2s; }
a:hover { border-bottom-color: #2563eb; }
hr { border: none; border-top: 1px solid #e5e7eb; margin: 24px 0; }

/* 打印优化 */
@media print { 
    body { 
        padding: 0 !important; 
        max-width: 100% !important; 
        margin: 0 auto !important;
        width: 100% !important;
    } 
    h2 { background: none; border: 1px solid #e5e7eb; } 
    table { 
        page-break-inside: auto;
        width: 100% !important;
    }
    tr { page-break-inside: avoid; }
}
</style>

"""

        # ==============================================================================
        # 1. 封面与前言 (Cover & Preface)
        # ==============================================================================
        title_suffix = f"（{category}）"
        md = css_style
        md += f"# 内容安全审核与分析报告{title_suffix}\n\n"
        md += f"**报告日期**：{date_str}\n\n"
        md += f"**研判周期**：{p.report_period}\n\n"
        md += "---\n\n"

        md += "## 前言：舆情态势综述\n\n"
        preface_paragraphs = [
            _normalize_body_text(text) for text in (getattr(p, "paragraphs", []) or [])
        ]
        preface_paragraphs = [text for text in preface_paragraphs if text]
        if preface_paragraphs:
            for paragraph in preface_paragraphs:
                md += f"{paragraph}\n\n"
        else:
            md += "（前言生成异常）\n\n"

        md += "<div style='page-break-after: always;'></div>\n\n"  # 强制分页

        # ==============================================================================
        # 2. 本期热点舆情总览 (Overview Table)
        # ==============================================================================
        md += "## 第一部分：本期热点舆情总览\n\n"
        md += f"基于全网大数据监测，本期（{p.report_period}）核心热点事件汇总如下：\n\n"

        md += "| 序号 | 时间 | 事件名称 | 热度值 |\n"
        md += "| :---: | :---: | :--- | :---: |\n"

        #  辅助函数：清理 # 号
        def _clean_hashtag(s: str) -> str:
            """清理字符串中的 # 号"""
            if not s:
                return s
            return s.strip().strip("#").strip()

        if not core_events:
            md += "| - | - | 暂无数据 | - |\n"
        else:
            #  去重：按 event_name 去重，保留首次出现的（热度最高的）
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
                #  直接使用热搜标题，清理 # 号
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

        #  去重：按 event_name 去重
        seen_b_names = set()
        unique_b_events = []
        for e in b_events:
            event_name = e.get("event_name") or e.get("topic") or "未知"
            if event_name not in seen_b_names:
                seen_b_names.add(event_name)
                unique_b_events.append(e)

        for i, e in enumerate(unique_b_events):
            r = e.get("opinion_report", {})
            #  优先使用原始热搜标题 raw_title，否则使用 event_name
            event_title = _clean_hashtag(
                e.get("raw_title") or e.get("event_name") or e.get("topic") or "未知"
            )

            md += f"### {i+1}. 事件：《{event_title}》\n\n"

            # (1) 事件概况 -  改为 h4 + 段落，与其他部分样式一致
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
        # 3.5 历史同期热门事件回顾 (Historical Review)
        # ==============================================================================
        if historical_events and historical_events.get("events"):
            events_list = historical_events.get("events", [])
            summary = historical_events.get("summary", "")

            md += "## 历史同期热门事件回顾\n\n"

            # 使用 LLM 生成的导语
            if summary:
                md += f"{_normalize_body_text(summary)}\n\n"

            # 表格
            md += "| 日期 | 热门事件 |\n"
            md += "| :---: | :--- |\n"

            for evt in events_list:
                date = evt.get("date", "")
                title = evt.get("event_title", "")
                evt_summary = evt.get("event_summary", "")

                # 转义 Markdown 表格分隔符
                title = title.replace("|", r"\|")
                evt_summary = evt_summary.replace("|", r"\|")

                # 组合标题和摘要
                event_text = f"**{title}**<br>{evt_summary}" if evt_summary else title

                md += f"| {date} | {event_text} |\n"

            md += "\n<div style='page-break-after: always;'></div>\n\n"
        else:
            # 如果没有历史数据，可以选择不显示或显示占位符
            # 这里选择不显示该章节
            pass

        # ==============================================================================
        # 4. 违规风险透视 (正文)
        # ==============================================================================
        md += "## 第三部分：违规风险透视\n\n"

        if not c_violations:
            md += "本期未检出需要重点处置的违规内容，风险整体可控。\n\n"
        else:
            total_cases = 0
            event_groups: Dict[str, List[Dict[str, Any]]] = {}
            risk_counts: Dict[str, int] = {}
            category_counts: Dict[str, int] = {}
            for item in c_violations:
                event_name = item.get("event_name") or "未知事件"
                info = item.get("violation_info") or {}
                cases = []
                if info.get("post_case"):
                    cases.append(info.get("post_case"))
                cases.extend(info.get("comment_cases") or [])
                total_cases += len(cases)
                if cases:
                    event_groups.setdefault(event_name, []).extend(cases)
                overall_risk = info.get("overall_risk_level") or "Low"
                risk_counts[overall_risk] = risk_counts.get(overall_risk, 0) + len(
                    cases
                )
                for case in cases:
                    cat = normalize_category(case.get("category") or "其他")
                    category_counts[cat] = category_counts.get(cat, 0) + 1

            md += (
                f"本期共确认违规案例 <strong>{total_cases}</strong> 条，"
                f"涉及事件 <strong>{len(event_groups)}</strong> 个。\n\n"
            )
            high_cnt = risk_counts.get("High", 0)
            medium_cnt = risk_counts.get("Medium", 0)
            low_cnt = risk_counts.get("Low", 0)
            md += "### 本期违规态势总结\n\n"
            summary_parts = [f"当前确认违规内容共 {total_cases} 条。"]
            if high_cnt:
                summary_parts.append(f"其中高风险案例 {high_cnt} 条，为当前处置重点。")
            elif medium_cnt:
                summary_parts.append(f"当前以中风险案例为主，共 {medium_cnt} 条。")
            elif low_cnt:
                summary_parts.append(f"当前以低风险案例为主，共 {low_cnt} 条。")
            if category_counts:
                top3 = [
                    name
                    for name, _ in sorted(
                        category_counts.items(), key=lambda item: item[1], reverse=True
                    )[:3]
                ]
                summary_parts.append(f"主要集中在：{'、'.join(top3)}。")
            md += "".join(summary_parts) + "\n\n"

            md += "### 风险等级分布\n\n"
            md += "| 风险等级 | 次数 |\n| :---: | :---: |\n"
            for level in ["High", "Medium", "Low"]:
                if level in risk_counts:
                    md += f"| {level} | {risk_counts[level]} |\n"
            md += "\n"

            md += "### 主要违规类别\n\n"
            md += "| 违规类别 | 次数 |\n| :--- | :---: |\n"
            for cat, cnt in sorted(
                category_counts.items(), key=lambda item: item[1], reverse=True
            )[:8]:
                md += f"| {_normalize_body_text(cat)} | {cnt} |\n"
            md += "\n"

        md += "<div style='page-break-after: always;'></div>\n\n"

        # ==============================================================================
        # 5. 未来趋势与战略预警 (Forecast)
        # ==============================================================================
        md += "## 第四部分：未来趋势与战略预警\n\n"

        # 适配新版 Schema (TrendForecastReport: target_period, topics)
        topics = d_trend.get("topics", [])

        if topics:
            md += f"**研判周期**：{d_trend.get('target_period', '下月')}\n\n"

            for i, topic in enumerate(topics):
                title = topic.get("topic_name", "重点议题")
                md += f"### {i+1}. {title}\n\n"

                # 背景
                bg = topic.get("background")
                if bg:
                    md += f"> **背景导语**：{_normalize_body_text(bg)}\n\n"
                main_tension = topic.get("main_tension")
                audience = topic.get("audience")
                scene_opening = topic.get("scene_opening")
                points = topic.get("points", [])
                if not audience:
                    audience = next(
                        (
                            point.get("audience")
                            for point in points
                            if point.get("audience")
                        ),
                        "",
                    )
                if not scene_opening:
                    scene_opening = next(
                        (point.get("scene") for point in points if point.get("scene")),
                        "",
                    )
                if main_tension or audience or scene_opening:
                    summary_parts = []
                    if main_tension:
                        summary_parts.append(
                            f"核心矛盾：{_normalize_body_text(main_tension)}"
                        )
                    if audience:
                        summary_parts.append(
                            f"涉及人群：{_normalize_body_text(audience)}"
                        )
                    if scene_opening:
                        summary_parts.append(
                            f"典型场景：{_normalize_body_text(scene_opening)}"
                        )
                    md += f"> **预警摘要**：{'；'.join(summary_parts)}\n\n"

                # 风险点
                for point in points:
                    sub = point.get("subtitle", "")
                    content = _compose_forecast_summary_paragraph(point)
                    md += f"#### {sub}\n"
                    md += f"**研判**：{_normalize_body_text(content)}\n\n"
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
                for cat_raw in violated_cats:
                    if not cat_raw:
                        continue
                    cat = normalize_category(cat_raw)
                    category_counts[cat] = category_counts.get(cat, 0) + 1
            else:
                for it in violated_comments:
                    cat = normalize_category((it or {}).get("category") or "其他")
                    category_counts[cat] = category_counts.get(cat, 0) + 1

            # 条款引用统计：强制使用检索到的数据库 metadata (matched_laws)，不使用 LLM 生成的 evidence_report.cited_laws
            for law in info.get("matched_laws") or []:
                key = _law_entry_bucket(law)
                law_counts[key] = law_counts.get(key, 0) + 1

            suggestion = (info.get("evidence_report") or {}).get("disposal_suggestion")
            if suggestion:
                s = _esc_cell(suggestion)
                suggestion_counts[s] = suggestion_counts.get(s, 0) + 1

        md += f"本期共检出疑似违规帖子 <strong>{total_posts}</strong> 条，涉及违规评论 <strong>{total_violated_comments}</strong> 条。\n\n"

        # --- 违规态势总结 ---
        md += "### 违规态势概述\n\n"

        # 风险等级分析
        high_cnt = risk_counts.get("High", 0)
        medium_cnt = risk_counts.get("Medium", 0)
        low_cnt = risk_counts.get("Low", 0)

        if high_cnt > 0:
            risk_summary = f"本期违规内容中, <strong>高风险(High)</strong>占 {high_cnt} 条，需重点关注处置；"
        else:
            risk_summary = "本期未检出高风险(High)级别违规内容；"

        if medium_cnt > 0:
            risk_summary += f"<strong>中风险(Medium)</strong>占 {medium_cnt} 条；"
        if low_cnt > 0:
            risk_summary += f"<strong>低风险(Low)</strong>占 {low_cnt} 条。"

        md += f"{risk_summary}\n\n"

        # 主要违规领域分析
        if category_counts:
            top3_cats = sorted(
                category_counts.items(), key=lambda x: x[1], reverse=True
            )[:3]
            cat_analysis = (
                "从违规类型分布来看，主要集中在："
                + "、".join(
                    [f"<strong>{cat}</strong>({cnt}次)" for cat, cnt in top3_cats]
                )
                + "。"
            )
            md += f"{cat_analysis}\n\n"

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

        # (5) 违规案例明细（按事件分组、逐条展开）
        md += "### 5) 违规案例明细\n\n"
        event_num = 0
        case_num = 0
        for v in c_violations:
            event_name = v.get("event_name") or "未知"
            info = v.get("violation_info") or {}
            evidence_report = info.get("evidence_report") or {}

            cases_for_appendix = []
            if info.get("post_case"):
                post_case = info.get("post_case") or {}
                if _normalize_body_text(post_case.get("primary_law", "")):
                    cases_for_appendix.append(("帖子", post_case))
            for case in info.get("comment_cases") or []:
                if _normalize_body_text(case.get("primary_law", "")):
                    cases_for_appendix.append(("评论", case))

            if not cases_for_appendix:
                continue

            event_num += 1
            md += f"#### {event_num}. {_esc_cell(event_name)}\n\n"

            for source_type, case in cases_for_appendix:
                case_num += 1
                quote = _normalize_body_text(case.get("quote", ""))
                reasoning = _normalize_body_text(
                    case.get("reasoning") or evidence_report.get("reasoning") or ""
                )
                primary_law = _normalize_body_text(case.get("primary_law", ""))
                disposal = _normalize_body_text(
                    case.get("disposal_suggestion")
                    or evidence_report.get("disposal_suggestion")
                    or "建议人工研判"
                )
                risk_level = _normalize_body_text(
                    case.get("risk_level") or info.get("overall_risk_level") or "Low"
                )
                category = _normalize_body_text(case.get("category", "未标注类别"))
                if source_type == "评论":
                    post_preview = _normalize_body_text(v.get("post_content") or "")
                    if len(post_preview) > 80:
                        post_preview = post_preview[:80].rstrip() + "..."
                    evidence_chain = "；".join(
                        [
                            f"所属帖子：{post_preview}",
                            f"评论原文：{quote}",
                        ]
                    ).strip("；")
                else:
                    evidence_chain = f"帖子原文：{quote}"

                md += f"**案例 {case_num}**\n\n"
                md += f"**来源类型**：{source_type}\n\n"
                md += f"**所属事件**：{_normalize_body_text(event_name)}\n\n"
                md += f"**违规类别**：{category}\n\n"
                md += f"**风险等级**：{risk_level}\n\n"
                md += f"**违规摘录**：{quote}\n\n"
                md += f"**判定理由**：{reasoning}\n\n"
                md += f"**主要依据**：{primary_law}\n\n"
                md += f"**证据链**：{_normalize_body_text(evidence_chain or '已记录原始内容上下文')}\n\n"
                md += f"**处置建议**：{disposal}\n\n"
                law_reason = _normalize_body_text(case.get("law_reason", ""))
                if law_reason:
                    md += f"**法规说明**：{law_reason}\n\n"
                md += "---\n\n"

        return md

    def _save_markdown(self, md_content: str, filename: str) -> str:
        """
        保存 Markdown 兼容导出文件。
        """
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)

        md_path = os.path.join(output_dir, filename)
        try:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_content)
            logger.info(f" Markdown 报告已保存: {md_path}")
            return md_path
        except Exception as e:
            logger.error(f" Markdown 保存失败: {e}")
            return ""

    def _save_json(self, report_doc: Dict[str, Any], path: str) -> str:
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(report_doc, file, ensure_ascii=False, indent=2)
            logger.info(f" JSON 报告已保存: {path}")
            return path
        except Exception as e:
            logger.error(f" JSON 保存失败: {e}")
            return ""

    def _save_html(self, report_doc: Dict[str, Any], path: str) -> str:
        try:
            save_report_html(report_doc, path)
            logger.info(f" HTML 报告已保存: {path}")
            return path
        except Exception as e:
            logger.error(f" HTML 保存失败: {e}")
            return ""

    def _save_pdf(self, report_doc: Dict[str, Any], path: str) -> str:
        try:
            save_report_pdf(report_doc, path)
            logger.info(f" PDF 报告已保存: {path}")
            return path
        except Exception as e:
            logger.error(f" PDF 保存失败: {e}")
            return ""


agent_report = AgentReport()

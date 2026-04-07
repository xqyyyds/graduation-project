import os

from playwright.sync_api import sync_playwright
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xhtml2pdf import pisa

from app.core.logger import logger
from app.services.render_html import render_report_html


def _flatten_css_vars(html: str) -> str:
    replacements = {
        "var(--ink)": "#1f2937",
        "var(--muted)": "#6b7280",
        "var(--line)": "#dbe4f0",
        "var(--panel)": "#ffffff",
        "var(--panel-soft)": "#f8fbff",
        "var(--accent)": "#1d4ed8",
        "var(--accent-soft)": "#e8f1ff",
        "var(--danger)": "#b91c1c",
        "var(--shadow)": "none",
    }
    flattened = html
    for source, target in replacements.items():
        flattened = flattened.replace(source, target)
    return flattened


def _save_pdf_with_xhtml2pdf(report_doc: dict, output_path: str) -> str:
    html = _flatten_css_vars(render_report_html(report_doc))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as file:
        result = pisa.CreatePDF(src=html, dest=file, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"xhtml2pdf 渲染失败，错误码: {result.err}")
    return output_path


def _save_pdf_with_playwright(report_doc: dict, output_path: str) -> str:
    html = render_report_html(report_doc)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1800})
        page.set_content(html, wait_until="load")
        page.emulate_media(media="screen")
        page.wait_for_timeout(400)
        page.pdf(
            path=output_path,
            format="A4",
            print_background=True,
            prefer_css_page_size=True,
            margin={
                "top": "14mm",
                "right": "12mm",
                "bottom": "14mm",
                "left": "12mm",
            },
        )
        browser.close()

    return output_path


def _build_styles():
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=styles["Heading1"],
            fontName="STSong-Light",
            fontSize=20,
            leading=28,
            textColor=colors.HexColor("#14213d"),
            spaceAfter=14,
        ),
        "heading": ParagraphStyle(
            "HeadingCn",
            parent=styles["Heading2"],
            fontName="STSong-Light",
            fontSize=14,
            leading=22,
            textColor=colors.HexColor("#1d3557"),
            spaceBefore=10,
            spaceAfter=8,
        ),
        "subheading": ParagraphStyle(
            "SubHeadingCn",
            parent=styles["Heading3"],
            fontName="STSong-Light",
            fontSize=12,
            leading=18,
            textColor=colors.HexColor("#2f4858"),
            spaceBefore=8,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "BodyCn",
            parent=styles["BodyText"],
            fontName="STSong-Light",
            fontSize=10.5,
            leading=18,
            textColor=colors.HexColor("#333333"),
            spaceAfter=6,
        ),
        "muted": ParagraphStyle(
            "MutedCn",
            parent=styles["BodyText"],
            fontName="STSong-Light",
            fontSize=9.5,
            leading=15,
            textColor=colors.HexColor("#6b7280"),
            spaceAfter=6,
        ),
    }


def _safe(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def _forecast_point_paragraph(point: dict) -> str:
    from app.services.report_document import _compose_forecast_summary_paragraph

    return _compose_forecast_summary_paragraph(point)


def _build_overview_table(rows):
    data = [["序号", "时间", "事件名称", "热度值"]]
    for row in rows:
        data.append([row["seq"], row["time"], row["event_name"], row["heat_value"]])
    table = Table(data, colWidths=[18 * mm, 32 * mm, 105 * mm, 24 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f1ff")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1d3557")),
                ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#fafbfd")],
                ),
                ("LEADING", (0, 0), (-1, -1), 14),
            ]
        )
    )
    return table


def _save_pdf_with_reportlab(report_doc: dict, output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    styles = _build_styles()
    story = []

    meta = report_doc.get("meta", {})
    forecast = report_doc.get("forecast", {})
    compliance = report_doc.get("compliance", {})

    story.append(Paragraph(_safe(meta.get("title", "舆情研判报告")), styles["title"]))
    story.append(
        Paragraph(
            _safe(
                f"类别：{meta.get('category', '综合')}　生成时间：{meta.get('generated_at', '')}　周期：{meta.get('report_period', '')}"
            ),
            styles["muted"],
        )
    )
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("第一部分：本期热点舆情总览", styles["heading"]))
    story.append(_build_overview_table(report_doc.get("overview_table", [])))
    story.append(Spacer(1, 5 * mm))

    story.append(Paragraph("第二部分：重点舆情深读", styles["heading"]))
    for item in report_doc.get("deep_reads", []):
        story.append(
            Paragraph(
                _safe(item.get("editorial_title") or item.get("event_name")),
                styles["subheading"],
            )
        )
        if item.get("one_line_verdict"):
            story.append(Paragraph(_safe(item["one_line_verdict"]), styles["body"]))
        if item.get("event_overview"):
            story.append(Paragraph("事件概况", styles["subheading"]))
            story.append(Paragraph(_safe(item["event_overview"]), styles["body"]))
        if item.get("public_opinions"):
            story.append(Paragraph("舆论观点画像", styles["subheading"]))
            for opinion in item.get("public_opinions", []):
                story.append(Paragraph(_safe(f"• {opinion}"), styles["body"]))
        if item.get("depth_analysis"):
            story.append(Paragraph("深度研判", styles["subheading"]))
            story.append(Paragraph(_safe(item["depth_analysis"]), styles["body"]))

    story.append(Paragraph("第三部分：违规风险透视", styles["heading"]))
    story.append(
        Paragraph(
            _safe(
                compliance.get("summary", {}).get("phase_summary")
                or f"确认违规案例 {compliance.get('summary', {}).get('total_cases', 0)} 条，涉及事件 {compliance.get('summary', {}).get('event_count', 0)} 个。"
            ),
            styles["body"],
        )
    )
    for item in compliance.get("summary", {}).get("risk_levels", []):
        story.append(
            Paragraph(
                _safe(f"风险等级：{item.get('label')} / 次数：{item.get('count')}"),
                styles["body"],
            )
        )
    for item in compliance.get("summary", {}).get("categories", [])[:8]:
        story.append(
            Paragraph(
                _safe(f"主要违规类别：{item.get('label')} / 次数：{item.get('count')}"),
                styles["body"],
            )
        )

    story.append(Paragraph("第四部分：未来趋势与战略预警", styles["heading"]))
    for topic in forecast.get("topics", []):
        story.append(
            Paragraph(_safe(topic.get("topic_name", "重点议题")), styles["subheading"])
        )
        if topic.get("background"):
            story.append(Paragraph(_safe(topic["background"]), styles["body"]))
        summary_parts = []
        points = topic.get("points", []) or []
        audience = topic.get("audience") or next(
            (point.get("audience") for point in points if point.get("audience")),
            "",
        )
        scene_opening = topic.get("scene_opening") or next(
            (point.get("scene") for point in points if point.get("scene")),
            "",
        )
        if topic.get("main_tension"):
            summary_parts.append(f"核心矛盾：{topic.get('main_tension')}")
        if audience:
            summary_parts.append(f"涉及人群：{audience}")
        if scene_opening:
            summary_parts.append(f"典型场景：{scene_opening}")
        if summary_parts:
            story.append(
                Paragraph(
                    _safe(f"预警摘要：{'；'.join(summary_parts)}"), styles["body"]
                )
            )
        for point in points:
            story.append(
                Paragraph(_safe(point.get("subtitle", "风险点")), styles["subheading"])
            )
            story.append(
                Paragraph(_safe(_forecast_point_paragraph(point)), styles["body"])
            )

    story.append(Paragraph("附录：违规数据监测", styles["heading"]))
    for event in report_doc.get("appendix_cases", []):
        story.append(
            Paragraph(_safe(event.get("event_name", "未知事件")), styles["subheading"])
        )
        for case in event.get("cases", []):
            story.append(
                Paragraph(
                    _safe(
                        f"[{case.get('source_type')}] {case.get('category')} / {case.get('risk_level')}<br/>"
                        f"所属事件：{case.get('event_name') or event.get('event_name')}<br/>"
                        f"违规摘录：{case.get('quote')}<br/>"
                        f"判定理由：{case.get('reasoning')}<br/>"
                        f"主要依据：{case.get('primary_law')}<br/>"
                        f"{'法规说明：' + case.get('law_reason') + '<br/>' if case.get('law_reason') else ''}"
                        f"证据链：{case.get('evidence_chain')}<br/>"
                        f"处置建议：{case.get('disposal_suggestion')}"
                    ),
                    styles["body"],
                )
            )

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )
    doc.build(story)
    return output_path


def save_report_pdf(report_doc: dict, output_path: str) -> str:
    try:
        return _save_pdf_with_playwright(report_doc, output_path)
    except Exception as e:
        logger.warning(f" [PDF] Playwright 渲染失败，回退 xhtml2pdf: {e}")
    try:
        return _save_pdf_with_xhtml2pdf(report_doc, output_path)
    except Exception as e:
        logger.warning(f" [PDF] HTML 转 PDF 失败，回退 ReportLab: {e}")
        return _save_pdf_with_reportlab(report_doc, output_path)

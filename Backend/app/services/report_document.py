from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List


REPORT_RENDER_VERSION = "report_json_v2"


def _clean_event_name(value: str) -> str:
    return (value or "").strip().strip("#").strip()


def _format_heat(value: Any) -> str:
    try:
        numeric = int(value or 0)
    except (TypeError, ValueError):
        return str(value or "0")
    return f"{numeric / 10000:.1f}万" if numeric >= 10000 else str(numeric)


def _extract_date(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) >= 10:
        return text[:10]
    return datetime.now().strftime("%Y-%m-%d")


def build_overview_rows(core_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen_names = set()
    for event in core_events or []:
        event_name = _clean_event_name(
            event.get("event_name") or event.get("topic") or "未知事件"
        )
        if not event_name or event_name in seen_names:
            continue
        seen_names.add(event_name)
        rows.append(
            {
                "seq": len(rows) + 1,
                "time": _extract_date(event.get("created_at")),
                "event_name": event_name,
                "heat_value": _format_heat(event.get("total_heat", 0)),
            }
        )
    return rows


def _first_law_text(matched_laws: List[Any]) -> str:
    if not matched_laws:
        return "-"
    first = matched_laws[0]
    if isinstance(first, str):
        return first.strip() or "-"
    first = first or {}
    category = first.get("category") or "未匹配条款"
    article = first.get("article") or "未标注条款"
    return f"{category} / {article}"


def _truncate_text(text: str, limit: int = 80) -> str:
    raw = (text or "").strip()
    if len(raw) <= limit:
        return raw
    return raw[:limit].rstrip() + "..."


def _build_evidence_chain(case: Dict[str, Any], result: Dict[str, Any]) -> str:
    source_type = (case.get("source_type") or "").lower()
    quote = _truncate_text(case.get("quote") or "", limit=80)
    post_text = _truncate_text(result.get("post_content") or "", limit=80)
    if source_type == "comment":
        parts = []
        if post_text:
            parts.append(f"所属帖子：{post_text}")
        if quote:
            parts.append(f"评论原文：{quote}")
        return "；".join(parts) or "已记录原始评论与所属帖子上下文"
    if quote:
        return f"帖子原文：{quote}"
    if post_text:
        return f"帖子原文：{post_text}"
    return "已记录原始内容上下文"


def _build_compliance_phase_summary(
    total_cases: int,
    event_count: int,
    risk_counts: Dict[str, int],
    category_counts: Dict[str, int],
) -> str:
    if total_cases <= 0:
        return "本期未检出需要重点处置的违规内容，整体风险可控。"

    high = risk_counts.get("High", 0)
    medium = risk_counts.get("Medium", 0)
    low = risk_counts.get("Low", 0)
    top_categories = [
        name
        for name, _ in sorted(
            category_counts.items(), key=lambda item: item[1], reverse=True
        )[:3]
    ]

    parts = [f"本期共确认违规案例 {total_cases} 条，涉及事件 {event_count} 个。"]
    if high:
        parts.append(f"其中高风险案例 {high} 条，为当前处置重点。")
    elif medium:
        parts.append(f"当前以中风险案例为主，共 {medium} 条。")
    elif low:
        parts.append(f"当前以低风险案例为主，共 {low} 条。")
    if top_categories:
        parts.append(f"主要集中在：{'、'.join(top_categories)}。")
    return "".join(parts)


def _compose_forecast_summary_paragraph(point: Dict[str, Any]) -> str:
    explicit = (point.get("summary_paragraph") or "").strip()
    if explicit:
        return explicit

    content = (point.get("content") or "").strip()
    audience = (point.get("audience") or "").strip()
    scene = (point.get("scene") or "").strip()
    evolution_path = (point.get("evolution_path") or "").strip()

    # 兼容旧字段：历史数据可能仍含 trigger/spread/offline/online
    trigger = (point.get("trigger") or "").strip()
    spread_path = (point.get("spread_path") or "").strip()
    offline_scene = (point.get("offline_scene") or "").strip()
    online_scene = (point.get("online_scene") or "").strip()
    evidence_basis = [
        str(item).strip()
        for item in (point.get("evidence_basis") or [])
        if str(item).strip()
    ]

    lead_parts: List[str] = []
    if scene:
        lead_parts.append(f"最容易点燃讨论的往往是{scene}")
    elif trigger:
        lead_parts.append(f"一旦{trigger}")

    if audience:
        lead_parts.append(f"首批被卷入的通常是{audience}")

    if evolution_path:
        lead_parts.append(f"讨论常会沿着“{evolution_path}”这条路径被持续推高")
    elif spread_path:
        lead_parts.append(f"相关讨论很可能沿着{spread_path}迅速扩散")

    if not scene and (offline_scene or online_scene):
        scene_parts: List[str] = []
        if offline_scene:
            scene_parts.append(offline_scene)
        if online_scene:
            scene_parts.append(online_scene)
        lead_parts.append(f"并在{'、'.join(scene_parts)}等场景中持续放大")

    lead = "，".join(lead_parts).strip("，")
    if lead:
        lead += "。"

    basis = ""
    if evidence_basis:
        basis = f"这一判断综合参考了{'；'.join(evidence_basis[:2])}。"

    if content:
        return f"{lead}{content}{basis}".strip()
    return f"{lead}{basis}".strip()


def _normalize_preface_text(value: Any) -> str:
    return str(value or "").strip()


def build_preface_paragraphs(preface: Any) -> List[str]:
    if not preface:
        return []

    return [
        _normalize_preface_text(item)
        for item in (getattr(preface, "paragraphs", []) or [])
        if _normalize_preface_text(item)
    ]


def _build_forecast_topics(trend_forecast: Dict[str, Any]) -> Dict[str, Any]:
    topics = []
    for topic in trend_forecast.get("topics") or []:
        topic_points = []
        for point in topic.get("points") or []:
            point_copy = dict(point)
            point_copy["summary_paragraph"] = _compose_forecast_summary_paragraph(
                point_copy
            )
            topic_points.append(point_copy)
        topic_copy = dict(topic)
        topic_copy["points"] = topic_points
        topics.append(topic_copy)

    return {
        "target_period": trend_forecast.get("target_period") or "",
        "evidence_sources": trend_forecast.get("evidence_sources") or [],
        "topics": topics,
    }


def build_compliance_cases(audit_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []

    for result in audit_results or []:
        info = result.get("violation_info") or {}
        evidence = info.get("evidence_report") or {}
        event_name = result.get("event_name") or "未知事件"
        risk_level = info.get("overall_risk_level") or "Low"
        primary_law = _first_law_text(info.get("matched_laws") or [])
        disposal_suggestion = evidence.get("disposal_suggestion") or "建议人工研判"

        post_case = info.get("post_case")
        if post_case or info.get("is_post_violated"):
            post_primary_law = (post_case or {}).get("primary_law") or primary_law
            if not post_primary_law:
                post_primary_law = ""
            post_source_id = (
                (post_case or {}).get("source_id") or result.get("note_id") or ""
            )
            post_index = (post_case or {}).get("index")
            if post_index is None:
                post_index = -1
            cases.append(
                {
                    "event_name": event_name,
                    "source_type": "帖子",
                    "source_id": post_source_id,
                    "index": post_index,
                    "category": (post_case or {}).get("category")
                    or info.get("category")
                    or "未标注类别",
                    "risk_level": risk_level,
                    "quote": _truncate_text(
                        (post_case or {}).get("quote")
                        or result.get("post_content")
                        or "",
                        limit=120,
                    ),
                    "reasoning": (post_case or {}).get("reasoning")
                    or evidence.get("reasoning")
                    or "主帖触达平台规则边界",
                    "primary_law": post_primary_law,
                    "law_reason": (post_case or {}).get("law_reason") or "",
                    "evidence_chain": _build_evidence_chain(post_case or {}, result),
                    "disposal_suggestion": (post_case or {}).get("disposal_suggestion")
                    or disposal_suggestion,
                }
            )
            if not post_primary_law:
                cases.pop()

        comment_cases = info.get("comment_cases") or []
        if comment_cases:
            for detail in comment_cases:
                detail_primary_law = detail.get("primary_law") or primary_law
                if not detail_primary_law:
                    continue
                cases.append(
                    {
                        "event_name": event_name,
                        "source_type": "评论",
                        "source_id": detail.get("source_id") or "",
                        "index": detail.get("index", -1),
                        "category": detail.get("category") or "未标注类别",
                        "risk_level": detail.get("risk_level") or risk_level,
                        "quote": _truncate_text(detail.get("quote") or "", limit=120),
                        "reasoning": detail.get("reasoning")
                        or evidence.get("reasoning")
                        or "评论触达平台规则边界",
                        "primary_law": detail_primary_law,
                        "law_reason": detail.get("law_reason") or "",
                        "evidence_chain": _build_evidence_chain(detail, result),
                        "disposal_suggestion": detail.get("disposal_suggestion")
                        or disposal_suggestion,
                    }
                )
        else:
            comment_details = {
                int(item.get("index", -1)): item
                for item in info.get("violated_comments") or []
            }
            for original in result.get("violated_comment_originals") or []:
                index = int(original.get("index", -1))
                detail = comment_details.get(index, {})
                if not primary_law:
                    continue
                cases.append(
                    {
                        "event_name": event_name,
                        "source_type": "评论",
                        "source_id": detail.get("source_id") or "",
                        "index": index,
                        "category": original.get("category")
                        or detail.get("category")
                        or "未标注类别",
                        "risk_level": original.get("risk_level") or risk_level,
                        "quote": _truncate_text(
                            original.get("content") or "", limit=120
                        ),
                        "reasoning": detail.get("reasoning")
                        or evidence.get("reasoning")
                        or "评论触达平台规则边界",
                        "primary_law": primary_law,
                        "law_reason": detail.get("law_reason") or "",
                        "evidence_chain": _build_evidence_chain(
                            detail or original, result
                        ),
                        "disposal_suggestion": disposal_suggestion,
                    }
                )

    return cases


def build_report_document(
    state_data: Dict[str, Any], markdown: str = "", preface: Any = None
) -> Dict[str, Any]:
    core_events = state_data.get("core_events", [])
    analyzed_events = state_data.get("analyzed_events", [])
    audit_results = state_data.get("audit_results", [])
    trend_forecast = _build_forecast_topics(state_data.get("trend_forecast", {}) or {})
    category = state_data.get("category", "综合")
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    deep_reads = []
    for item in analyzed_events or []:
        report = item.get("opinion_report") or {}
        deep_reads.append(
            {
                "event_name": item.get("event_name") or "未知事件",
                "editorial_title": report.get("editorial_title")
                or item.get("event_name")
                or "重点舆情",
                "one_line_verdict": report.get("one_line_verdict")
                or report.get("event_overview")
                or "",
                "event_overview": report.get("event_overview") or "",
                "public_opinions": report.get("public_opinions") or [],
                "depth_analysis": report.get("depth_analysis") or "",
                "key_quotes": report.get("key_quotes") or [],
            }
        )

    compliance_cases = build_compliance_cases(audit_results)
    cases_by_event: Dict[str, List[Dict[str, Any]]] = {}
    risk_counts: Dict[str, int] = {}
    category_counts: Dict[str, int] = {}
    law_counts: Dict[str, int] = {}
    for case in compliance_cases:
        cases_by_event.setdefault(case["event_name"], []).append(case)
        risk_counts[case["risk_level"]] = risk_counts.get(case["risk_level"], 0) + 1
        category_counts[case["category"]] = category_counts.get(case["category"], 0) + 1
        law_key = case.get("primary_law") or ""
        if not law_key:
            continue
        law_counts[law_key] = law_counts.get(law_key, 0) + 1

    return {
        "meta": {
            "title": f"舆情研判报告（{category}）",
            "category": category,
            "generated_at": generated_at,
            "task_id": state_data.get("task_id", ""),
            "report_period": preface.report_period if preface else "",
            "render_version": REPORT_RENDER_VERSION,
        },
        "preface": {
            "report_period": getattr(preface, "report_period", ""),
            "paragraphs": build_preface_paragraphs(preface),
        },
        "overview_table": build_overview_rows(core_events),
        "deep_reads": deep_reads,
        "forecast": trend_forecast,
        "compliance": {
            "summary": {
                "total_cases": len(compliance_cases),
                "event_count": len(cases_by_event),
                "risk_levels": [
                    {"label": label, "count": count}
                    for label, count in sorted(
                        risk_counts.items(),
                        key=lambda item: {"High": 3, "Medium": 2, "Low": 1}.get(
                            item[0], 0
                        ),
                        reverse=True,
                    )
                ],
                "categories": [
                    {"label": label, "count": count}
                    for label, count in sorted(
                        category_counts.items(), key=lambda item: item[1], reverse=True
                    )
                ],
                "laws": [
                    {"label": label, "count": count}
                    for label, count in sorted(
                        law_counts.items(), key=lambda item: item[1], reverse=True
                    )
                ],
                "phase_summary": _build_compliance_phase_summary(
                    len(compliance_cases),
                    len(cases_by_event),
                    risk_counts,
                    category_counts,
                ),
            },
            "events": [
                {"event_name": event_name, "cases": cases}
                for event_name, cases in cases_by_event.items()
            ],
        },
        "appendix_cases": [
            {"event_name": event_name, "cases": cases}
            for event_name, cases in cases_by_event.items()
        ],
        "appendix_stats": {
            "risk_levels": [
                {"label": label, "count": count}
                for label, count in sorted(
                    risk_counts.items(),
                    key=lambda item: {"High": 3, "Medium": 2, "Low": 1}.get(item[0], 0),
                    reverse=True,
                )
            ],
            "categories": [
                {"label": label, "count": count}
                for label, count in sorted(
                    category_counts.items(), key=lambda item: item[1], reverse=True
                )
            ],
            "laws": [
                {"label": label, "count": count}
                for label, count in sorted(
                    law_counts.items(), key=lambda item: item[1], reverse=True
                )
            ],
        },
    }

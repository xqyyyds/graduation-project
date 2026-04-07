from typing import Any, Dict, List

from app.core.logger import logger
from app.agents.state import GraphState

MAX_RETRIES = 3


def _check_b(state: GraphState) -> Dict[str, Any]:
    analyzed_events = state.get("analyzed_events", []) or []
    issues: List[str] = []

    if len(analyzed_events) < 5:
        issues.append(f"深读事件数量不足：当前 {len(analyzed_events)} 个")

    for idx, event in enumerate(analyzed_events[:5], start=1):
        report = event.get("opinion_report") or {}
        for field in [
            "editorial_title",
            "one_line_verdict",
            "event_overview",
            "public_opinions",
            "depth_analysis",
            "key_quotes",
        ]:
            value = report.get(field)
            if not value:
                issues.append(f"深读事件{idx} 缺少字段 {field}")
        if len(report.get("key_quotes") or []) < 2:
            issues.append(f"深读事件{idx} 关键引述不足 2 条")

    return {"passed": not issues, "issues": issues}


def _check_c(state: GraphState) -> Dict[str, Any]:
    audit_results = state.get("audit_results", []) or []
    issues: List[str] = []

    def _check_trace_fields(case: Dict[str, Any], prefix: str):
        for field in ["source_type", "source_id", "index"]:
            if case.get(field) in (None, ""):
                issues.append(f"{prefix} 缺少字段 {field}")

    for idx, result in enumerate(audit_results, start=1):
        info = result.get("violation_info") or {}
        for case in info.get("comment_cases") or []:
            _check_trace_fields(case, f"审核事件{idx} 评论 case")
            for field in [
                "quote",
                "category",
                "reasoning",
                "primary_law",
                "disposal_suggestion",
            ]:
                if not case.get(field):
                    issues.append(f"审核事件{idx} 评论 case 缺少字段 {field}")
        post_case = info.get("post_case")
        if post_case:
            _check_trace_fields(post_case, f"审核事件{idx} 主帖 case")
            for field in [
                "quote",
                "category",
                "reasoning",
                "primary_law",
                "disposal_suggestion",
            ]:
                if not post_case.get(field):
                    issues.append(f"审核事件{idx} 主帖 case 缺少字段 {field}")

    return {"passed": not issues, "issues": issues}


def _check_d(state: GraphState) -> Dict[str, Any]:
    forecast = state.get("trend_forecast", {}) or {}
    topics = forecast.get("topics") or []
    issues: List[str] = []

    if not (3 <= len(topics) <= 5):
        issues.append(f"预测主题数量异常：当前 {len(topics)} 个")

    topic_names = [str(topic.get("topic_name", "")).strip() for topic in topics]
    if len([name for name in topic_names if name]) != len(
        set([name for name in topic_names if name])
    ):
        issues.append("预测主题存在重复标题，议题区分度不足")

    for idx, topic in enumerate(topics, start=1):
        if len(topic.get("points") or []) < 2:
            issues.append(f"预测主题{idx} 缺少至少 2 个预测点")
        for field in ["topic_name", "background", "main_tension"]:
            if not topic.get(field):
                issues.append(f"预测主题{idx} 缺少字段 {field}")
        for point_idx, point in enumerate(topic.get("points") or [], start=1):
            # 新契约：点级场景推演字段
            for field in [
                "subtitle",
                "audience",
                "scene",
                "evolution_path",
                "evidence_basis",
                "summary_paragraph",
            ]:
                if not point.get(field):
                    issues.append(f"预测主题{idx}-点{point_idx} 缺少字段 {field}")

            # 兼容旧口径：若缺少新字段但存在旧字段，可视为部分通过（但仍提示）
            if not point.get("scene") and (
                point.get("trigger")
                or point.get("offline_scene")
                or point.get("online_scene")
            ):
                issues.append(
                    f"预测主题{idx}-点{point_idx} 使用了旧场景字段，请迁移到 scene"
                )
            if not point.get("evolution_path") and point.get("spread_path"):
                issues.append(
                    f"预测主题{idx}-点{point_idx} 使用了旧传播字段，请迁移到 evolution_path"
                )

            summary = str(point.get("summary_paragraph") or "").strip()
            if summary:
                if len(summary) < 120:
                    issues.append(f"预测主题{idx}-点{point_idx} summary_paragraph 过短")

            evidence_basis = point.get("evidence_basis") or []
            if len(evidence_basis) < 2:
                issues.append(f"预测主题{idx}-点{point_idx} 依据不足 2 条")

    return {"passed": not issues, "issues": issues}


def quality_gate_bc_node(state: GraphState) -> Dict[str, Any]:
    logger.info("\n [Gate BC] 规则检查...")
    b_result = _check_b(state)
    c_result = _check_c(state)
    feedback = []
    if b_result["issues"]:
        feedback.extend([f"B: {item}" for item in b_result["issues"][:5]])
    if c_result["issues"]:
        feedback.extend([f"C: {item}" for item in c_result["issues"][:5]])

    return {
        "quality_scores": {
            "agent_b_analyze": b_result,
            "agent_c": c_result,
        },
        "supervisor_feedback": "；".join(feedback) or "B/C 结构检查通过",
        "current_step": "GateBC_Done",
    }


def quality_gate_d_node(state: GraphState) -> Dict[str, Any]:
    logger.info("\n [Gate D] 规则检查...")
    d_result = _check_d(state)
    if d_result.get("passed", True):
        feedback = "D 结构检查通过"
    else:
        feedback = "请重写预测正文：确保3-5个议题、每议题至少2个风险点，段落自然包含应对建议并保持正式研判文风。"
    scores = dict(state.get("quality_scores", {}) or {})
    scores["agent_d"] = d_result
    return {
        "quality_scores": scores,
        "supervisor_feedback": feedback,
        "current_step": "GateD_Done",
    }


def route_after_bc_gate(state: GraphState):
    logger.info("    [Route BC] B/C 仅做规则检查，不触发整体回炉 → D")
    return "continue_to_d"


def route_after_d_gate(state: GraphState) -> str:
    scores = state.get("quality_scores", {}) or {}
    retries = state.get("retry_count", {}) or {}
    d_result = scores.get("agent_d", {}) or {}

    if d_result.get("passed", True):
        logger.info("    [Route D] 通过 → 报告生成")
        return "continue_to_e"

    if retries.get("agent_d", 0) < MAX_RETRIES:
        logger.info(
            f"    [Route D] 预测质量未达标 → 重跑 D ({retries.get('agent_d', 0)+1}/{MAX_RETRIES})"
        )
        return "retry_d"

    logger.info("    [Route D] D 重试已满，降级放行")
    return "continue_to_e"


def retry_counter_b_node(state: GraphState) -> Dict[str, Any]:
    retry = dict(state.get("retry_count", {}) or {})
    retry["agent_b_analyze"] = retry.get("agent_b_analyze", 0) + 1
    return {"retry_count": retry}


def retry_counter_c_node(state: GraphState) -> Dict[str, Any]:
    retry = dict(state.get("retry_count", {}) or {})
    retry["agent_c"] = retry.get("agent_c", 0) + 1
    return {"retry_count": retry}


def retry_counter_d_node(state: GraphState) -> Dict[str, Any]:
    retry = dict(state.get("retry_count", {}) or {})
    retry["agent_d"] = retry.get("agent_d", 0) + 1
    return {"retry_count": retry}

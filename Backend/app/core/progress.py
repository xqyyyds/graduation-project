from typing import Any


STAGE_ORDER = ["prepare", "deep_read", "compliance", "forecast", "report", "done"]
STAGE_LABELS = {
    "prepare": "数据准备",
    "deep_read": "深读分析",
    "compliance": "违规审核",
    "forecast": "趋势预测",
    "report": "报告组装",
    "done": "导出完成",
}
STAGE_WEIGHTS = {
    "prepare": 15,
    "deep_read": 20,
    "compliance": 30,
    "forecast": 15,
    "report": 18,
    "done": 2,
}


def _normalize_stage_id(stage_id: str) -> str:
    return stage_id if stage_id in STAGE_ORDER else "prepare"


def build_progress_payload(stage_id: str, stage_progress: int, message: str) -> dict[str, Any]:
    normalized_stage = _normalize_stage_id(stage_id)
    clamped_progress = max(0, min(100, int(stage_progress)))
    completed_weight = sum(
        STAGE_WEIGHTS[item]
        for item in STAGE_ORDER[: STAGE_ORDER.index(normalized_stage)]
    )
    current_weight = STAGE_WEIGHTS[normalized_stage]
    overall_progress = round(completed_weight + current_weight * clamped_progress / 100)

    if normalized_stage == "done":
        overall_progress = 100

    return {
        "stage_id": normalized_stage,
        "stage_label": STAGE_LABELS[normalized_stage],
        "stage_progress": clamped_progress,
        "overall_progress": overall_progress,
        "message": message,
    }

import operator
from typing import List, Dict, Any, Annotated, TypedDict, Optional, Literal

# 🔥 新增导入：LangGraph 的消息管理利器
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


# 有效类别常量定义
VALID_CATEGORIES = ["综合", "社会", "高校", "生活", "科技", "政治", "其他"]
CategoryType = Literal["综合", "社会", "高校", "生活", "科技", "政治", "其他"]


# 定义状态字典
class GraphState(TypedDict):
    """
    定义 LangGraph 在各个节点间传递的数据结构。
    """

    # === 1. 核心会话管理 ===
    messages: Annotated[list[BaseMessage], add_messages]

    # === 2. 基础输入 ===
    task_id: str
    user_query: str

    # 🔥 [新增] ETL 时间窗口参数 (用户输入)
    start_date: Optional[str]  # "YYYY-MM-DD HH:MM:SS"
    end_date: Optional[str]  # "YYYY-MM-DD HH:MM:SS"

    # 🔥 [新增] 趋势预测时间范围 (1w/2w/1m/2m)
    forecast_range: Optional[str]  # "1w", "2w", "1m", "2m"

    # 🔥 [新增] 类别筛选 (综合/社会/高校/生活/科技/政治/其他)
    category: Optional[str]  # 默认 "综合" 表示不筛选类别

    # === 3. Agent A (统计分析师) 的产出 ===
    raw_trends: List[Dict]
    core_events: List[Dict]  # 这里会包含由 ETL 归并后的数据

    # === 4. Agent B (舆情观点分析师) 的产出 ===
    analyzed_events: List[Dict]

    # === 5. Agent C (合规审查官) 的产出 ===
    pending_posts: List[Dict]
    audit_results: List[Dict]

    # === 6. Agent D (趋势预测师) 的产出 ===
    # 🔥 修改：改为 Any 或 Dict，因为 Agent D 返回的是 TrendForecastReport 对象(字典)
    trend_forecast: Dict[str, Any]

    # === 7. Agent E (前言/最终报告) 的产出 ===
    final_report: str

    # 🔥 [新增] 违规统计数据 (用于存入 report_sessions 供 Dashboard 聚合)
    violation_stats: Dict[str, int]

    # === 8. 系统控制字段 ===
    error: str
    current_step: str

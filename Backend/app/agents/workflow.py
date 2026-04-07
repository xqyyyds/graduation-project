from langgraph.graph import StateGraph, START, END

# 1. 引入同级目录下的 State
from app.agents.state import GraphState

# 2. 引入同级目录下的 Nodes
from app.agents.nodes import (
    classify_node,
    agent_a_node,
    agent_b_analyze_node,
    agent_c_node,
    # agent_historical_node,  # 暂不启用
    agent_d_node,
    agent_e_node,
)

# 3. 引入 LLM 质量门控
from app.agents.quality_gate import (
    quality_gate_bc_node,
    quality_gate_d_node,
    route_after_bc_gate,
    route_after_d_gate,
    retry_counter_d_node,
)


# =====================================================
# 条件路由逻辑
# =====================================================
def should_continue(state: GraphState):
    """
    检查 Agent A 是否产出有效数据。
    有数据 → 并行启动 B 和 C；无数据 → 终止。
    """
    if not state.get("core_events"):
        return "end"
    return ["analyze", "audit"]  # 返回列表 → LangGraph 并行分叉


# =====================================================
# 构建工作流图 (Agent 协作架构 v2.0)
#
# 架构:
#   START → Classify → A(ETL+选题+抓取) → [B-Analyze ∥ C] → GateBC → D → GateD → E → END
#
# Agent A 承担全部前置工作:
# 1. ETL 数据清洗归并
# 2. 热度排序选题 Top N
# 3. 并行抓取帖子+评论，为 B/C 准备数据
# =====================================================


def create_workflow():
    # 1. 初始化图
    workflow = StateGraph(GraphState)

    # =========================================================
    # 2. 注册节点 (Nodes)
    # =========================================================

    # --- 数据准备阶段 ---
    workflow.add_node("node_classify", classify_node)  # Step 0: 热搜分类
    workflow.add_node("agent_a", agent_a_node)  # Step 1: ETL + 选题 + 数据抓取

    # --- 并行分析阶段 ---
    workflow.add_node("agent_b_analyze", agent_b_analyze_node)  # Step 2a: 深度分析
    workflow.add_node("agent_c", agent_c_node)  # Step 2b: 合规审查 (并行)

    # --- 质量门控阶段 ---
    workflow.add_node("quality_gate_bc", quality_gate_bc_node)  # Step 3: BC 质量评估
    # --- 趋势预测阶段 ---
    # workflow.add_node("agent_historical", agent_historical_node)  # 暂不启用
    workflow.add_node("agent_d", agent_d_node)  # Step 4: 趋势预测
    workflow.add_node("quality_gate_d", quality_gate_d_node)  # Step 5: D 质量评估
    workflow.add_node("retry_counter_d", retry_counter_d_node)  # 重试计数器 D

    # --- 报告生成阶段 ---
    workflow.add_node("agent_e", agent_e_node)  # Step 6: 生成报告

    # =========================================================
    # 3. 连接边 (Edges)
    # =========================================================

    # --- 线性准备阶段 ---
    workflow.add_edge(START, "node_classify")
    workflow.add_edge("node_classify", "agent_a")

    # Agent A 条件路由：有数据则并行启动 B + C，无数据则终止
    workflow.add_conditional_edges(
        "agent_a",
        should_continue,
        {
            "analyze": "agent_b_analyze",  # B 分析
            "audit": "agent_c",  # C 审查（与 B 并行）
            "end": END,
        },
    )

    # --- 汇聚：B 和 C 都完成后进入质量门控 ---
    workflow.add_edge("agent_b_analyze", "quality_gate_bc")
    workflow.add_edge("agent_c", "quality_gate_bc")

    # --- BC 质量门控路由 ---
    workflow.add_conditional_edges(
        "quality_gate_bc",
        route_after_bc_gate,
        {
            "continue_to_d": "agent_d",  # 通过 → D
        },
    )

    # --- BC 通过后：D → 质量门控 ---
    workflow.add_edge("agent_d", "quality_gate_d")
    # workflow.add_edge("agent_historical", "quality_gate_d")  # 暂不启用

    workflow.add_conditional_edges(
        "quality_gate_d",
        route_after_d_gate,
        {
            "continue_to_e": "agent_e",  # 通过 → 生成报告
            "retry_d": "retry_counter_d",  # D 不合格 → 重试
        },
    )

    workflow.add_edge("retry_counter_d", "agent_d")  # D 重试

    # --- 报告生成 → 结束 ---
    workflow.add_edge("agent_e", END)

    #  注意：不在这里 compile，方便 main.py 注入 memory
    return workflow


# 导出实例
workflow = create_workflow()

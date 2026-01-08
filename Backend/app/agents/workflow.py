from langgraph.graph import StateGraph, START, END

# 1. 引入同级目录下的 State
from app.agents.state import GraphState

# 2. 引入同级目录下的 Nodes
from app.agents.nodes import (
    classify_node,  # 新增：分类节点
    etl_node,
    agent_a_node,
    agent_b_node,
    agent_c_node,
    agent_d_node,
    agent_e_node,
)


# =====================================================
# 条件路由逻辑
# =====================================================
def should_continue(state: GraphState):
    """
    检查 ETL 是否成功。
    如果失败 (Empty 或 Error)，直接结束，避免后续 Agent 空跑。
    """
    if not state.get("core_events"):
        return "end"  # 路由到 END
    return "continue"  # 路由到 agent_a


# =====================================================
# 构建工作流图 (The Linear Pipeline)
# =====================================================


def create_workflow():
    # 1. 初始化图
    workflow = StateGraph(GraphState)

    # 2. 注册节点 (Nodes)
    # 这些函数已经在 nodes.py 里定义好了
    workflow.add_node("node_classify", classify_node)  # Step 0: 热搜分类（ETL 前置）
    workflow.add_node("node_etl", etl_node)  # Step 1: 数据归并
    workflow.add_node("agent_a", agent_a_node)  # Step 2: 热度统计
    workflow.add_node("agent_b", agent_b_node)  # Step 3: 观点分析 (耗时最长)
    workflow.add_node("agent_c", agent_c_node)  # Step 4: 合规审查
    workflow.add_node("agent_d", agent_d_node)  # Step 5: 趋势预测
    workflow.add_node("agent_e", agent_e_node)  # Step 6: 生成报告

    # 3. 连接边 (Edges)

    # 新增：先分类再 ETL
    workflow.add_edge(START, "node_classify")
    workflow.add_edge("node_classify", "node_etl")

    # 🔥 核心修改：增加条件路由，ETL 失败直接中断
    workflow.add_conditional_edges(
        "node_etl", should_continue, {"continue": "agent_a", "end": END}
    )

    workflow.add_edge("agent_a", "agent_b")
    # 解释：C 依赖 B 查回来的 '_fetched_posts' 数据，所以必须 B -> C
    workflow.add_edge("agent_b", "agent_c")
    # 解释：D 依赖 B 的观点总结和 C 的违规结论，所以必须 C -> D
    workflow.add_edge("agent_c", "agent_d")
    workflow.add_edge("agent_d", "agent_e")
    workflow.add_edge("agent_e", END)

    # ⚠️ 注意：不在这里 compile，方便 main.py 注入 memory
    return workflow


# 导出实例
workflow = create_workflow()

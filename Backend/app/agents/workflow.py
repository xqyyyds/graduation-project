from langgraph.graph import StateGraph, START, END

# 1. 引入同级目录下的 State
from app.agents.state import GraphState

# 2. 引入同级目录下的 Nodes
from app.agents.nodes import (
    etl_node,
    agent_a_node,
    agent_b_node,
    agent_c_node,
    agent_d_node,
    agent_e_node
)

# =====================================================
# 构建工作流图 (The Linear Pipeline)
# =====================================================

def create_workflow():
    # 1. 初始化图
    workflow = StateGraph(GraphState)

    # 2. 注册节点 (Nodes)
    # 这些函数已经在 nodes.py 里定义好了
    workflow.add_node("node_etl", etl_node)       # Step 1: 数据归并
    workflow.add_node("agent_a", agent_a_node)    # Step 2: 热度统计
    workflow.add_node("agent_b", agent_b_node)    # Step 3: 观点分析 (耗时最长)
    workflow.add_node("agent_c", agent_c_node)    # Step 4: 合规审查
    workflow.add_node("agent_d", agent_d_node)    # Step 5: 趋势预测
    workflow.add_node("agent_e", agent_e_node)    # Step 6: 生成报告

    # 3. 连接边 (Edges) - 线性逻辑
    # 逻辑：Start -> ETL -> A -> B -> C -> D -> E -> End
    
    workflow.add_edge(START, "node_etl")
    workflow.add_edge("node_etl", "agent_a")
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
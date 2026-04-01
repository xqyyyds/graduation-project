# =====================================================
# Agent 工厂模块 - 使用 LangChain 1.0+ create_agent
# =====================================================

from typing import List, Callable
from langchain_core.language_models import BaseChatModel
from langchain.agents import create_agent as _create_agent
from langgraph.graph.state import CompiledStateGraph


def create_agent(
    model: BaseChatModel,
    tools: List[Callable],
    system_prompt: str,
) -> CompiledStateGraph:
    """
    使用 LangChain 1.0+ 官方推荐的 create_agent 创建 Agent

    Args:
        model: LLM 模型实例 (BaseChatModel)
        tools: 工具函数列表
        system_prompt: 系统提示词

    Returns:
        编译后的 CompiledStateGraph
    """
    return _create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
    )

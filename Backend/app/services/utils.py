from app.core.config import settings
from app.core.logger import logger

# 使用官方 TavilyClient，不走 LangChain 包装
from tavily import TavilyClient
from langchain_core.tools import tool


@tool
def tavily_search(query: str) -> str:
    """
    搜索网络信息。用于查询历史同期舆情规律或未来政策日历。

    Args:
        query: 搜索查询词，必须包含具体时间和领域

    Returns:
        搜索结果摘要文本
    """
    return get_web_context(query, max_results=5, search_depth="advanced")


def get_web_context(
    query: str, max_results: int = 5, search_depth: str = "advanced"
) -> str:
    """
    联网搜索并返回清洗后的文本背景

    参数:
        query: 搜索关键词 (例如: "三峡大学留学生事件 官方通报")
        max_results: 最大返回结果数 (默认 5)
        search_depth: 搜索深度 "basic"(便宜) 或 "advanced"(贵，默认)

    返回:
        str: 拼接好的事实文本，如果失败则返回友好提示
    """
    if not settings.TAVILY_API_KEY:
        return "（系统提示：未配置 TAVILY_API_KEY，无法进行联网搜索）"

    logger.info(f"[Tools] 正在全网深度搜索: '{query}' (模式: {search_depth})...")

    try:
        # 使用官方 TavilyClient（最稳定）
        client = TavilyClient(api_key=settings.TAVILY_API_KEY)

        # 执行搜索，返回 dict
        response = client.search(
            query=query,
            search_depth=search_depth,
            max_results=max_results,
            topic="news",  # 搜索新闻
            include_answer=True,
            include_raw_content=False,
        )

        # 提取 results 列表
        results = response.get("results", [])

        if not results:
            return "（未检索到相关的互联网公开信息）"

        # 拼接结果为 LLM 易读的格式
        context_pieces = []
        for i, item in enumerate(results, 1):
            title = item.get("title", "").strip()
            url = item.get("url", "未知链接")
            content = item.get("content", "").strip()

            if len(content) > 10:
                context_pieces.append(f"【信源 {i}】{title}\n{content}\n(来源: {url})")

        return (
            "\n\n".join(context_pieces)
            if context_pieces
            else "（检索结果有效信息不足）"
        )

    except Exception as e:
        logger.error(f"[Tools] 联网搜索异常: {e}")
        return f"（由于网络或服务异常，联网搜索暂时不可用）"


def normalize_category(cat: str) -> str:
    """归一化违规类别文本（去首尾空白/标点、统一连字符、替换全角空格等）。

    目标：避免微小字符差异导致相同类别被拆成多个桶。
    """
    if not cat:
        return "其他"

    s = str(cat).strip()
    # 全角空格 -> 半角
    s = s.replace("\u3000", " ")
    # 统一短横与破折号为半角连字符
    s = s.replace("–", "-").replace("—", "-").replace("－", "-")
    # 去掉常见尾部标点（中英文）及多余空白
    s = s.strip().rstrip(".。,，、:：;；")
    # 收尾再次去空格
    s = s.strip()
    # 如果最终为空则返回默认
    return s if s else "其他"

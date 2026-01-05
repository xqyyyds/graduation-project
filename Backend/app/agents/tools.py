import logging
from app.core.config import settings

from langchain_community.tools.tavily_search import TavilySearchResults

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_web_context(query: str) -> str:
    """
    核心工具函数：联网搜索并返回清洗后的文本背景。

    参数:
        query: 搜索关键词 (例如: "三峡大学留学生事件 官方通报")
    返回:
        str: 拼接好的事实文本，如果失败则返回友好提示。
    """
    if not settings.TAVILY_API_KEY:
        return "（系统提示：未配置 TAVILY_API_KEY，无法进行联网搜索）"

    print(f"🌍 [Tools] 正在全网深度搜索: “{query}” ...")

    try:
        # 1. 初始化工具 (每次调用时初始化，无状态，轻量级)
        # 使用 advanced 模式以获取更深度的内容
        search_tool = TavilySearchResults(
            max_results=5,
            search_depth="advanced",
            include_answer=True,
            include_raw_content=False,
        )

        # 2. 执行搜索
        results = search_tool.invoke({"query": query})

        # 3. 结果校验
        if not results or not isinstance(results, list):
            logger.warning(f"搜索 '{query}' 未返回有效结果")
            return "（未检索到相关的互联网公开信息）"

        # 4. 数据清洗与拼接
        # 将 List[Dict] 转换为 LLM 易读的长字符串
        context_pieces = []
        for i, res in enumerate(results):
            content = res.get("content", "").strip()
            url = res.get("url", "未知链接")

            # 过滤过短的无效内容
            if len(content) > 10:
                context_pieces.append(f"【信源 {i+1}】{content}\n(来源: {url})")

        # 如果过滤完没东西了
        if not context_pieces:
            return "（检索结果有效信息不足）"

        return "\n\n".join(context_pieces)

    except Exception as e:
        logger.error(f"❌ 联网搜索发生异常: {e}")
        # 返回给 LLM 的提示，让它知道发生了什么，而不是直接报错崩溃
        return f"（由于网络或服务异常，联网搜索暂时不可用。异常信息: {str(e)}）"

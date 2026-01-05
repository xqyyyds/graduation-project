import json
from typing import List, Dict, Any

# LangChain 组件
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# 引入联网搜索工具 (如果你没有配 Tavily，可以暂时注释掉或换成 DuckDuckGo)
from langchain_community.tools.tavily_search import TavilySearchResults

# 引入配置
from app.core.config import settings

# 🔥 引入升级后的 Schema 和 Prompts
from app.core.schemas import PostOpinionSummary, EventAnalysisReport
from app.core.prompts import AGENT_B_MAP_TEMPLATE, AGENT_B_REDUCE_TEMPLATE


class AgentOpinions:
    """
    Agent B: 舆情观点分析师 (High-Precision Mode)
    核心架构：Search (查事实) + Map (多维观点聚类) -> Reduce (深度分层报告)
    """

    def __init__(self):
        # 初始化 LLM
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,  # 例如 "glm-4-flash"
            openai_api_key=settings.ZHIPU_API_KEY,
            openai_api_base=settings.LLM_BASE_URL,
            temperature=0.3,  # 稍微增加一点随机性以获取丰富观点
        )

        # 初始化结构化解析器
        self.map_parser = JsonOutputParser(pydantic_object=PostOpinionSummary)
        self.reduce_parser = JsonOutputParser(pydantic_object=EventAnalysisReport)

        # 初始化搜索工具 (用于获取官方事实)
        # 如果你没配 TAVILY_API_KEY，这里会报错，可以加 try-except
        try:
            self.search_tool = TavilySearchResults(max_results=3)
        except:
            self.search_tool = None
            print("⚠️ [Agent B] Tavily 搜索工具初始化失败，将跳过联网搜索。")

    def analyze_event(self, event_name: str, posts_data: List[Dict]) -> Dict[str, Any]:
        """
        全流程执行入口
        :param event_name: 事件名称
        :param posts_data: 列表，每个元素必须包含 {"content": str, "comments": List[str], "media_context": str}
        """
        print(f"🧐 [Agent B] 启动高精度舆情分析: “{event_name}”")

        # --- Step 1: Search (联网获取背景事实) ---
        web_context = "暂无网络背景信息"
        if self.search_tool:
            print(f"      🌐 [Search] 正在检索背景信息...")
            try:
                # 构造搜索词，确保获取官方口径
                search_query = f"{event_name} 事件详情 官方通报"
                search_res = self.search_tool.invoke(search_query)
                web_context = str(search_res)
            except Exception as e:
                print(f"      ❌ 搜索失败: {e}")

        # --- Step 2: Map (分批处理热门贴) ---
        print(f"📊 [Agent B] 正在扫描 {len(posts_data)} 个舆论战场(热门贴)...")

        # 预编译 Prompt 链，提高循环效率
        map_prompt = ChatPromptTemplate.from_template(AGENT_B_MAP_TEMPLATE).partial(
            format_instructions=self.map_parser.get_format_instructions()
        )
        map_chain = map_prompt | self.llm | self.map_parser

        map_results = []

        for i, post in enumerate(posts_data):
            try:
                # 调用 Map 逻辑
                summary = self._map_single_post(post, map_chain)
                map_results.append(summary)
            except Exception as e:
                print(f"      ⚠️ 帖子 {i+1} Map分析跳过: {e}")
                continue

        if not map_results:
            return {
                "event_overview": "有效观点过少，无法生成报告",
                "public_opinions": [],
                "depth_analysis": "数据不足",
            }

        # --- Step 3: Reduce (深度聚合) ---
        print(f"🧩 [Agent B] 正在聚合多维观点，生成深度报告 (Reduce)...")
        try:
            final_report = self._reduce_summaries(event_name, web_context, map_results)
            print(f"✅ [Agent B] 事件 “{event_name}” 分析完成。")

            # 返回字典供 State 存储
            # 如果 final_report 是 Pydantic 对象则 dump，如果是 dict 则直接返回
            if hasattr(final_report, "model_dump"):
                return final_report.model_dump()
            return final_report

        except Exception as e:
            print(f"❌ [Agent B] Reduce 阶段失败: {e}")
            return {
                "event_overview": "报告生成异常",
                "public_opinions": [],
                "depth_analysis": f"Error: {str(e)}",
            }

    def _map_single_post(self, post_data: Dict, chain: Any) -> PostOpinionSummary:
        """
        Map 逻辑：针对单个帖子进行【观点聚类】
        """
        # 1. 提取帖子内容
        post_content = post_data.get("content", "无内容")

        # 2. 提取媒体上下文 (由 Nodes.py 组装好的字符串)
        media_content = post_data.get("media_context", "无媒体链接")

        # 3. 提取评论 (Nodes.py 传进来的是 List[str])
        raw_comments = post_data.get("comments", [])

        # 截取评论文本 (虽然数据库查了200条，但为了防止Token爆炸，
        # 在 Prompt 里展示 100-150 条通常足够代表性，或者视模型上下文窗口而定)
        # 这里我们保守传 100 条，或者如果用的是 GLM-4-Plus 可以传更多
        if isinstance(raw_comments, list):
            comments_text = "\n".join([f"- {c}" for c in raw_comments[:120]])
        else:
            comments_text = str(raw_comments)[:3000]  # 兜底

        # 4. 调用 LLM
        # 注意：这里的 key 必须和 prompts.py 里的 AGENT_B_MAP_TEMPLATE 槽位名一致
        return chain.invoke(
            {
                "post_content": post_content,
                "media_content": media_content,  # 🔥 注入媒体上下文
                "comments_text": comments_text,
            }
        )

    def _reduce_summaries(
        self, event_name: str, web_context: str, map_results: List[PostOpinionSummary]
    ) -> EventAnalysisReport:
        """
        Reduce 逻辑：将碎片化的【观点簇】缝合成一份有层次感的报告
        """
        # 格式化 Map 结果
        mapped_text_list = []

        for i, res in enumerate(map_results):
            # 兼容性处理：防止 res 是 dict 而不是对象
            if isinstance(res, dict):
                # 如果是 dict，尝试转成 Pydantic 对象，或者直接读 key
                clusters = res.get("opinion_clusters", [])
                conflict = res.get("conflict_analysis", "无")
            else:
                clusters = res.opinion_clusters
                conflict = res.conflict_analysis

            # 遍历该帖子下的所有观点簇
            clusters_desc = []
            for cluster in clusters:
                # 兼容 cluster 可能是 dict
                if isinstance(cluster, dict):
                    ratio = cluster.get("estimated_ratio", "")
                    emotion = cluster.get("emotion", "")
                    viewpoint = cluster.get("viewpoint", "")
                else:
                    ratio = cluster.estimated_ratio
                    emotion = cluster.emotion
                    viewpoint = cluster.viewpoint

                clusters_desc.append(f"[{ratio} - {emotion}]: {viewpoint}")

            cluster_text = "; ".join(clusters_desc)

            entry = (
                f"【帖子{i+1} 分析切片】\n"
                f"   - 冲突分析: {conflict}\n"
                f"   - 观点分布: {cluster_text}"
            )
            mapped_text_list.append(entry)

        # 拼成一个超长文本喂给 Reduce LLM
        mapped_summaries = "\n\n".join(mapped_text_list)

        # 调用 LLM
        prompt = ChatPromptTemplate.from_template(AGENT_B_REDUCE_TEMPLATE).partial(
            format_instructions=self.reduce_parser.get_format_instructions()
        )

        chain = prompt | self.llm | self.reduce_parser

        return chain.invoke(
            {
                "event_name": event_name,  # 注意 Prompt 里如果用了这个变量就要传
                "web_search_context": web_context,
                "mapped_summaries": mapped_summaries,
            }
        )


# 单例导出
agent_opinions = AgentOpinions()

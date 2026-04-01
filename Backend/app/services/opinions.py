from typing import List, Dict, Any
import concurrent.futures

# LangChain 组件
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

# from langchain_core.output_parsers import JsonOutputParser (已弃用，改用 with_structured_output)

# 引入配置
from app.core.config import settings
from app.core.logger import logger

#  引入升级后的 Schema 和 Prompts
from app.core.schemas import PostOpinionSummary, EventAnalysisReport
from app.core.prompts import AGENT_B_MAP_TEMPLATE, AGENT_B_REDUCE_TEMPLATE

# 引入联网搜索工具
from app.services.utils import get_web_context


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
            request_timeout=180,  #  增加超时时间
            max_retries=3,
        )

        # 初始化结构化解析器 (已弃用，改用 with_structured_output)
        # self.map_parser = JsonOutputParser(pydantic_object=PostOpinionSummary)
        # self.reduce_parser = JsonOutputParser(pydantic_object=EventAnalysisReport)

    def analyze_event(
        self,
        event_name: str,
        posts_data: List[Dict],
        start_date: str = "",
        end_date: str = "",
        improvement_hint: str = "",
    ) -> Dict[str, Any]:
        """
        全流程执行入口
        :param event_name: 事件名称
        :param posts_data: 列表，每个元素必须包含 {"content": str, "comments": List[str], "media_context": str}
        :param improvement_hint: 质量门控反馋（重试时注入）
        """
        logger.info(f" [Agent B] 启动高精度舆情分析: “{event_name}”")

        start_date = (start_date or "").strip()
        end_date = (end_date or "").strip()
        if start_date and end_date:
            report_period = f"{start_date} 至 {end_date}"
            period_hint = f"{start_date[:10]}~{end_date[:10]}"
        elif start_date or end_date:
            report_period = (
                f"{start_date or '开始时间未知'} 至 {end_date or '结束时间未知'}"
            )
            period_hint = (
                start_date[:10] if start_date else (end_date[:10] if end_date else "")
            )
        else:
            report_period = "本期"
            period_hint = ""

        # --- Step 1: Search (联网获取背景事实) ---
        web_context = "暂无网络背景信息"
        logger.info(f"       [Search] 正在检索背景信息...")
        try:
            # 构造搜索词，确保获取官方口径
            search_query = f"{event_name} {period_hint} 事件详情 官方通报".strip()
            # 使用统一的 get_web_context 函数
            web_context = get_web_context(search_query, max_results=3, search_depth="basic")
        except Exception as e:
            logger.warning(f" [Agent B] 联网检索失败，将使用空背景: {e}")

        # --- Step 2: Map (分批处理热门贴) ---
        logger.info(f" [Agent B] 正在扫描 {len(posts_data)} 个舆论战场(热门贴)...")

        #  升级：使用 with_structured_output 替代 JsonOutputParser
        # 这样更稳定，且不需要在 Prompt 里塞 format_instructions
        structured_llm = self.llm.with_structured_output(PostOpinionSummary)
        map_prompt = ChatPromptTemplate.from_template(AGENT_B_MAP_TEMPLATE)
        map_chain = map_prompt | structured_llm

        def _select_comment_excerpts(raw_comments: Any, limit: int = 8) -> List[str]:
            if not raw_comments:
                return []
            if not isinstance(raw_comments, list):
                return [str(raw_comments)[:120]]

            excerpts: List[str] = []
            seen = set()
            for c in raw_comments:
                t = (c or "").strip()
                if len(t) < 8:
                    continue
                if t in seen:
                    continue
                seen.add(t)
                excerpts.append(t[:120])
                if len(excerpts) >= limit:
                    break
            return excerpts

        map_payloads: List[Dict[str, Any]] = []

        #  升级：并行处理 (ThreadPool) 加速 Map 阶段
        # 建议根据 API Rate Limit 调整 max_workers (例如 5-10)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            # 提交所有任务
            future_to_index = {
                executor.submit(self._map_single_post, post, map_chain): (i, post)
                for i, post in enumerate(posts_data)
            }

            for future in concurrent.futures.as_completed(future_to_index):
                i, post = future_to_index[future]
                try:
                    summary = future.result()
                    map_payloads.append(
                        {
                            "index": i,
                            "summary": summary,
                            "comment_excerpts": _select_comment_excerpts(
                                post.get("comments", []), limit=8
                            ),
                        }
                    )
                except Exception as e:
                    logger.warning(f"       帖子 {i+1} Map分析跳过: {e}")

        map_payloads.sort(key=lambda x: x.get("index", 0))

        if not map_payloads:
            return {
                "event_overview": "有效观点过少，无法生成报告",
                "public_opinions": [],
                "depth_analysis": "数据不足",
            }

        # --- Step 3: Reduce (深度聚合) ---
        logger.info(f" [Agent B] 正在聚合多维观点，生成深度报告 (Reduce)...")
        try:
            final_report = self._reduce_summaries(
                event_name=event_name,
                report_period=report_period,
                web_context=web_context,
                map_payloads=map_payloads,
                improvement_hint=improvement_hint,
            )
            logger.info(f" [Agent B] 事件 “{event_name}” 分析完成。")

            # 返回字典供 State 存储
            # 如果 final_report 是 Pydantic 对象则 dump，如果是 dict 则直接返回
            if hasattr(final_report, "model_dump"):
                return final_report.model_dump()
            return final_report

        except Exception as e:
            logger.error(f" [Agent B] Reduce 阶段失败: {e}")
            return {
                "event_overview": "报告生成异常",
                "public_opinions": [],
                "depth_analysis": f"Error: {str(e)}",
            }

    @staticmethod
    def _is_content_filter(e: Exception) -> bool:
        """判断异常是否为 LLM 内容安全过滤"""
        msg = str(e).lower()
        return any(kw in msg for kw in [
            "content_filter", "content filter", "content management",
            "sensitive", "refused", "refusal", "harmful",
            "responsibleaipolicy", "safety",
        ])

    def _map_single_post(self, post_data: Dict, chain: Any) -> PostOpinionSummary:
        """
        Map 逻辑：针对单个帖子进行【观点聚类】
        内容安全过滤时自动重试（截断评论后降级调用）
        """
        # 1. 提取帖子内容
        post_content = post_data.get("content", "无内容")

        # 2. 提取媒体上下文 (由 Nodes.py 组装好的字符串)
        media_content = post_data.get("media_context", "无媒体链接")

        # 3. 提取评论 (Nodes.py 传进来的是 List[str])
        raw_comments = post_data.get("comments", [])

        if isinstance(raw_comments, list):
            comments_text = "\n".join([f"- {c}" for c in raw_comments])
        else:
            comments_text = str(raw_comments)

        invoke_args = {
            "post_content": post_content,
            "media_content": media_content,
            "comments_text": comments_text,
            "improvement_hint": "",  # Map 阶段无需质量反馈
        }

        # 第一次尝试（全量数据）
        try:
            return chain.invoke(invoke_args)
        except Exception as e:
            if not self._is_content_filter(e):
                raise  # 非过滤异常直接上抛

        # 第二次尝试：截断评论到 30 条，降低敏感内容浓度
        logger.warning(" [Agent B] Map 触发内容过滤，截断评论后重试...")
        if isinstance(raw_comments, list):
            truncated = raw_comments[:30]
            comments_text = "\n".join([f"- {c}" for c in truncated])
        invoke_args["comments_text"] = comments_text

        try:
            return chain.invoke(invoke_args)
        except Exception as e2:
            if not self._is_content_filter(e2):
                raise

        # 第三次：只保留帖子正文，完全去掉评论
        logger.warning(" [Agent B] Map 二次过滤，去除评论后重试...")
        invoke_args["comments_text"] = "（评论数据因安全策略暂不可用）"
        return chain.invoke(invoke_args)  # 最后一次不再兜底，让上层跳过

    def _reduce_summaries(
        self,
        event_name: str,
        report_period: str,
        web_context: str,
        map_payloads: List[Dict[str, Any]],
        improvement_hint: str = "",
    ) -> EventAnalysisReport:
        """
        Reduce 逻辑：将碎片化的【观点簇】缝合成一份有层次感的报告
        """
        # 格式化 Map 结果
        mapped_text_list = []

        for i, payload in enumerate(map_payloads):
            res = (payload or {}).get("summary")
            comment_excerpts = (payload or {}).get("comment_excerpts") or []
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

            # 预处理评论摘录（f-string 中不能包含反斜杠）
            excerpts_lines = []
            for t in comment_excerpts[:8]:
                cleaned = str(t).replace("\n", " ")[:120]
                excerpts_lines.append(f"\n   - {cleaned}")
            excerpts_text = "".join(excerpts_lines)

            entry = (
                f"【帖子{i+1} 分析切片】\n"
                f"   - 冲突分析: {conflict}\n"
                f"   - 观点分布: {cluster_text}\n"
                f"   - 评论样本摘录:{excerpts_text if excerpts_text else '（无）'}"
            )
            mapped_text_list.append(entry)

        # 拼成一个超长文本喂给 Reduce LLM
        mapped_summaries = "\n\n".join(mapped_text_list)

        #  升级：使用 with_structured_output 替代 JsonOutputParser
        structured_llm = self.llm.with_structured_output(EventAnalysisReport)

        prompt = ChatPromptTemplate.from_template(AGENT_B_REDUCE_TEMPLATE)
        chain = prompt | structured_llm

        # 第一次尝试（全量 map 数据）
        try:
            return chain.invoke(
                {
                    "event_name": event_name,
                    "report_period": report_period,
                    "web_search_context": web_context,
                    "mapped_summaries": mapped_summaries,
                    "improvement_hint": improvement_hint or "",
                }
            )
        except Exception as e:
            if not self._is_content_filter(e):
                raise

        # 内容过滤 → 截断 map 数据到前 5 条后重试
        logger.warning(" [Agent B] Reduce 触发内容过滤，截断数据后重试...")
        truncated_summaries = "\n\n".join(mapped_text_list[:5])
        return chain.invoke(
            {
                "event_name": event_name,
                "report_period": report_period,
                "web_search_context": web_context,
                "mapped_summaries": truncated_summaries,
                "improvement_hint": (improvement_hint or "") + " (部分数据因安全策略已截断)",
            }
        )


# 单例导出
agent_opinions = AgentOpinions()

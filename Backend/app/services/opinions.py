from typing import Any, Dict, List
import concurrent.futures

from langchain_core.prompts import ChatPromptTemplate

from app.core.llm_factory import get_main_llm
from app.core.logger import logger
from app.core.prompts import AGENT_B_MAP_TEMPLATE, AGENT_B_REDUCE_TEMPLATE
from app.core.schemas import EventAnalysisReport, PostOpinionSummary
from app.services.utils import get_web_context


class AgentOpinions:
    """
    单模型版 Agent B：
    - 主模型逐帖切片
    - 主模型事件级成文
    """

    def __init__(self):
        self.map_llm = get_main_llm(
            temperature=0.2,
            request_timeout=120,
            max_retries=2,
        )
        self.reduce_llm = get_main_llm(
            temperature=0.4,
            request_timeout=180,
            max_retries=2,
        )

    @staticmethod
    def _is_content_filter(e: Exception) -> bool:
        msg = str(e).lower()
        return any(
            kw in msg
            for kw in [
                "content_filter",
                "content filter",
                "content management",
                "sensitive",
                "refused",
                "refusal",
                "harmful",
                "responsibleaipolicy",
                "safety",
            ]
        )

    @staticmethod
    def _is_timeout(e: Exception) -> bool:
        msg = str(e).lower()
        return any(kw in msg for kw in ["timed out", "timeout", "read timeout"])

    @staticmethod
    def _select_comment_excerpts(raw_comments: Any, limit: int = 8) -> List[str]:
        if not raw_comments:
            return []
        if not isinstance(raw_comments, list):
            return [str(raw_comments)[:120]]

        excerpts: List[str] = []
        seen = set()
        for item in raw_comments:
            if isinstance(item, dict):
                text = str(item.get("content") or "").strip()
            else:
                text = str(item or "").strip()
            if len(text) < 6 or text in seen:
                continue
            seen.add(text)
            excerpts.append(text[:120])
            if len(excerpts) >= limit:
                break
        return excerpts

    def _build_web_context(
        self,
        event_name: str,
        start_date: str,
        end_date: str,
    ) -> str:
        query_groups = [
            f"{event_name} 官方通报",
            f"{event_name} 最新进展",
            f"{event_name} 争议 焦点 网友质疑",
        ]
        if start_date or end_date:
            period = f"{start_date[:10] if start_date else ''} {end_date[:10] if end_date else ''}".strip()
            query_groups = [f"{q} {period}".strip() for q in query_groups]

        web_context_parts: List[str] = []
        for title, query in zip(["官方口径", "最新进展", "争议焦点"], query_groups):
            try:
                result = get_web_context(query, max_results=3, search_depth="basic")
                if result:
                    web_context_parts.append(f"【{title}】\n{result}")
            except Exception as e:
                logger.warning(f" [Agent B] 联网检索失败({title}): {e}")

        return (
            "\n\n".join(web_context_parts)
            if web_context_parts
            else "暂无可靠联网背景信息"
        )

    @staticmethod
    def _build_timeline_digest(map_payloads: List[Dict[str, Any]]) -> str:
        timeline_rows: List[Dict[str, str]] = []
        for payload in map_payloads:
            meta = payload.get("post_meta") or {}
            summary = payload.get("summary") or {}
            timeline_rows.append(
                {
                    "time": str(meta.get("create_date_time") or "").strip(),
                    "trigger": str(summary.get("trigger_summary") or "").strip(),
                    "propagation": str(summary.get("propagation_hint") or "").strip(),
                }
            )

        valid_rows = [
            row
            for row in timeline_rows
            if row["time"] or row["trigger"] or row["propagation"]
        ]
        if not valid_rows:
            return "- 时间推进线索不足，暂无法形成稳定时间轴摘要。"

        valid_rows.sort(key=lambda row: row["time"] or "9999-99-99 99:99:99")
        lines: List[str] = []
        for row in valid_rows[:6]:
            if not row["trigger"] and not row["propagation"]:
                continue
            parts: List[str] = []
            if row["trigger"]:
                parts.append(f"触发：{row['trigger']}")
            if row["propagation"]:
                parts.append(f"扩散：{row['propagation']}")
            time_part = row["time"] or "时间待核实"
            lines.append(f"- {time_part} | {'；'.join(parts)}")

        if not lines:
            return "- 时间推进线索不足，暂无法形成稳定时间轴摘要。"
        return "\n".join(lines)

    def _map_single_post(self, post_data: Dict[str, Any], chain: Any) -> Dict[str, Any]:
        post_content = post_data.get("content", "无内容")
        media_content = post_data.get("media_context", "无媒体链接")
        raw_comments = post_data.get("comments") or post_data.get("comment_items") or []
        comments_text = "\n".join(
            [
                f"- {text}"
                for text in self._select_comment_excerpts(raw_comments, limit=20)
            ]
        )
        invoke_args = {
            "post_content": post_content,
            "media_content": media_content,
            "comments_text": comments_text or "（暂无高赞评论样本）",
            "improvement_hint": "",
        }
        try:
            result = chain.invoke(invoke_args)
            return (
                result.model_dump() if hasattr(result, "model_dump") else dict(result)
            )
        except Exception as e:
            if not self._is_content_filter(e):
                raise
            logger.warning(" [Agent B] 单帖切片触发过滤，移除评论重试...")
            invoke_args["comments_text"] = "（评论样本因安全策略暂不可用）"
            result = chain.invoke(invoke_args)
            return (
                result.model_dump() if hasattr(result, "model_dump") else dict(result)
            )

    def analyze_event(
        self,
        event_name: str,
        posts_data: List[Dict[str, Any]],
        start_date: str = "",
        end_date: str = "",
        improvement_hint: str = "",
    ) -> Dict[str, Any]:
        logger.info(f" [Agent B] 启动重点深读: 《{event_name}》")
        selected_posts = (posts_data or [])[:12]
        if not selected_posts:
            return {
                "editorial_title": event_name,
                "one_line_verdict": "该事件数据不足，暂无法形成有效深读判断。",
                "event_overview": "数据不足",
                "public_opinions": [],
                "depth_analysis": "数据不足",
                "key_quotes": [],
            }

        web_context = self._build_web_context(event_name, start_date, end_date)

        structured_map_llm = self.map_llm.with_structured_output(PostOpinionSummary)
        map_chain = (
            ChatPromptTemplate.from_template(AGENT_B_MAP_TEMPLATE) | structured_map_llm
        )

        map_payloads: List[Dict[str, Any]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            future_to_index = {
                executor.submit(self._map_single_post, post, map_chain): (idx, post)
                for idx, post in enumerate(selected_posts)
            }
            for future in concurrent.futures.as_completed(future_to_index):
                idx, post = future_to_index[future]
                try:
                    summary = future.result()
                    map_payloads.append(
                        {
                            "index": idx,
                            "summary": summary,
                            "comment_excerpts": self._select_comment_excerpts(
                                post.get("comment_items") or post.get("comments") or [],
                                limit=8,
                            ),
                            "post_meta": {
                                "liked_count": post.get("liked_count", "0"),
                                "comments_count": post.get("comments_count", "0"),
                                "create_date_time": post.get("create_date_time", ""),
                            },
                        }
                    )
                except Exception as e:
                    logger.warning(f" [Agent B] 帖子切片失败，已跳过: {e}")

        map_payloads.sort(key=lambda item: item.get("index", 0))
        if not map_payloads:
            return {
                "editorial_title": event_name,
                "one_line_verdict": "该事件样本不足，暂无法形成可靠结论。",
                "event_overview": "数据不足",
                "public_opinions": [],
                "depth_analysis": "数据不足",
                "key_quotes": [],
            }

        mapped_text_list = []
        for idx, payload in enumerate(map_payloads, start=1):
            summary = payload.get("summary") or {}
            clusters = summary.get("opinion_clusters") or []
            cluster_desc = []
            for cluster in clusters:
                cluster_desc.append(
                    f"[{cluster.get('estimated_ratio', '')} - {cluster.get('emotion', '')}] {cluster.get('viewpoint', '')}"
                )
            excerpts = payload.get("comment_excerpts") or []
            quotes_text = "\n".join([f"   - {quote}" for quote in excerpts[:8]])
            meta = payload.get("post_meta") or {}
            mapped_text_list.append(
                (
                    f"【帖子{idx}】\n"
                    f"热度: 点赞{meta.get('liked_count','0')} / 评论{meta.get('comments_count','0')}\n"
                    f"时间: {meta.get('create_date_time','')}\n"
                    f"冲突分析: {summary.get('conflict_analysis', '无')}\n"
                    f"触发点: {summary.get('trigger_summary', '待补充')}\n"
                    f"传播方向: {summary.get('propagation_hint', '待补充')}\n"
                    f"观点分布: {'; '.join(cluster_desc) or '无明显观点分歧'}\n"
                    f"评论样本:\n{quotes_text or '   - （无）'}"
                )
            )
        mapped_summaries = "\n\n".join(mapped_text_list)
        timeline_digest = self._build_timeline_digest(map_payloads)

        structured_reduce_llm = self.reduce_llm.with_structured_output(
            EventAnalysisReport
        )
        reduce_chain = (
            ChatPromptTemplate.from_template(AGENT_B_REDUCE_TEMPLATE)
            | structured_reduce_llm
        )

        try:
            report_obj = reduce_chain.invoke(
                {
                    "event_name": event_name,
                    "report_period": (
                        f"{start_date or '开始时间未知'} 至 {end_date or '结束时间未知'}"
                        if (start_date or end_date)
                        else "本期"
                    ),
                    "web_search_context": web_context,
                    "mapped_summaries": mapped_summaries,
                    "timeline_digest": timeline_digest,
                    "improvement_hint": improvement_hint or "",
                }
            )
        except Exception as e:
            if self._is_timeout(e):
                logger.warning(
                    " [Agent B] 事件级成文超时，压缩上下文后使用主模型重试一次..."
                )
                fallback_reduce_chain = ChatPromptTemplate.from_template(
                    AGENT_B_REDUCE_TEMPLATE
                ) | self.reduce_llm.with_structured_output(EventAnalysisReport)
                report_obj = fallback_reduce_chain.invoke(
                    {
                        "event_name": event_name,
                        "report_period": (
                            f"{start_date or '开始时间未知'} 至 {end_date or '结束时间未知'}"
                            if (start_date or end_date)
                            else "本期"
                        ),
                        "web_search_context": web_context,
                        "mapped_summaries": mapped_summaries,
                        "timeline_digest": "\n".join(timeline_digest.splitlines()[:6]),
                        "improvement_hint": (improvement_hint or "")
                        + "（主模型超时，已压缩时间线后重试）",
                    }
                )
            elif not self._is_content_filter(e):
                raise
            else:
                logger.warning(" [Agent B] 事件级成文触发过滤，截断切片后重试...")
                report_obj = reduce_chain.invoke(
                    {
                        "event_name": event_name,
                        "report_period": (
                            f"{start_date or '开始时间未知'} 至 {end_date or '结束时间未知'}"
                            if (start_date or end_date)
                            else "本期"
                        ),
                        "web_search_context": web_context,
                        "mapped_summaries": "\n\n".join(mapped_text_list[:6]),
                        "timeline_digest": "\n".join(timeline_digest.splitlines()[:6]),
                        "improvement_hint": (improvement_hint or "")
                        + "（部分切片已截断）",
                    }
                )

        report = (
            report_obj.model_dump()
            if hasattr(report_obj, "model_dump")
            else dict(report_obj)
        )
        report.setdefault("editorial_title", event_name)
        report.setdefault("one_line_verdict", report.get("event_overview", ""))
        report.setdefault("key_quotes", [])
        return report


agent_opinions = AgentOpinions()

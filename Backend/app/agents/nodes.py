from typing import Dict, Any, List
from datetime import datetime, timedelta
import concurrent.futures
from dateutil.relativedelta import relativedelta
from app.core.logger import logger
from app.core.config import settings
from app.core.llm_factory import get_main_llm
from langchain_core.prompts import ChatPromptTemplate

from app.core.schemas import EventDuplicateCheck
from app.core.prompts import EVENT_DUPLICATE_CHECK_PROMPT

# 1. 引入同级目录下的 State
from app.agents.state import GraphState

# 2. 引入 ETL 处理器
from app.etl.event_manager import event_merger

# 3. 引入业务服务
from app.services.stats import agent_stats  # Agent A
from app.services.opinions import agent_opinions  # Agent B
from app.services.compliance import agent_c  # Agent C
from app.services.forecast import agent_forecast  # Agent D
from app.services.historical import agent_historical  # Agent Historical
from app.services.report import agent_report  # Agent E
from app.services.utils import get_web_context  # 工具函数

# 4. 引入数据库管理器
from app.db.mongo_manager import mongo_db

# 5. 引入分类服务
from app.services.category_classifier import category_classifier


def _is_duplicate_event_simple(event_name: str, selected_names: List[str]) -> bool:
    if not selected_names:
        return False
    event_name_clean = (event_name or "").strip().replace("#", "")
    for selected_name in selected_names:
        selected_clean = (selected_name or "").strip().replace("#", "")
        if event_name_clean == selected_clean:
            return True
        if event_name_clean in selected_clean or selected_clean in event_name_clean:
            if abs(len(event_name_clean) - len(selected_clean)) <= 5:
                return True
    return False


def _build_focus_events(
    all_events: List[Dict[str, Any]], target_count: int = 5
) -> List[Dict[str, Any]]:
    """前置圈定重点事件：按热度遍历，结合LLM去重，筛出最多 target_count 个有数据事件。"""
    if not all_events:
        return []

    dedup_llm = get_main_llm(
        temperature=0.1,
        request_timeout=60,
        max_retries=2,
    )
    structured_dedup_llm = dedup_llm.with_structured_output(EventDuplicateCheck)
    dedup_prompt = ChatPromptTemplate.from_template(EVENT_DUPLICATE_CHECK_PROMPT)

    selected: List[Dict[str, Any]] = []
    selected_names: List[str] = []

    for event in all_events:
        if len(selected) >= target_count:
            break

        event_name = event.get("event_name", "未知")
        posts_data = event.get("_fetched_posts", []) or []
        if not posts_data:
            continue

        is_duplicate = False
        if selected_names:
            try:
                chain = dedup_prompt | structured_dedup_llm
                result = chain.invoke(
                    {
                        "current_event": event_name,
                        "analyzed_events": ", ".join(selected_names),
                    }
                )
                is_duplicate = bool(result and result.is_same_event)
            except Exception as e:
                logger.warning(f"    [A-Select] LLM 去重失败，使用规则兜底: {e}")
                is_duplicate = _is_duplicate_event_simple(event_name, selected_names)

        if is_duplicate:
            logger.info(f"    [A-Select] 跳过重复重点事件: {event_name}")
            continue

        selected.append(event)
        selected_names.append(event_name)

    logger.info(
        f"    [A-Select] 圈定重点事件 {len(selected)} 个：{', '.join(selected_names) if selected_names else '无'}"
    )
    return selected


# =====================================================
# Node Classify: 热搜分类 (ETL 前置节点)
# =====================================================
def classify_node(state: GraphState) -> Dict[str, Any]:
    """
    对热搜词条进行分类标注
    如果用户选择"综合"类别，则跳过分类
    已有分类的词条不会被覆盖
    """
    category = state.get("category")
    start_str = state.get("start_date")
    end_str = state.get("end_date")

    # 如果是综合类别，跳过分类
    if not category or category == "综合":
        logger.info("\n [Node Classify] 综合类别，跳过分类...")
        return {"current_step": "Classify_Skipped"}

    logger.info(f"\n [Node Classify] 启动：热搜分类 (目标类别: {category})...")

    if not start_str or not end_str:
        now = datetime.now()
        end_str = now.strftime("%Y-%m-%d %H:%M:%S")
        start_str = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

    try:
        # 1. 获取原始热搜数据
        raw_items = mongo_db.get_raw_trend_items(start_str, end_str)
        if not raw_items:
            logger.warning(" [Node Classify] 无可用数据")
            return {"current_step": "Classify_Empty"}

        # 2. 提取所有唯一词条
        all_words = list(
            set(item.get("word") for item in raw_items if item.get("word"))
        )
        logger.info(f"    [Node Classify] 获取到 {len(all_words)} 个唯一热搜词条")

        # 3. 获取已有分类（避免覆盖）
        existing_categories = mongo_db.get_existing_categories(start_str, end_str)
        logger.info(f"    [Node Classify] 已有 {len(existing_categories)} 个词条有分类")

        # 4. 并行调用 LLM 分类（跳过已分类的）
        category_map = category_classifier.classify_parallel(
            words=all_words, max_workers=8, existing_categories=existing_categories
        )

        # 5. 回写到数据库
        mongo_db.update_hot_search_categories(category_map, start_str, end_str)

        logger.info(f" [Node Classify] 分类完成，共 {len(category_map)} 个词条")
        return {"current_step": "Classify_Done"}

    except Exception as e:
        logger.error(f" [Node Classify] 分类失败: {e}")
        return {"current_step": "Classify_Error"}


# =====================================================
# Node A: 数据准备与选题 (ETL + 热度统计 + 数据抓取)
# 职责: 完成分析前的全部前置工作，为 B/C 并行分析做好数据准备
# =====================================================
def agent_a_node(state: GraphState) -> Dict[str, Any]:
    FETCH_EVENT_COUNT = 20
    POSTS_PER_EVENT = 15
    DEEP_READ_COMMENTS_PER_POST = 20
    # 单贴审核候选评论总量控制在 40 条，降低长上下文带来的幻觉风险。
    AUDIT_HOT_COMMENTS_PER_POST = 20
    AUDIT_RECENT_COMMENTS_PER_POST = 20
    FETCH_WORKERS = 6
    FOCUS_EVENT_COUNT = 5

    category = state.get("category")
    category_label = (
        f"【{category}】" if category and category != "综合" else "【综合】"
    )
    start_str = state.get("start_date")
    end_str = state.get("end_date")

    logger.info(f"\n [Node A] 启动：{category_label} 数据准备与选题...")

    if not start_str or not end_str:
        now = datetime.now()
        end_str = now.strftime("%Y-%m-%d %H:%M:%S")
        start_str = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

    # -----------------------------------------------------------------
    # Phase 1: ETL — 数据清洗与归并
    # -----------------------------------------------------------------
    logger.info(f"    [A-Phase1] ETL 清洗与归并...")
    try:
        events = event_merger.run_merge_task(start_str, end_str, category=category)
        if not events:
            logger.warning("    [A-Phase1] ETL 无数据")
            return {"core_events": [], "current_step": "A_ETL_Empty"}

        clean_events = []
        for e in events:
            d = e.model_dump() if hasattr(e, "model_dump") else dict(e)
            if "_id" in d and d["_id"]:
                d["_id"] = str(d["_id"])
            if "id" in d and d["id"] and not isinstance(d["id"], str):
                d["id"] = str(d["id"])
            clean_events.append(d)

        logger.info(f"    [A-Phase1] ETL 完成：{len(clean_events)} 个事件")
    except Exception as e:
        logger.error(f"    [A-Phase1] ETL 失败: {e}")
        return {"core_events": [], "current_step": "A_ETL_Error"}

    # -----------------------------------------------------------------
    # Phase 2: 热度统计与选题 — 从 DB 读取 Top N
    # -----------------------------------------------------------------
    logger.info(f"    [A-Phase2] 热度排序选题...")
    result = agent_stats.run(top_n=50)
    core_events = result.get("core_events", [])

    if not core_events:
        logger.warning("    [A-Phase2] 无有效事件")
        return {"core_events": [], "current_step": "A_Stats_Empty"}

    logger.info(f"    [A-Phase2] 锁定 {len(core_events)} 个核心议题")

    # -----------------------------------------------------------------
    # Phase 3: 并行抓取帖子+评论 — 为 B/C 准备数据
    # -----------------------------------------------------------------
    target_events = core_events[:FETCH_EVENT_COUNT]
    logger.info(
        f"    [A-Phase3] 并行抓取候选池：前 {len(target_events)} 个事件的帖子+评论（仅用于后续圈定重点）..."
    )

    def fetch_event_posts(event):
        """抓取单个事件的帖子和评论数据"""
        try:
            keywords = event.get("related_keywords", [])
            raw_posts = mongo_db.get_posts_by_keywords(keywords, limit=POSTS_PER_EVENT)
            note_ids = [
                str(p.get("note_id") or "").strip()
                for p in (raw_posts or [])
                if str(p.get("note_id") or "").strip()
            ]
            deep_read_comment_map = mongo_db.get_grouped_comments_by_post_ids(
                note_ids=note_ids,
                limit_per_post=DEEP_READ_COMMENTS_PER_POST,
                sort_field="comment_like_count",
                descending=True,
            )
            audit_comment_map = mongo_db.get_comment_candidates_by_post_ids(
                note_ids=note_ids,
                hot_limit=AUDIT_HOT_COMMENTS_PER_POST,
                recent_limit=AUDIT_RECENT_COMMENTS_PER_POST,
            )
            valid_posts_data = []

            for p in raw_posts or []:
                note_id = str(p.get("note_id", ""))
                if not note_id:
                    continue

                deep_read_comments = deep_read_comment_map.get(note_id, [])
                audit_comments = audit_comment_map.get(note_id, [])

                comment_texts = []
                comment_items = []
                for c in deep_read_comments or []:
                    if not isinstance(c, dict):
                        continue
                    content = (c.get("content") or "").strip()
                    if not content or len(content) < 2:
                        continue
                    comment_texts.append(content)
                    comment_items.append(
                        {
                            "db_id": str(c.get("_id")) if c.get("_id") else "",
                            "comment_id": str(c.get("comment_id") or ""),
                            "content": content,
                            "create_date_time": c.get("create_date_time", ""),
                            "comment_like_count": c.get("comment_like_count", "0"),
                        }
                    )

                audit_comment_items = []
                for c in audit_comments or []:
                    if not isinstance(c, dict):
                        continue
                    content = (c.get("content") or "").strip()
                    if not content or len(content) < 2:
                        continue
                    audit_comment_items.append(
                        {
                            "db_id": str(c.get("_id")) if c.get("_id") else "",
                            "comment_id": str(c.get("comment_id") or ""),
                            "content": content,
                            "create_date_time": c.get("create_date_time", ""),
                            "comment_like_count": c.get("comment_like_count", "0"),
                        }
                    )

                image_list_raw = p.get("image_list", "") or ""
                image_urls = [u.strip() for u in image_list_raw.split(",") if u.strip()]
                video_url = p.get("video_url", "") or ""

                media_context = ""
                if image_urls:
                    media_context += f"【图片链接】{', '.join(image_urls)}\n"
                if video_url:
                    media_context += f"【视频链接】{video_url}"

                post_packet = {
                    "note_id": note_id,
                    "db_id": str(p.get("_id")) if p.get("_id") else "",
                    "content": p.get("full_content") or p.get("content", ""),
                    "source_keyword": p.get("source_keyword", ""),
                    "create_date_time": p.get("create_date_time", ""),
                    "liked_count": p.get("liked_count", "0"),
                    "comments_count": p.get("comments_count", "0"),
                    "comments": comment_texts,
                    "comment_items": [item for item in comment_items],
                    "audit_comment_items": audit_comment_items,
                    "media_context": media_context,
                    "audit_status": p.get("audit_status"),
                    "is_violation": p.get("is_violation"),
                    "violation_info": p.get("violation_info"),
                }
                valid_posts_data.append(post_packet)

            logger.info(
                f"    [A-Phase3] 候选池抓取完成: 《{event.get('event_name', '未知事件')}》"
                f" -> {len(valid_posts_data)} 贴 / {sum(len(p.get('audit_comment_items', [])) for p in valid_posts_data)} 条审核候选评论"
            )
            return valid_posts_data
        except Exception as e:
            logger.error(f"    [A-Phase3] 数据抓取失败: {e}")
            return []

    events_with_data = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
        future_to_event = {
            executor.submit(fetch_event_posts, evt): evt for evt in target_events
        }

        for future in concurrent.futures.as_completed(future_to_event):
            evt = future_to_event[future]
            try:
                posts_data = future.result()
                evt_copy = dict(evt)
                evt_copy["_fetched_posts"] = posts_data
                events_with_data.append(evt_copy)
            except Exception as e:
                logger.error(f"    [A-Phase3] 抓取失败: {e}")
                events_with_data.append(dict(evt))

    events_with_data.sort(key=lambda x: x.get("total_heat", 0), reverse=True)
    final_list = events_with_data + core_events[FETCH_EVENT_COUNT:]
    focus_events = _build_focus_events(events_with_data, target_count=FOCUS_EVENT_COUNT)

    logger.info(
        f" [Node A] 完成：ETL {len(clean_events)} 事件 → "
        f"选题 {len(core_events)} 个 → "
        f"抓取 {len(events_with_data)} 个事件数据 → "
        f"圈定重点 {len(focus_events)} 个"
    )
    return {
        "core_events": final_list,
        "focus_events": focus_events,
        "current_step": "A_Done",
    }


# =====================================================
# Node B-Analyze: 深度舆情分析 (从原 agent_b_node 拆出)
# 读取 core_events 中的 _fetched_posts 进行深度观点分析
# 只写 analyzed_events，不影响 core_events
# =====================================================
def agent_b_analyze_node(state: GraphState) -> Dict[str, Any]:
    # 读取质量门控反馋（重试时由 retry_counter 写入）
    feedback = (state.get("supervisor_feedback") or "").strip()
    retry_count = (state.get("retry_count") or {}).get("agent_b_analyze", 0)
    is_retry = retry_count > 0

    focus_events = state.get("focus_events", []) or []

    logger.info(
        f"\n [Node B-Analyze] 启动：深度分析 (复用前置圈定事件 {len(focus_events)} 个)"
        f"{f' [第{retry_count}次重试, 反馋: {feedback}]' if is_retry else ''}..."
    )

    all_events = focus_events or state.get("core_events", [])
    if not all_events:
        return {"analyzed_events": [], "current_step": "B_Skipped"}

    start_date = (state.get("start_date") or "").strip()
    end_date = (state.get("end_date") or "").strip()

    # -------------------------------------------------------------------------
    # 串行深度分析（复用前置圈定后的事件，不再二次去重）
    # -------------------------------------------------------------------------
    analyzed_results = []

    for evt in all_events:
        event_name = evt.get("event_name", "未知")
        posts_data = evt.get("_fetched_posts", [])

        if not posts_data:
            logger.info(f"    [B-Analyze] 跳过无数据事件: {event_name}")
            continue

        logger.info(
            f"    [B-Analyze] 深度分析: 《{event_name}》 ({len(analyzed_results)+1}/{len(all_events)})..."
        )

        try:
            analysis_input = [
                {
                    "content": d["content"],
                    "comments": d["comments"],
                    "comment_items": d.get("comment_items", []),
                    "media_context": d["media_context"],
                    "liked_count": d.get("liked_count", "0"),
                    "comments_count": d.get("comments_count", "0"),
                    "create_date_time": d.get("create_date_time", ""),
                }
                for d in posts_data[:12]
            ]

            analyzed_res = agent_opinions.analyze_event(
                event_name,
                analysis_input,
                start_date=start_date,
                end_date=end_date,
                improvement_hint=feedback if is_retry else "",
            )

            if analyzed_res:
                evt["opinion_report"] = analyzed_res
                analyzed_results.append(evt)
                logger.info(f"    [B-Analyze] 完成分析: 《{event_name}》")

        except Exception as e:
            logger.error(f" [B-Analyze] 分析失败 ({event_name}): {e}")

    logger.info(f" [B-Analyze] 完成：深度分析了 {len(analyzed_results)} 个事件。")

    return {
        "analyzed_events": analyzed_results,
        "current_step": "B_Done",
    }


# =====================================================
# Node C: 合规审查 (Batch 模式 - 完美版)
# =====================================================
def agent_c_node(state: GraphState) -> Dict[str, Any]:
    AUDIT_POSTS_PER_EVENT = 12
    AUDIT_WORKERS = 8
    should_force_audit = bool(state.get("force_audit_update", False)) or bool(
        settings.FORCE_AUDIT_UPDATE
    )
    logger.info("\n [Node C] 启动：逐条合规审查（单模型分层审核）...")

    focus_events = state.get("focus_events", []) or []
    target_events = focus_events or (state.get("core_events", []) or [])[:5]
    logger.info(
        f"    [Node C] 本轮实际审核事件数：{len(target_events)}（来源：{'focus_events' if focus_events else 'core_events[:5]' }）"
    )
    if target_events:
        logger.info(
            "    [Node C] 审核事件清单："
            + "；".join([f"《{e.get('event_name', '未知')}》" for e in target_events])
        )

    # -------------------------------------------------------------------------
    # 辅助函数：单个帖子的审核任务
    # -------------------------------------------------------------------------
    def process_single_audit_task(p, event_name):
        try:
            if not should_force_audit and p.get("audit_status") == "completed":
                if p.get("is_violation") is True:
                    existing_info = p.get("violation_info") or {}
                    repaired_info = agent_c.repair_existing_violation_info(
                        existing_info
                    )
                    repaired_is_violation = bool(
                        repaired_info.get("post_case")
                        or (repaired_info.get("comment_cases") or [])
                    )
                    return {
                        "post": p,
                        "event_name": event_name,
                        "is_violation": repaired_is_violation,
                        "violation_info": repaired_info,
                        "audit_comment_items": p.get("audit_comment_items", []),
                    }
                return None
            audit_payload = agent_c.audit_post_packet(p, event_name=event_name)
            return {
                "post": p,
                "event_name": event_name,
                "is_violation": audit_payload.get("is_violation", False),
                "violation_info": audit_payload.get("violation_info", {}),
                "audit_comment_items": p.get("audit_comment_items", []),
            }
        except Exception as e:
            logger.error(f" [Node C] 帖子审核失败 ({p.get('note_id')}): {e}")
            return None

    # -------------------------------------------------------------------------
    # 1. 准备任务列表
    # -------------------------------------------------------------------------
    tasks = []
    for event in target_events:
        event_name = event.get("event_name", "未知")
        posts = (event.get("_fetched_posts", []) or [])[:AUDIT_POSTS_PER_EVENT]
        if not posts:
            continue

        logger.info(
            f"   🔎 [Node C] 准备批量扫描事件: 《{event_name}》({len(posts)} 贴)..."
        )
        for p in posts:
            tasks.append((p, event_name))

    # -------------------------------------------------------------------------
    # 2. 并行执行 (ThreadPoolExecutor)
    # -------------------------------------------------------------------------
    audit_results = []
    post_audit_updates = []
    comment_audit_updates = []

    # mini 模型场景下恢复较高审核并发，保留轻量 timeout/fallback 机制兜底。
    with concurrent.futures.ThreadPoolExecutor(max_workers=AUDIT_WORKERS) as executor:
        futures = [
            executor.submit(process_single_audit_task, p, ename) for p, ename in tasks
        ]

        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if not res:
                continue

            p = res["post"]
            is_violation = res["is_violation"]
            violation_info = res["violation_info"]
            comment_items = res.get("audit_comment_items") or []
            comment_cases = violation_info.get("comment_cases") or []
            post_case = violation_info.get("post_case")

            post_audit_updates.append(
                {
                    "id": p["db_id"],
                    "is_violation": is_violation,
                    "violation_info": violation_info,
                }
            )

            violated_map = {}
            for v_item in comment_cases:
                try:
                    violated_map[int(v_item.get("index"))] = v_item
                except Exception:
                    continue

            for idx, c_item in enumerate(comment_items):
                c_db_id = c_item.get("db_id")
                if not c_db_id:
                    continue

                if idx in violated_map:
                    v_detail = violated_map[idx]
                    comment_audit_updates.append(
                        {
                            "id": c_db_id,
                            "is_violation": True,
                            "violation_info": v_detail,
                        }
                    )
                else:
                    comment_audit_updates.append(
                        {
                            "id": c_db_id,
                            "is_violation": False,
                            "violation_info": None,
                        }
                    )

            if is_violation:
                violated_comment_texts = []
                for case in comment_cases:
                    try:
                        index = int(case.get("index", -1))
                    except Exception:
                        index = -1
                    if 0 <= index < len(comment_items):
                        violated_comment_texts.append(
                            {
                                "index": index,
                                "content": comment_items[index].get("content", ""),
                                "category": case.get("category", ""),
                                "risk_level": case.get("risk_level", "Low"),
                            }
                        )
                audit_results.append(
                    {
                        "event_name": res["event_name"],
                        "note_id": p["note_id"],
                        "db_id": p["db_id"],
                        "is_violation": True,
                        "violation_info": violation_info,
                        "post_content": p.get("content", ""),
                        "post_case": post_case,
                        "comment_cases": comment_cases,
                        "violated_comment_originals": violated_comment_texts,
                    }
                )

    # 批量回写（帖子粒度）
    if post_audit_updates:
        try:
            mongo_db.update_post_audit(post_audit_updates)
            logger.info(
                f"    [Node C] 已更新 {len(post_audit_updates)} 条帖子的审核状态。"
            )
        except Exception as e:
            logger.error(f"    [Node C] 回写帖子审核结果失败: {e}")

    # 批量回写（评论粒度，仅违规项）
    if comment_audit_updates:
        try:
            mongo_db.update_comment_audit(comment_audit_updates)
            logger.info(
                f"    [Node C] 已更新 {len(comment_audit_updates)} 条评论的审核状态。"
            )
        except Exception as e:
            logger.error(f"    [Node C] 回写评论审核结果失败: {e}")

    return {"audit_results": audit_results, "current_step": "C_Done"}


# =====================================================
# Node Historical: 历史同期热门事件回顾
# =====================================================
def agent_historical_node(state: GraphState) -> Dict[str, Any]:
    """
    搜索去年同月每天的代表性热点事件
    """
    logger.info("\n [Node Historical] 启动：历史同期热门事件回顾...")

    end_date = state.get("end_date")
    if not end_date:
        logger.warning(" [Node Historical] 缺少结束日期，跳过历史回顾")
        return {"historical_events": None, "current_step": "Historical_Skipped"}

    try:
        result = agent_historical.analyze(end_date)
        return result
    except Exception as e:
        logger.error(f" [Node Historical] 执行失败: {e}")
        return {"historical_events": None, "current_step": "Historical_Error"}


# =====================================================
# Node D: 趋势预测 (ReAct Agent 模式)
# =====================================================
def agent_d_node(state: GraphState) -> Dict[str, Any]:
    feedback = (state.get("supervisor_feedback") or "").strip()
    retry_count = (state.get("retry_count") or {}).get("agent_d", 0)
    is_retry = retry_count > 0

    logger.info(
        f"\n [Node D] 启动：趋势研判 (Fixed Search + Structured Forecast)"
        f"{f' [第{retry_count}次重试, 反馈: {feedback}]' if is_retry else ''}..."
    )

    analyzed_events = state.get("analyzed_events", [])
    audit_results = state.get("audit_results", [])
    category = state.get("category") or "综合"
    forecast_range = state.get("forecast_range") or "1m"

    deep_read_briefs = []
    for evt in analyzed_events[:5]:
        report = evt.get("opinion_report") or {}
        deep_read_briefs.append(
            "\n".join(
                [
                    f"【事件】{evt.get('event_name', '未知事件')}",
                    f"【一句话判断】{report.get('one_line_verdict') or report.get('event_overview') or ''}",
                    f"【观点摘要】{'；'.join((report.get('public_opinions') or [])[:2])}",
                    f"【关键引述】{'；'.join((report.get('key_quotes') or [])[:2])}",
                ]
            ).strip()
        )
    opinion_str = (
        "\n\n".join([text for text in deep_read_briefs if text]) or "无重点深读摘要"
    )

    risk_priority = {"High": 3, "Medium": 2, "Low": 1}
    sorted_audits = sorted(
        audit_results,
        key=lambda item: risk_priority.get(
            ((item.get("violation_info") or {}).get("overall_risk_level") or "Low"), 1
        ),
        reverse=True,
    )
    audit_briefs = []
    for item in sorted_audits[:5]:
        info = item.get("violation_info") or {}
        top_categories = []
        for case in (info.get("comment_cases") or [])[:2]:
            category_name = case.get("category")
            if category_name and category_name not in top_categories:
                top_categories.append(category_name)
        representative_quotes = [
            case.get("quote", "")
            for case in (info.get("comment_cases") or [])[:2]
            if case.get("quote")
        ]
        audit_briefs.append(
            "\n".join(
                [
                    f"【事件】{item.get('event_name', '未知事件')}",
                    f"【风险等级】{info.get('overall_risk_level', 'Low')}",
                    f"【主要类别】{'、'.join(top_categories) or '未标注'}",
                    f"【代表性表达】{'；'.join(representative_quotes) or '无'}",
                ]
            ).strip()
        )
    audit_str = "\n\n".join(audit_briefs) or "无明显违规风险摘要"

    forecast = agent_forecast.run(
        current_opinion_analysis=opinion_str,
        audit_risks=audit_str,
        forecast_range=forecast_range,
        category=category,
        improvement_hint=feedback if is_retry else "",
    )

    logger.info(
        f"   [Node D] 固定流程预测完成，生成 {len(forecast.get('topics', []))} 个预测主题"
    )

    return {"trend_forecast": forecast, "current_step": "D_Done"}


# =====================================================
# Node E: 报告总编
# =====================================================


def agent_e_node(state: GraphState) -> Dict[str, Any]:
    logger.info("\n [Node E] 启动：生成 PDF...")
    output = agent_report.generate_full_report(state)

    # --- 持久化到长期记忆 (Mongo report_sessions) ---
    try:
        session_data = {
            "task_id": state.get("task_id"),
            "created_at": datetime.now(),
            "category": state.get("category", "综合"),
            "md_path": output.get("md_path", ""),
            "json_path": output.get("json_path", ""),
            "html_path": output.get("html_path", ""),
            "pdf_path": output.get("pdf_path", ""),
            "report_markdown": output.get("markdown", ""),
            "report_json": output.get("report_json", {}),
            "trend_forecast": state.get("trend_forecast", {}),
            "core_events": state.get("core_events", []),
            "analyzed_events": state.get("analyzed_events", []),
            "audit_results": state.get("audit_results", []),
            "violation_stats": output.get("violation_stats", {}),
        }
        mongo_db.save_report_session(session_data)
        logger.info(" [Memory] 报告已存入长期记忆 (report_sessions)")
    except Exception as e:
        logger.error(f" [Node E] 保存报告到长期记忆失败: {e}")

    logger.info(f" 报告文件: {output.get('md_path')}")
    return {
        "final_report": output.get("markdown", ""),
        "report_json": output.get("report_json", {}),
        "violation_stats": output.get("violation_stats", {}),
        "current_step": "E_Done",
    }

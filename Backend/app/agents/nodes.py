from typing import Dict, Any, List
from datetime import datetime, timedelta
import concurrent.futures
from dateutil.relativedelta import relativedelta
from langchain_openai import ChatOpenAI
from app.core.logger import logger
from app.core.config import settings

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
    COMMENTS_PER_POST = 200

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
    logger.info(f"    [A-Phase3] 并行抓取前 {len(target_events)} 个事件的帖子+评论...")

    def fetch_event_posts(event):
        """抓取单个事件的帖子和评论数据"""
        try:
            keywords = event.get("related_keywords", [])
            raw_posts = mongo_db.get_posts_by_keywords(keywords, limit=POSTS_PER_EVENT)
            valid_posts_data = []

            for p in raw_posts or []:
                note_id = str(p.get("note_id", ""))
                if not note_id:
                    continue

                comments = mongo_db.get_comments_by_post_ids(
                    [note_id], limit=COMMENTS_PER_POST
                )

                comment_texts = []
                comment_items = []
                for c in comments or []:
                    if not isinstance(c, dict):
                        continue
                    content = (c.get("content") or "").strip()
                    if not content:
                        continue
                    comment_texts.append(content)
                    comment_items.append({"db_id": c.get("_id"), "content": content})

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
                    "comments": comment_texts,
                    "comment_items": [
                        (
                            {**item, "db_id": str(item["db_id"])}
                            if item.get("db_id")
                            else item
                        )
                        for item in comment_items
                    ],
                    "media_context": media_context,
                    "audit_status": p.get("audit_status"),
                    "is_violation": p.get("is_violation"),
                    "violation_info": p.get("violation_info"),
                }
                valid_posts_data.append(post_packet)

            return valid_posts_data
        except Exception as e:
            logger.error(f"    [A-Phase3] 数据抓取失败: {e}")
            return []

    events_with_data = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
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

    logger.info(
        f" [Node A] 完成：ETL {len(clean_events)} 事件 → "
        f"选题 {len(core_events)} 个 → "
        f"抓取 {len(events_with_data)} 个事件数据"
    )
    return {"core_events": final_list, "current_step": "A_Done"}


# =====================================================
# Node B-Analyze: 深度舆情分析 (从原 agent_b_node 拆出)
# 读取 core_events 中的 _fetched_posts 进行深度观点分析
# 只写 analyzed_events，不影响 core_events
# =====================================================
def agent_b_analyze_node(state: GraphState) -> Dict[str, Any]:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from app.core.schemas import EventDuplicateCheck
    from app.core.prompts import EVENT_DUPLICATE_CHECK_PROMPT

    ANALYZE_EVENT_COUNT = 5

    # 读取质量门控反馋（重试时由 retry_counter 写入）
    feedback = (state.get("supervisor_feedback") or "").strip()
    retry_count = (state.get("retry_count") or {}).get("agent_b_analyze", 0)
    is_retry = retry_count > 0

    logger.info(
        f"\n [Node B-Analyze] 启动：深度分析 (必须 {ANALYZE_EVENT_COUNT} 个不同事件)"
        f"{f' [第{retry_count}次重试, 反馋: {feedback}]' if is_retry else ''}..."
    )

    all_events = state.get("core_events", [])
    if not all_events:
        return {"analyzed_events": [], "current_step": "B_Skipped"}

    start_date = (state.get("start_date") or "").strip()
    end_date = (state.get("end_date") or "").strip()

    # 初始化去重用的 LLM
    dedup_llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        openai_api_key=settings.ZHIPU_API_KEY,
        openai_api_base=settings.LLM_BASE_URL,
        temperature=0.1,
        request_timeout=60,
        max_retries=2,
    )
    structured_dedup_llm = dedup_llm.with_structured_output(EventDuplicateCheck)
    dedup_prompt = ChatPromptTemplate.from_template(EVENT_DUPLICATE_CHECK_PROMPT)

    # -------------------------------------------------------------------------
    # 辅助函数：LLM 去重
    # -------------------------------------------------------------------------
    def is_duplicate_event_llm(event_name: str, analyzed_names: list) -> bool:
        if not analyzed_names:
            return False
        try:
            chain = dedup_prompt | structured_dedup_llm
            result = chain.invoke(
                {
                    "current_event": event_name,
                    "analyzed_events": ", ".join(analyzed_names),
                }
            )
            if result and result.is_same_event:
                logger.info(
                    f"    [LLM去重] 跳过重复事件: {event_name}\n"
                    f"      理由: {result.reasoning}"
                )
                return True
            else:
                logger.info(f"    [LLM去重] {event_name} 是独立事件")
                return False
        except Exception as e:
            logger.warning(f"    [LLM去重] 调用失败，使用规则兜底: {e}")
            return is_duplicate_event_simple(event_name, analyzed_names)

    def is_duplicate_event_simple(event_name: str, analyzed_names: list) -> bool:
        if not analyzed_names:
            return False
        event_name_clean = event_name.strip().replace("#", "")
        for analyzed_name in analyzed_names:
            analyzed_clean = analyzed_name.strip().replace("#", "")
            if event_name_clean == analyzed_clean:
                return True
            if event_name_clean in analyzed_clean or analyzed_clean in event_name_clean:
                if abs(len(event_name_clean) - len(analyzed_clean)) <= 5:
                    return True
        return False

    # -------------------------------------------------------------------------
    # 串行深度分析 (LLM 去重 + 确保 5 个不同事件)
    # -------------------------------------------------------------------------
    analyzed_results = []
    analyzed_event_names = []

    for evt in all_events:
        if len(analyzed_results) >= ANALYZE_EVENT_COUNT:
            break

        event_name = evt.get("event_name", "未知")
        posts_data = evt.get("_fetched_posts", [])

        if not posts_data:
            logger.info(f"    [B-Analyze] 跳过无数据事件: {event_name}")
            continue

        if is_duplicate_event_llm(event_name, analyzed_event_names):
            continue

        logger.info(
            f"    [B-Analyze] 深度分析: 《{event_name}》 ({len(analyzed_results)+1}/{ANALYZE_EVENT_COUNT})..."
        )

        try:
            analysis_input = [
                {
                    "content": d["content"],
                    "comments": d["comments"],
                    "media_context": d["media_context"],
                }
                for d in posts_data
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
                analyzed_event_names.append(event_name)
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
    feedback = (state.get("supervisor_feedback") or "").strip()
    retry_count = (state.get("retry_count") or {}).get("agent_c", 0)
    if retry_count > 0:
        logger.info(
            f"\n [Node C] 启动：批量合规审查 [第{retry_count}次重试, 反馋: {feedback}]..."
        )
    else:
        logger.info("\n [Node C] 启动：批量合规审查 (复用 B 的全量 200 条数据)...")

    events_with_data = state.get("core_events", [])
    target_events = events_with_data[:10]

    # -------------------------------------------------------------------------
    # 辅助函数：单个帖子的审核任务
    # -------------------------------------------------------------------------
    def process_single_audit_task(p, event_name):
        try:
            #  【修改】处理已审核过的帖子
            if not settings.FORCE_AUDIT_UPDATE and p.get("audit_status") == "completed":
                # 如果数据库里已经是违规状态，我们需要把它加回本次报告中
                if p.get("is_violation") is True:
                    existing_info = p.get("violation_info") or {}
                    # 构造与新审核一致的返回结构
                    return {
                        "post": p,
                        "event_name": event_name,
                        "is_violation": True,
                        "violation_info": existing_info,
                        "comment_items": p.get("comment_items", []),
                        # 注意：这里需要确保 p 里有 comment_items，或者从 p['comments'] 还原
                        # 如果 existing_info 里有 violated_comments，报告生成器就能用
                        "violated_comments": existing_info.get("violated_comments", []),
                    }
                else:
                    # 既已完成又是安全的，则本次报告直接忽略
                    return None

            # 这里的 comments 是全量 200 条（同时保留评论 _id 用于回写）
            comment_items = p.get("comment_items") or []
            comments_text_block = "\n".join(
                [
                    f"{idx}. {(it.get('content','') or '')}"
                    for idx, it in enumerate(comment_items)
                ]
            )

            #  Batch + RAG：一次审查 + 标签检索法规 + 证据链
            rag_payload = agent_c.batch_audit_with_rag(
                post_content=p["content"],
                comments_text=comments_text_block,
                media_context=p["media_context"],
                note_id=p["note_id"],
            )

            batch_res = rag_payload.get("batch_result", {})
            matched_laws = rag_payload.get("matched_laws", [])
            evidence_report = rag_payload.get("evidence_report", {})

            # 简化模式审查结果直接视为安全
            # （无需特殊标记，正常流程处理）

            # 统一写回结构
            violation_info = {
                **(batch_res or {}),
                "matched_laws": matched_laws,
                "evidence_report": evidence_report,
            }

            is_violation = bool(
                batch_res.get("is_post_violated")
                or (batch_res.get("violated_comments") or [])
            )

            # 返回结果包
            return {
                "post": p,
                "event_name": event_name,
                "is_violation": is_violation,
                "violation_info": violation_info,
                "comment_items": comment_items,
                "violated_comments": batch_res.get("violated_comments") or [],
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
        posts = event.get("_fetched_posts", [])
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

    # 同样控制并发数，Agent C 比较耗费 token 和计算，建议适中 (例如 3)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
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
            comment_items = res["comment_items"]
            violated_comments = res["violated_comments"]

            # --- 组装写回数据 ---

            # A. 帖子回写
            post_audit_updates.append(
                {
                    "id": p["db_id"],
                    "is_violation": is_violation,
                    "violation_info": violation_info,
                }
            )

            # B. 评论回写
            violated_map = {}
            for v_item in violated_comments:
                try:
                    v_idx = int(v_item.get("index"))
                    violated_map[v_idx] = v_item
                except:
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
                            "violation_info": {
                                "index": idx,
                                "note_id": p.get("note_id"),
                                "item": v_detail,
                                "matched_laws": violation_info.get("matched_laws"),
                            },
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

            # C. 记录违规结果到 state
            if is_violation:
                #  重构：保存原始帖子内容和违规评论原文，用于报告展示
                violated_comment_texts = []
                for v_item in violated_comments:
                    try:
                        v_idx = int(v_item.get("index", -1))
                        if 0 <= v_idx < len(comment_items):
                            original_text = comment_items[v_idx].get("content", "")
                            violated_comment_texts.append(
                                {
                                    "index": v_idx,
                                    "content": original_text,
                                    "category": v_item.get("category", ""),
                                    "risk_level": v_item.get("risk_level", ""),
                                }
                            )
                    except:
                        continue

                audit_results.append(
                    {
                        "event_name": res["event_name"],
                        "note_id": p["note_id"],
                        "db_id": p["db_id"],
                        "is_violation": True,
                        "violation_info": violation_info,
                        #  新增：保存原始内容
                        "post_content": p.get("content", ""),  # 帖子原文
                        "violated_comment_originals": violated_comment_texts,  # 违规评论原文
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
    """
    Agent D: 趋势预测 (ReAct Agent 模式)

    Agent 自主构造搜索词，但 Prompt 约束时间与领域格式
    """
    from app.agents.factory import create_agent
    from app.services.utils import tavily_search
    from app.core.prompts import AGENT_D_REACT_SYSTEM_PROMPT
    from langchain_core.messages import HumanMessage
    import re
    import json as json_module

    feedback = (state.get("supervisor_feedback") or "").strip()
    retry_count = (state.get("retry_count") or {}).get("agent_d", 0)
    is_retry = retry_count > 0

    logger.info(
        f"\n [Node D] 启动：趋势研判 (ReAct Mode)"
        f"{f' [第{retry_count}次重试, 反馈: {feedback}]' if is_retry else ''}..."
    )

    # ----------------------------------------------------------------
    # 公共数据准备
    # ----------------------------------------------------------------
    analyzed_events = state.get("analyzed_events", [])
    audit_results = state.get("audit_results", [])
    category = state.get("category") or "综合"
    forecast_range = state.get("forecast_range") or "1m"

    # 准备当前舆情摘要
    b_texts = []
    for evt in analyzed_events:
        r = evt.get("opinion_report", {})
        if isinstance(r, dict):
            b_texts.append(
                f"【事件】{evt.get('event_name')}\n【概况】{r.get('event_overview')}"
            )
    opinion_str = "\n---\n".join(b_texts) if b_texts else "无数据"

    c_texts = []
    for r in audit_results:
        v = r.get("violation_info", {})
        c_texts.append(
            f"事件<{r.get('event_name','未知')}>: 风险[{v.get('overall_risk_level')}]"
        )
    audit_str = "\n".join(c_texts) if c_texts else "无高风险"

    # ----------------------------------------------------------------
    # 计算目标时间段描述
    # ----------------------------------------------------------------
    range_map = {
        "1w": ("未来一周", 7, "days"),
        "2w": ("未来两周", 14, "days"),
        "1m": ("未来一个月", 1, "months"),
        "2m": ("未来两个月", 2, "months"),
    }
    range_desc, delta_val, delta_unit = range_map.get(
        forecast_range, ("未来一个月", 1, "months")
    )
    now = datetime.now()

    if delta_unit == "days":
        target_date = now + timedelta(days=delta_val)
    else:
        target_date = now + relativedelta(months=delta_val)

    target_period = f"{now.strftime('%Y年%m月%d日')}至{target_date.strftime('%Y年%m月%d日')}（{range_desc}）"

    logger.info(f"   🌍 [Node D] 研判周期: {target_period}, 领域: {category}")

    # ----------------------------------------------------------------
    # 创建 ReAct Agent
    # ----------------------------------------------------------------
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        openai_api_key=settings.ZHIPU_API_KEY,
        openai_api_base=settings.LLM_BASE_URL,
        temperature=0.6,
        request_timeout=180,
        max_retries=3,
    )

    system_prompt = AGENT_D_REACT_SYSTEM_PROMPT.format(
        target_period=target_period,
        category=category,
        current_date=now.strftime("%Y年%m月%d日"),
    )

    agent = create_agent(
        model=llm,
        tools=[tavily_search],
        system_prompt=system_prompt,
    )

    # ----------------------------------------------------------------
    # 执行 Agent
    # ----------------------------------------------------------------
    user_message = f"""
请为【{category}领域】的【{target_period}】进行舆情风险预测。

当前舆论情绪摘要：
{opinion_str}

已核实违规风险：
{audit_str}

{'【改进建议】' + feedback if is_retry else ''}
"""

    try:
        # 添加 recursion_limit 防止无限循环
        result = agent.invoke(
            {"messages": [HumanMessage(content=user_message)]}, {"recursion_limit": 10}
        )

        # 从最后一条消息提取 JSON
        last_message = result["messages"][-1]
        forecast = _extract_json_from_agent_message(last_message.content)

        # 确保 target_period 有值
        if not forecast.get("target_period"):
            forecast["target_period"] = target_period

        logger.info(
            f"   [Node D] ReAct Agent 完成，生成 {len(forecast.get('topics', []))} 个预测主题"
        )

    except Exception as e:
        logger.error(f"[Node D] ReAct Agent 执行失败: {e}")
        # 降级：返回空预测结构，标记错误以便 quality_gate 判断
        forecast = {"target_period": target_period, "topics": [], "_error": str(e)}

    return {"trend_forecast": forecast, "current_step": "D_Done"}


def _extract_json_from_agent_message(content: str) -> dict:
    """从 Agent 输出中提取 JSON"""
    import re
    import json

    # 尝试匹配 JSON 代码块
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except:
            pass

    # 尝试匹配裸 JSON 对象
    obj_match = re.search(r"\{[\s\S]*\}", content)
    if obj_match:
        try:
            return json.loads(obj_match.group())
        except:
            pass

    # 兜底返回空结构
    return {"target_period": "", "topics": []}


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
            "report_markdown": output.get("markdown", ""),
            "trend_forecast": state.get("trend_forecast", {}),
            "core_events": state.get("core_events", []),
            "violation_stats": output.get("violation_stats", {}),
        }
        mongo_db.save_report_session(session_data)
        logger.info(" [Memory] 报告已存入长期记忆 (report_sessions)")
    except Exception as e:
        logger.error(f" [Node E] 保存报告到长期记忆失败: {e}")

    logger.info(f" 报告文件: {output.get('md_path')}")
    return {
        "final_report": output.get("markdown", ""),
        "violation_stats": output.get("violation_stats", {}),
        "current_step": "E_Done",
    }

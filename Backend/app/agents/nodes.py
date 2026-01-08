from typing import Dict, Any, List
from datetime import datetime, timedelta
import concurrent.futures
from dateutil.relativedelta import relativedelta
from app.core.logger import logger
from app.core.config import settings

# 1. 引入同级目录下的 State
from app.agents.state import GraphState

# 2. 引入 ETL 处理器
from app.etl.event_manager import event_merger

# 3. 引入 Agents
from app.agents.agent_stats import agent_stats  # Agent A
from app.agents.agent_opinions import agent_opinions  # Agent B
from app.agents.agent_compliance import agent_c  # Agent C
from app.agents.agent_forecast import agent_forecast  # Agent D
from app.agents.agent_report import agent_report  # Agent E
from app.agents.tools import get_web_context  # 工具函数

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
        logger.info("\n🏷️ [Node Classify] 综合类别，跳过分类...")
        return {"current_step": "Classify_Skipped"}

    logger.info(f"\n🏷️ [Node Classify] 启动：热搜分类 (目标类别: {category})...")

    if not start_str or not end_str:
        now = datetime.now()
        end_str = now.strftime("%Y-%m-%d %H:%M:%S")
        start_str = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

    try:
        # 1. 获取原始热搜数据
        raw_items = mongo_db.get_raw_trend_items(start_str, end_str)
        if not raw_items:
            logger.warning("⚠️ [Node Classify] 无可用数据")
            return {"current_step": "Classify_Empty"}

        # 2. 提取所有唯一词条
        all_words = list(
            set(item.get("word") for item in raw_items if item.get("word"))
        )
        logger.info(f"   📥 [Node Classify] 获取到 {len(all_words)} 个唯一热搜词条")

        # 3. 获取已有分类（避免覆盖）
        existing_categories = mongo_db.get_existing_categories(start_str, end_str)
        logger.info(
            f"   📌 [Node Classify] 已有 {len(existing_categories)} 个词条有分类"
        )

        # 4. 并行调用 LLM 分类（跳过已分类的）
        category_map = category_classifier.classify_parallel(
            words=all_words, max_workers=5, existing_categories=existing_categories
        )

        # 5. 回写到数据库
        mongo_db.update_hot_search_categories(category_map, start_str, end_str)

        logger.info(f"✅ [Node Classify] 分类完成，共 {len(category_map)} 个词条")
        return {"current_step": "Classify_Done"}

    except Exception as e:
        logger.error(f"❌ [Node Classify] 分类失败: {e}")
        return {"current_step": "Classify_Error"}


# =====================================================
# Node ETL: 数据清洗与归并
# =====================================================
def etl_node(state: GraphState) -> Dict[str, Any]:
    category = state.get("category")
    category_label = (
        f"【{category}】" if category and category != "综合" else "【综合】"
    )

    logger.info(f"\n🧹 [Node ETL] 启动：{category_label} 清洗与归并...")
    start_str = state.get("start_date")
    end_str = state.get("end_date")

    if not start_str or not end_str:
        now = datetime.now()
        end_str = now.strftime("%Y-%m-%d %H:%M:%S")
        start_str = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

    try:
        # 传递 category 参数到 ETL
        events = event_merger.run_merge_task(start_str, end_str, category=category)
        if not events:
            return {"core_events": [], "current_step": "ETL_Empty"}

        # 🔥 确保 etl_node 输出的数据是干净的 (无 ObjectId)
        clean_events = []
        for e in events:
            # 如果是 Pydantic 对象，dump 之；如果是 dict，直接用
            d = e.model_dump() if hasattr(e, "model_dump") else dict(e)
            if "_id" in d and d["_id"]:
                d["_id"] = str(d["_id"])
            if "id" in d and d["id"] and not isinstance(d["id"], str):
                d["id"] = str(d["id"])
            clean_events.append(d)

        return {"core_events": clean_events, "current_step": "ETL_Done"}
    except Exception as e:
        logger.error(f"   ❌ [Node ETL] Error: {e}")
        return {"core_events": [], "current_step": "ETL_Error"}


# =====================================================
# Node A: 统计分析
# =====================================================
def agent_a_node(state: GraphState) -> Dict[str, Any]:
    logger.info("\n📊 [Node A] 启动：统计热度...")
    result = agent_stats.run(top_n=50)
    return {"core_events": result.get("core_events", []), "current_step": "A_Done"}


# =====================================================
# Node B: 数据提取与深度分析 (B承担"搬运工")
# 🔥 重构：使用 LLM 判断事件是否重复，确保分析 5 个不同事件
# =====================================================
def agent_b_node(state: GraphState) -> Dict[str, Any]:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate
    from app.core.schemas import EventDuplicateCheck
    from app.core.prompts import EVENT_DUPLICATE_CHECK_PROMPT

    # --- 配置参数 ---
    FETCH_EVENT_COUNT = 20  # 🔥 前 20 个事件抓取数据 (供合规审查)
    ANALYZE_EVENT_COUNT = 5  # 🔥 必须分析 5 个不同事件
    POSTS_PER_EVENT = 15  # 每个事件取 Top 15 帖子
    COMMENTS_PER_POST = 200  # 每个帖子取 200 条评论

    logger.info(
        f"\n🧐 [Node B] 启动：数据提取 (Top {FETCH_EVENT_COUNT}) & 深度分析 (必须 {ANALYZE_EVENT_COUNT} 个不同事件)..."
    )

    all_events = state.get("core_events", [])
    if not all_events:
        return {"analyzed_events": [], "current_step": "B_Skipped"}

    # 仅处理前 N 个事件
    target_events = all_events[:FETCH_EVENT_COUNT]

    start_date = (state.get("start_date") or "").strip()
    end_date = (state.get("end_date") or "").strip()

    # -------------------------------------------------------------------------
    # 初始化去重用的 LLM
    # -------------------------------------------------------------------------
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
    # 辅助函数：获取单个事件的帖子数据
    # -------------------------------------------------------------------------
    def fetch_event_posts(event):
        """只负责抓取数据，不做分析"""
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
                }
                valid_posts_data.append(post_packet)

            return valid_posts_data
        except Exception as e:
            logger.error(f"❌ [Node B] 数据抓取失败: {e}")
            return []

    # -------------------------------------------------------------------------
    # 🔥 辅助函数：使用 LLM 检测事件是否与已分析事件重复
    # -------------------------------------------------------------------------
    def is_duplicate_event_llm(event_name: str, analyzed_names: list) -> bool:
        """
        使用 LLM 判断当前事件是否与已分析的事件是同一新闻事件
        如"小洛熙"与"小洛熙妈妈"、"马杜罗"与"委内瑞拉局势"
        """
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
                    f"   ⏭️ [LLM去重] 跳过重复事件: {event_name}\n"
                    f"      理由: {result.reasoning}"
                )
                return True
            else:
                logger.info(f"   ✅ [LLM去重] {event_name} 是独立事件")
                return False

        except Exception as e:
            logger.warning(f"   ⚠️ [LLM去重] 调用失败，使用规则兜底: {e}")
            # 兜底：简单规则判断
            return is_duplicate_event_simple(event_name, analyzed_names)

    def is_duplicate_event_simple(event_name: str, analyzed_names: list) -> bool:
        """简单规则兜底：字符串包含关系"""
        if not analyzed_names:
            return False

        event_name_clean = event_name.strip().replace("#", "")

        for analyzed_name in analyzed_names:
            analyzed_clean = analyzed_name.strip().replace("#", "")

            # 完全相同
            if event_name_clean == analyzed_clean:
                return True

            # 包含关系（且长度差不超过 5）
            if event_name_clean in analyzed_clean or analyzed_clean in event_name_clean:
                len_diff = abs(len(event_name_clean) - len(analyzed_clean))
                if len_diff <= 5:
                    return True

        return False

    # -------------------------------------------------------------------------
    # Step 1: 并行抓取所有事件的数据
    # -------------------------------------------------------------------------
    logger.info(f"   📥 [Node B] 并行抓取 {len(target_events)} 个事件的数据...")

    events_with_data = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
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
                logger.error(f"❌ [Node B] 抓取失败: {e}")
                events_with_data.append(dict(evt))

    # 按原始热度顺序排序
    events_with_data.sort(key=lambda x: x.get("total_heat", 0), reverse=True)

    # -------------------------------------------------------------------------
    # Step 2: 🔥 串行深度分析 (使用 LLM 去重，确保分析 5 个不同事件)
    # -------------------------------------------------------------------------
    logger.info(
        f"   🔍 [Node B] 开始深度分析 (必须 {ANALYZE_EVENT_COUNT} 个不同事件，使用 LLM 去重)..."
    )

    analyzed_results = []
    analyzed_event_names = []  # 记录已分析的事件名，用于去重

    for evt in events_with_data:
        # 达到分析数量上限则停止
        if len(analyzed_results) >= ANALYZE_EVENT_COUNT:
            break

        event_name = evt.get("event_name", "未知")
        posts_data = evt.get("_fetched_posts", [])

        # 检查是否有数据
        if not posts_data:
            logger.info(f"   ⏭️ [Node B] 跳过无数据事件: {event_name}")
            continue

        # 🔥 使用 LLM 检查是否与已分析事件重复
        if is_duplicate_event_llm(event_name, analyzed_event_names):
            continue

        # 执行深度分析
        logger.info(
            f"   🔍 [Node B] 深度分析: 《{event_name}》 ({len(analyzed_results)+1}/{ANALYZE_EVENT_COUNT})..."
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
            )

            if analyzed_res:
                evt["opinion_report"] = analyzed_res
                analyzed_results.append(evt)
                analyzed_event_names.append(event_name)
                logger.info(f"   ✅ [Node B] 完成分析: 《{event_name}》")

        except Exception as e:
            logger.error(f"❌ [Node B] 分析失败 ({event_name}): {e}")

    # 合并剩余未处理的事件
    final_list = events_with_data + all_events[FETCH_EVENT_COUNT:]

    logger.info(
        f"✅ [Node B] 完成。处理了 {len(events_with_data)} 个事件，深度分析 {len(analyzed_results)} 个。"
    )

    return {
        "core_events": final_list,  # 更新带数据和报告的完整列表
        "analyzed_events": analyzed_results,  # 只含被深度分析的
        "current_step": "B_Done",
    }


# =====================================================
# Node C: 合规审查 (Batch 模式 - 完美版)
# =====================================================
def agent_c_node(state: GraphState) -> Dict[str, Any]:
    logger.info("\n👮 [Node C] 启动：批量合规审查 (复用 B 的全量 200 条数据)...")

    events_with_data = state.get("core_events", [])
    target_events = events_with_data[:10]

    # -------------------------------------------------------------------------
    # 辅助函数：单个帖子的审核任务
    # -------------------------------------------------------------------------
    def process_single_audit_task(p, event_name):
        try:
            # 🔥 如果配置了强制重新审核，或者状态不是 completed，才进行审核
            if not settings.FORCE_AUDIT_UPDATE and p.get("audit_status") == "completed":
                return None

            # 这里的 comments 是全量 200 条（同时保留评论 _id 用于回写）
            comment_items = p.get("comment_items") or []
            comments_text_block = "\n".join(
                [
                    f"{idx}. {(it.get('content','') or '')}"
                    for idx, it in enumerate(comment_items)
                ]
            )

            # ✅ Batch + RAG：一次审查 + 标签检索法规 + 证据链
            rag_payload = agent_c.batch_audit_with_rag(
                post_content=p["content"],
                comments_text=comments_text_block,
                media_context=p["media_context"],
                note_id=p["note_id"],
            )

            batch_res = rag_payload.get("batch_result", {})
            matched_laws = rag_payload.get("matched_laws", [])
            evidence_report = rag_payload.get("evidence_report", {})

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
            logger.error(f"❌ [Node C] 帖子审核失败 ({p.get('note_id')}): {e}")
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

    # 同样控制并发数，Agent C 比较耗费 token 和计算，建议适中 (例如 5-8)
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
                # 🔥 重构：保存原始帖子内容和违规评论原文，用于报告展示
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
                        # 🔥 新增：保存原始内容
                        "post_content": p.get("content", ""),  # 帖子原文
                        "violated_comment_originals": violated_comment_texts,  # 违规评论原文
                    }
                )

    # 批量回写（帖子粒度）
    if post_audit_updates:
        try:
            mongo_db.update_post_audit(post_audit_updates)
            logger.info(
                f"   ✅ [Node C] 已更新 {len(post_audit_updates)} 条帖子的审核状态。"
            )
        except Exception as e:
            logger.error(f"   ⚠️ [Node C] 回写帖子审核结果失败: {e}")

    # 批量回写（评论粒度，仅违规项）
    if comment_audit_updates:
        try:
            mongo_db.update_comment_audit(comment_audit_updates)
            logger.info(
                f"   ✅ [Node C] 已更新 {len(comment_audit_updates)} 条评论的审核状态。"
            )
        except Exception as e:
            logger.error(f"   ⚠️ [Node C] 回写评论审核结果失败: {e}")

    return {"audit_results": audit_results, "current_step": "C_Done"}


# =====================================================
# Node D: 趋势预测
# =====================================================
def agent_d_node(state: GraphState) -> Dict[str, Any]:
    logger.info("\n🔮 [Node D] 启动：趋势研判...")
    analyzed_events = state.get("analyzed_events", [])
    audit_results = state.get("audit_results", [])

    b_texts = []
    for evt in analyzed_events:
        r = evt.get("opinion_report", {})
        if isinstance(r, dict):
            b_texts.append(
                f"【事件】{evt.get('event_name')}\n【概况】{r.get('event_overview')}\n【观点】{r.get('public_opinions')}"
            )
    opinion_str = "\n---\n".join(b_texts) if b_texts else "无数据"

    c_texts = []
    for r in audit_results:
        v = r.get("violation_info", {})

        # 🔥 升级：提取违规标签摘要，辅助趋势研判
        cats = set()
        for item in v.get("violated_comments") or []:
            if item.get("category"):
                cats.add(item.get("category"))

        cat_info = f" | 涉及: {', '.join(cats)}" if cats else ""

        c_texts.append(
            f"事件<{r.get('event_name','未知')}>: 风险[{v.get('overall_risk_level')}]{cat_info}"
        )
    audit_str = "\n".join(c_texts) if c_texts else "无高风险"

    # --- 🔥 新增：Node 层显式执行搜索逻辑 (符合架构设计) ---
    # 0. 获取用户指定的预测范围 (从 state 读取)
    forecast_range = state.get("forecast_range") or "1m"

    # 解析预测范围，计算目标时间
    range_map = {
        "1w": (7, "days"),
        "2w": (14, "days"),
        "1m": (1, "months"),
        "2m": (2, "months"),
    }
    delta_val, delta_unit = range_map.get(forecast_range, (1, "months"))

    # 1. 锁定时间坐标
    now = datetime.now()
    if delta_unit == "days":
        target_date = now + timedelta(days=delta_val)
    else:
        target_date = now + relativedelta(months=delta_val)

    target_year = target_date.year
    target_month = target_date.month

    logger.info(
        f"   🌍 [Node D] 正在调取全网情报库 (目标: {target_year}年{target_month}月, 范围: {forecast_range})..."
    )

    # 2. 搜历史铁律
    query_history = (
        f"历年{target_month}月 中国网络舆情 高发领域 复盘 "
        f"历年{target_month}月 社会矛盾 典型舆情案例"
    )
    # 3. 搜未来前瞻
    query_future = (
        f"{target_year}年{target_month}月 中国 社会舆情风险点 专家预测 "
        f"{target_year}年{target_month}月 舆情研判 重点关注领域 "
        f"{target_year}年{target_month}月 政策施行 经济形势 民生痛点前瞻"
    )

    history_context = get_web_context(query_history)
    future_context = get_web_context(query_future)

    # 4. 调用 Agent D 进行研判 (传递 forecast_range)
    forecast = agent_forecast.run(
        current_opinion_analysis=opinion_str,
        audit_risks=audit_str,
        history_context=history_context,
        future_context=future_context,
        forecast_range=forecast_range,
    )
    return {"trend_forecast": forecast, "current_step": "D_Done"}


# =====================================================
# Node E: 报告总编
# =====================================================
from datetime import datetime


def agent_e_node(state: GraphState) -> Dict[str, Any]:
    logger.info("\n📝 [Node E] 启动：生成 PDF...")
    output = agent_report.generate_full_report(state)

    # --- 持久化到长期记忆 (Mongo report_sessions) ---
    try:
        session_data = {
            "task_id": state.get("task_id"),
            "created_at": datetime.now(),
            "pdf_path": output.get("pdf_path", ""),
            "report_markdown": output.get("markdown", ""),
            "trend_forecast": state.get("trend_forecast", {}),
            "core_events": state.get("core_events", [])[:20],  # 仅保留 Top20 简要元数据
        }
        mongo_db.save_report_session(session_data)
        logger.info("💾 [Memory] 报告已存入长期记忆 (report_sessions)")
    except Exception as e:
        logger.error(f"⚠️ [Node E] 保存报告到长期记忆失败: {e}")

    logger.info(f"📄 PDF: {output.get('pdf_path')}")
    return {"final_report": output.get("markdown", ""), "current_step": "E_Done"}

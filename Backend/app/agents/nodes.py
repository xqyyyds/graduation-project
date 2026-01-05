from typing import Dict, Any, List
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from app.core.logger import logger

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


# =====================================================
# Node ETL: 数据清洗与归并
# =====================================================
def etl_node(state: GraphState) -> Dict[str, Any]:
    logger.info("\n🧹 [Node ETL] 启动：清洗与归并...")
    start_str = state.get("start_date")
    end_str = state.get("end_date")

    if not start_str or not end_str:
        now = datetime.now()
        end_str = now.strftime("%Y-%m-%d %H:%M:%S")
        start_str = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

    try:
        events = event_merger.run_merge_task(start_str, end_str)
        if not events:
            return {"core_events": [], "current_step": "ETL_Empty"}
        return {"core_events": events, "current_step": "ETL_Done"}
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
# =====================================================
def agent_b_node(state: GraphState) -> Dict[str, Any]:
    # --- 配置参数 ---
    FETCH_EVENT_COUNT = 10  # 为前 10 个事件抓取数据 (供合规审查)
    ANALYZE_EVENT_COUNT = 5  # 为前 5 个事件做深度观点分析 (节省 Token)
    POSTS_PER_EVENT = 15  # 每个事件取 Top 15 帖子
    COMMENTS_PER_POST = 200  # 每个帖子取 200 条评论

    logger.info(
        f"\n🧐 [Node B] 启动：数据提取 (Top {FETCH_EVENT_COUNT}) & 深度分析 (Top {ANALYZE_EVENT_COUNT})..."
    )

    all_events = state.get("core_events", [])
    if not all_events:
        return {"analyzed_events": [], "current_step": "B_Skipped"}

    # 仅处理前 N 个事件，后面的直接保留原样
    target_events = all_events[:FETCH_EVENT_COUNT]
    remaining_events = all_events[FETCH_EVENT_COUNT:]

    analyzed_results = []  # 存放有深度报告的事件
    processed_events = []  # 存放处理过数据的所有事件 (含 Top 10)

    for i, event in enumerate(target_events):
        event_name = event.get("event_name", "未知")
        keywords = event.get("related_keywords", [])

        # 1. 查帖子 (Top N)
        raw_posts = mongo_db.get_posts_by_keywords(keywords, limit=POSTS_PER_EVENT)

        valid_posts_data = []
        for p in raw_posts or []:
            note_id = str(p.get("note_id", ""))
            if not note_id:
                continue

            # 获取全量评论
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

            # 提取媒体链接
            image_list_raw = p.get("image_list", "") or ""
            image_urls = [u.strip() for u in image_list_raw.split(",") if u.strip()]
            video_url = p.get("video_url", "") or ""

            # 组装媒体上下文
            media_context = ""
            if image_urls:
                media_context += f"【图片链接】{', '.join(image_urls)}\n"
            if video_url:
                media_context += f"【视频链接】{video_url}"

            post_packet = {
                "note_id": note_id,
                "db_id": p.get("_id"),
                "content": p.get("full_content") or p.get("content", ""),
                "comments": comment_texts,
                "comment_items": comment_items,
                "media_context": media_context,
                "audit_status": p.get("audit_status"),
            }
            valid_posts_data.append(post_packet)

        # 2. 挂载数据 (基于原事件对象创建一个新字典)
        current_event = dict(event)
        current_event["_fetched_posts"] = valid_posts_data

        # 3. Agent B 分析 (仅 Top M)
        if i < ANALYZE_EVENT_COUNT and valid_posts_data:
            logger.info(f"   🔍 [Node B] 深度分析: 《{event_name}》...")

            analysis_input = [
                {
                    "content": d["content"],
                    "comments": d["comments"],
                    "media_context": d["media_context"],
                }
                for d in valid_posts_data
            ]

            report = agent_opinions.analyze_event(event_name, analysis_input)
            # 将报告也挂载到同一个对象上，保证数据不分裂
            current_event["opinion_report"] = report
            analyzed_results.append(current_event)

        processed_events.append(current_event)

    # 合并列表：[处理过的 Top 10] + [未处理的剩余事件]
    final_core_events = processed_events + remaining_events

    return {
        "analyzed_events": analyzed_results,  # 仅包含 Top 5 (带报告)
        "core_events": final_core_events,  # 包含全量 (Top 10 带数据, Top 5 带报告)
        "current_step": "B_Done",
    }


# =====================================================
# Node C: 合规审查 (Batch 模式 - 完美版)
# =====================================================
def agent_c_node(state: GraphState) -> Dict[str, Any]:
    logger.info("\n👮 [Node C] 启动：批量合规审查 (复用 B 的全量 200 条数据)...")

    events_with_data = state.get("core_events", [])
    target_events = events_with_data[:10]
    audit_results = []
    post_audit_updates = []
    comment_audit_updates = []

    for event in target_events:
        event_name = event.get("event_name", "未知")
        posts = event.get("_fetched_posts", [])
        if not posts:
            continue

        logger.info(f"   🔎 [Node C] 批量扫描: 《{event_name}》...")

        for p in posts:
            if p.get("audit_status") == "completed":
                continue

            # 这里的 comments 是全量 200 条（同时保留评论 _id 用于回写）
            comment_items = p.get("comment_items") or []
            # 🔥 修正：移除 120 字符截断，确保 Agent C 看到完整内容
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

            # 统一写回结构（全部塞进 violation_info，便于 Mongo 侧一次性落库）
            violation_info = {
                **(batch_res or {}),
                "matched_laws": matched_laws,
                "evidence_report": evidence_report,
            }

            is_violation = bool(
                batch_res.get("is_post_violated")
                or (batch_res.get("violated_comments") or [])
            )

            # 1. 帖子粒度回写：无论是否违规，都标记为 completed
            try:
                post_audit_updates.append(
                    {
                        "id": p["db_id"],
                        "is_violation": is_violation,
                        "violation_info": violation_info,
                    }
                )
            except Exception:
                pass

            # 2. 评论粒度回写：🔥 修正逻辑，违规和不违规的都要更新状态
            # 先构建一个 {index: violation_detail} 的映射表，方便快速查找
            violated_map = {}
            raw_violated_list = batch_res.get("violated_comments") or []
            for v_item in raw_violated_list:
                try:
                    v_idx = int(v_item.get("index"))
                    violated_map[v_idx] = v_item
                except:
                    continue

            # 遍历该帖子下所有评论，逐一判断
            for idx, c_item in enumerate(comment_items):
                c_db_id = c_item.get("db_id")
                if not c_db_id:
                    continue

                if idx in violated_map:
                    # 命中违规
                    v_detail = violated_map[idx]
                    comment_audit_updates.append(
                        {
                            "id": c_db_id,
                            "is_violation": True,
                            "violation_info": {
                                "index": idx,
                                "note_id": p.get("note_id"),
                                "item": v_detail,
                                "matched_laws": matched_laws,  # 附带上下文
                            },
                        }
                    )
                else:
                    # 未命中 -> 标记为合规 (is_violation=False)
                    comment_audit_updates.append(
                        {
                            "id": c_db_id,
                            "is_violation": False,
                            "violation_info": None,
                        }
                    )

            if is_violation:
                audit_results.append(
                    {
                        "event_name": event_name,
                        "note_id": p["note_id"],
                        "db_id": p["db_id"],
                        "is_violation": True,
                        "violation_info": violation_info,
                    }
                )

    # 批量回写（帖子粒度）
    if post_audit_updates:
        try:
            mongo_db.update_post_audit(post_audit_updates)
        except Exception as e:
            logger.error(f"   ⚠️ [Node C] 回写帖子审核结果失败: {e}")

    # 批量回写（评论粒度，仅违规项）
    if comment_audit_updates:
        try:
            mongo_db.update_comment_audit(comment_audit_updates)
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
    # 1. 锁定时间坐标 (下个月)
    now = datetime.now()
    next_month_date = now + relativedelta(months=1)
    target_year = next_month_date.year
    target_month = next_month_date.month

    logger.info(
        f"   🌍 [Node D] 正在调取全网情报库 (目标: {target_year}年{target_month}月)..."
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

    # 4. 调用 Agent D 进行研判
    forecast = agent_forecast.run(
        current_opinion_analysis=opinion_str,
        audit_risks=audit_str,
        history_context=history_context,
        future_context=future_context,
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

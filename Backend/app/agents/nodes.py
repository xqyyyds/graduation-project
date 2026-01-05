from typing import Dict, Any, List
from datetime import datetime, timedelta

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

# 4. 引入数据库管理器
from app.db.mongo_manager import mongo_db


# =====================================================
# Node ETL: 数据清洗与归并
# =====================================================
def etl_node(state: GraphState) -> Dict[str, Any]:
    print("\n🧹 [Node ETL] 启动：清洗与归并...")
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
        print(f"   ❌ [Node ETL] Error: {e}")
        return {"core_events": [], "current_step": "ETL_Error"}


# =====================================================
# Node A: 统计分析
# =====================================================
def agent_a_node(state: GraphState) -> Dict[str, Any]:
    print("\n📊 [Node A] 启动：统计热度...")
    result = agent_stats.run(top_n=50)
    return {"core_events": result.get("core_events", []), "current_step": "A_Done"}


# =====================================================
# Node B: 数据提取与深度分析 (B承担"搬运工")
# =====================================================
def agent_b_node(state: GraphState) -> Dict[str, Any]:
    print("\n🧐 [Node B] 启动：数据提取 (Top 10) & 深度分析 (Top 5)...")

    all_events = state.get("core_events", [])
    if not all_events:
        return {"analyzed_events": [], "current_step": "B_Skipped"}

    target_events_for_fetch = all_events[:10]
    analyzed_results = []
    updated_core_events = []

    for i, event in enumerate(target_events_for_fetch):
        event_name = event.get("event_name", "未知")
        keywords = event.get("related_keywords", [])

        # 1. 查帖子 (Top 15)
        raw_posts = mongo_db.get_posts_by_keywords(keywords, limit=15)

        valid_posts_data = []
        for p in raw_posts or []:
            note_id = str(p.get("note_id", ""))
            if not note_id:
                continue

            # 🔥 修改点 1: 恢复为 200 条评论，满足你的全量需求！
            comments = mongo_db.get_comments_by_post_ids([note_id], limit=200)

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

            # 🔥 修改点 2: 组装媒体上下文，供 B 和 C 使用
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
                "media_context": media_context,  # URL 放入包中
                "audit_status": p.get("audit_status"),
            }
            valid_posts_data.append(post_packet)

        # 2. 挂载数据 (给 C 用)
        event_with_data = dict(event)
        event_with_data["_fetched_posts"] = valid_posts_data
        updated_core_events.append(event_with_data)

        # 3. Agent B 分析 (Top 5)
        if i < 5 and valid_posts_data:
            print(f"   🔍 [Node B] 深度分析: 《{event_name}》 (含媒体上下文)")

            # 准备给 Agent B 的输入，显式包含 media_context
            analysis_input = [
                {
                    "content": d["content"],
                    "comments": d["comments"],
                    "media_context": d["media_context"],  # 🔥 传入 URL 上下文
                }
                for d in valid_posts_data
            ]

            report = agent_opinions.analyze_event(event_name, analysis_input)

            event_with_report = dict(event)
            event_with_report["opinion_report"] = report
            analyzed_results.append(event_with_report)

    updated_core_events.extend(all_events[10:])

    return {
        "analyzed_events": analyzed_results,
        "core_events": updated_core_events,
        "current_step": "B_Done",
    }


# =====================================================
# Node C: 合规审查 (Batch 模式 - 完美版)
# =====================================================
def agent_c_node(state: GraphState) -> Dict[str, Any]:
    print("\n👮 [Node C] 启动：批量合规审查 (复用 B 的全量 200 条数据)...")

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

        print(f"   🔎 [Node C] 批量扫描: 《{event_name}》...")

        for p in posts:
            if p.get("audit_status") == "completed":
                continue

            # 这里的 comments 是全量 200 条（同时保留评论 _id 用于回写）
            comment_items = p.get("comment_items") or []
            comments_text_block = "\n".join(
                [
                    f"{idx}. {(it.get('content','')[:120])}"
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

            # 无论是否违规，都写回 completed，保证断点续传与幂等
            try:
                post_audit_updates.append(
                    {
                        "id": p["db_id"],
                        "is_violation": is_violation,
                        "violation_info": violation_info,
                    }
                )
            except Exception:
                # 回写失败不应阻断主流程
                pass

            # 评论粒度回写：只回写“违规评论”
            violated_items = batch_res.get("violated_comments") or []
            for it in violated_items:
                try:
                    idx = int((it or {}).get("index"))
                except Exception:
                    continue
                if idx < 0:
                    continue
                if idx >= len(comment_items):
                    continue

                comment_db_id = comment_items[idx].get("db_id")
                if not comment_db_id:
                    continue

                comment_audit_updates.append(
                    {
                        "id": comment_db_id,
                        "is_violation": True,
                        "violation_info": {
                            "index": idx,
                            "note_id": p.get("note_id"),
                            "item": it,
                            "matched_laws": matched_laws,
                        },
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
            print(f"   ⚠️ [Node C] 回写帖子审核结果失败: {e}")

    # 批量回写（评论粒度，仅违规项）
    if comment_audit_updates:
        try:
            mongo_db.update_comment_audit(comment_audit_updates)
        except Exception as e:
            print(f"   ⚠️ [Node C] 回写评论审核结果失败: {e}")

    return {"audit_results": audit_results, "current_step": "C_Done"}


# =====================================================
# Node D: 趋势预测
# =====================================================
def agent_d_node(state: GraphState) -> Dict[str, Any]:
    print("\n🔮 [Node D] 启动：趋势研判...")
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
        c_texts.append(
            f"事件<{r.get('event_name','未知')}>: 风险[{v.get('overall_risk_level')}]"
        )
    audit_str = "\n".join(c_texts) if c_texts else "无高风险"

    forecast = agent_forecast.run(
        current_opinion_analysis=opinion_str, audit_risks=audit_str
    )
    return {"trend_forecast": forecast, "current_step": "D_Done"}


# =====================================================
# Node E: 报告总编
# =====================================================
from datetime import datetime


def agent_e_node(state: GraphState) -> Dict[str, Any]:
    print("\n📝 [Node E] 启动：生成 PDF...")
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
        print("💾 [Memory] 报告已存入长期记忆 (report_sessions)")
    except Exception as e:
        print(f"⚠️ [Node E] 保存报告到长期记忆失败: {e}")

    print(f"📄 PDF: {output.get('pdf_path')}")
    return {"final_report": output.get("markdown", ""), "current_step": "E_Done"}

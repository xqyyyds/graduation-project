from typing import Dict, Any, List
from app.db.mongo_manager import mongo_db


class AgentStats:
    """
    Agent A: 统计分析师
    职责：从数据库读取 ETL 处理好的核心事件，按热度排序并筛选 Top N。
    它是“选题人”，决定后续 Agent 分析哪些话题。
    """

    def run(self, top_n: int = 50) -> Dict[str, Any]:
        """
        执行统计任务
        :param top_n: 筛选前多少个热点，默认 50
        """
        print(f"📊 [Agent A] 正在获取 Top {top_n} 热点事件...")

        # 1. 调用 MongoDB 获取数据
        # 注意：你的 mongodb_manager.get_top_events 定义里有个 unused 的 'events' 参数
        # 我们这里传个空列表 [] 占位即可，实际它直接查的是 self.db['events']
        raw_events = mongo_db.get_top_events(events=[], top_n=top_n)

        if not raw_events:
            print(
                "⚠️ [Agent A] 数据库 'events' 表为空，请检查是否已运行 ETL (event_merger.py)。"
            )
            return {"core_events": [], "error": "数据库中无已清洗的事件数据"}

        # 2. 数据清洗与格式标准化
        # 这一步很重要！ETL 存的是 'event_name'，但 State 里通用叫 'topic'
        # 我们在这里做一层映射，方便下游 Agent B/C/E 使用
        formatted_events = []

        for event in raw_events:
            event_name = event.get("event_name", "未知话题")
            related_keywords = event.get("related_keywords", [])
            formatted_events.append(
                {
                    # 兼容字段（给报告/旧逻辑）
                    "topic": event_name,
                    "keywords": related_keywords,
                    # 标准字段（给 ETL / nodes / 新逻辑）
                    "event_name": event_name,
                    "related_keywords": related_keywords,
                    "total_heat": event.get("total_heat", 0),
                    "summary": event.get(
                        "merge_reason", ""
                    ),  # 把 ETL 归并时的理由带上作为简介
                    "created_at": str(
                        event.get("created_at", "")
                    ),  # 转字符串，防止 JSON 序列化报错
                }
            )

        print(f"✅ [Agent A] 成功锁定 {len(formatted_events)} 个核心议题。")
        if formatted_events:
            print(
                f"   🔥 榜首: {formatted_events[0]['topic']} (热度: {formatted_events[0]['total_heat']})"
            )

        # 3. 返回给 GraphState
        return {"core_events": formatted_events, "current_step": "Agent A 完成"}


# 单例导出
agent_stats = AgentStats()

from pymongo import (
    MongoClient,
    UpdateMany,
    UpdateOne,
    DeleteMany,
    DeleteOne,
    DESCENDING,
)
from typing import Any, List, Dict, Optional
from bson.objectid import ObjectId
from datetime import datetime, timedelta, timezone
import re
from app.core.config import settings


def _is_date_only(value: str) -> bool:
    """判断字符串是否为纯 'YYYY-MM-DD' 日期格式。"""
    if not value:
        return False
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", value.strip()))


from datetime import timedelta, timezone


def _parse_date_or_datetime(value: str) -> datetime:
    """严格解析日期-only (YYYY-MM-DD)，返回该日 00:00:00 的 tz-aware datetime（+08:00）。

    任何非 YYYY-MM-DD 格式都会抛出 ValueError。
    """
    s = (value or "").strip()
    if not s:
        raise ValueError("Empty date string")

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        raise ValueError(f"仅支持日期格式 YYYY-MM-DD，收到: {value}")

    tz_cn = timezone(timedelta(hours=8))
    dt = datetime.strptime(s, "%Y-%m-%d")
    return dt.replace(tzinfo=tz_cn, hour=0, minute=0, second=0, microsecond=0)


class MongoManager:
    def __init__(self):
        """
        初始化 MongoDB 连接。
        """
        try:
            self.client = MongoClient(settings.MONGO_URI)
            self.db = self.client[settings.MONGO_DB_NAME]
            print("✅ MongoDB 连接成功。")
        except Exception as e:
            print(f"❌ MongoDB 连接失败: {e}")
            raise e

    def get_collection(self, collection_name: str):
        """
        获取指定名称的集合。
        """
        return self.db[collection_name]

    def get_raw_hot_searches(
        self, start_date: str, end_date: str, user_limit: Optional[int] = None
    ) -> List[Dict]:
        """
        根据日期范围获取热搜快照。

        :param start_date: 开始日期字符串 (格式 "YYYY-MM-DD")
        :param end_date: 结束日期字符串 (格式 "YYYY-MM-DD")
        :param user_limit: 用户指定的数量 (可选)
        :return: 热搜快照列表
        """
        # 1. 解析并计算日期区间与默认 limit（支持只传日期 YYYY-MM-DD）
        try:
            if not end_date:
                end_date = start_date

            d1 = _parse_date_or_datetime(start_date)
            d2 = _parse_date_or_datetime(end_date)

            # 如果传入仅为日期（YYYY-MM-DD），把区间扩展到该天的全时段
            if _is_date_only(start_date):
                d1 = d1.replace(hour=0, minute=0, second=0, microsecond=0)
            if _is_date_only(end_date):
                d2 = d2.replace(hour=23, minute=59, second=59, microsecond=999999)

            # 以日期差为单位计算默认 limit
            delta_days = (d2.date() - d1.date()).days + 1  # 包含结束日期
            if delta_days <= 0:
                print("⚠️ 结束日期必须大于或等于开始日期，默认返回最近一天的数据。")
                delta_days = 1

            default_limit = delta_days * 3
            limit = (
                user_limit
                if user_limit is not None and user_limit <= default_limit
                else default_limit
            )

            print(
                f"ℹ️ 查询日期范围: {d1.isoformat(sep=' ')} 至 {d2.isoformat(sep=' ')}, 计划使用{limit}个热搜快照."
            )
        except Exception as e:
            print(f"❌ [ETL] 日期解析错误: {e}")
            return []

        # 以空格分隔的 ISO 格式生成，与数据库中现有时间格式保持一致
        gte = d1.isoformat(sep=" ")
        lte = d2.isoformat(sep=" ")

        query = {"source": "weibo_social", "collected_at": {"$gte": gte, "$lte": lte}}

        cursor = (
            self.db["hot_trends_history"]
            .find(query)
            .sort("collected_at", DESCENDING)
            .limit(limit)
        )
        results = list(cursor)
        print(f"✅ 获取到 {len(results)} 条热搜快照数据。")
        return results

    def get_raw_trend_items(self, start_date: str, end_date: str) -> List[Dict]:
        """
        获取所有快照中的 top_n 数组，并炸开成平铺列表
        用于给 EventMerger 做本地预聚合
        """
        snapshots = self.get_raw_hot_searches(start_date, end_date)
        raw_items = []

        for snap in snapshots:
            if "top_n" in snap:
                for item in snap["top_n"]:
                    raw_items.append(
                        {
                            "word": item.get("word"),
                            "num": item.get("num"),
                            "collected_at": snap.get("collected_at"),
                        }
                    )

        return raw_items

    def save_core_events(self, events: List[Dict]):
        """
        保存清洗后的热度TOP事件到'events'集合
        """
        if not events:
            print("⚠️ 无事件数据可保存。")
            return
        self.db["events"].delete_many({})
        self.db["events"].insert_many(events)
        print(f"✅ 已保存 {len(events)} 条核心事件数据到 'events' 集合。")

    def get_top_events(self, events: List[Dict], top_n: int = 10) -> List[Dict]:
        """
        从事件列表中获取按热度排序的前 N 个事件。

        :param events: 事件列表
        :param top_n: 需要获取的前 N 个事件数量
        :return: 排序后的前 N 个事件列表
        """
        return list(
            self.db["events"].find().sort("total_heat", DESCENDING).limit(top_n)
        )

    def get_posts_by_keywords(self, keywords: List[str], limit: int = 10) -> List[Dict]:
        """
        根据合并后的关键词列表，取weibo_contents表里找帖子
        逻辑：只要帖子的source_keyword在这个事件的关键词列表里，就是这个事件的帖子
        """
        if not keywords:
            print("⚠️ 关键词列表为空，无法查询帖子。")
            return []

        query = {"source_keyword": {"$in": keywords}}
        # 按点赞数倒序，取最热的帖子
        return list(
            self.db["weibo_contents"]
            .find(query)
            .sort("liked_count", DESCENDING)
            .limit(limit)
        )

    def get_comments_by_post_ids(
        self, note_ids: List[str], limit: int = 200
    ) -> List[Dict]:
        """
        根据帖子 note_id 列表，获取对应的评论数据。
        🔥 修改点：按 'comment_like_count' 倒序排列，优先获取高赞评论。
        """
        if not note_ids:
            print("⚠️ 帖子 note_id 列表为空，无法查询评论。")
            return []

        query = {"note_id": {"$in": note_ids}}

        # 这里加上 sort，确保 Agent B 分析的是热门观点
        return list(
            self.db["weibo_comments"]
            .find(query)
            .sort("comment_like_count", DESCENDING)
            .limit(limit)
        )

    def get_pending_posts(self, batch_size: int = 50) -> List[Dict]:
        """
        🔥 新增：获取需要审核的帖子（即还没有 'audit_status' 字段，或状态不是 'completed' 的）
        用于断点续传，每次只捞没处理过的。
        """
        query = {
            "$or": [
                {"audit_status": {"$exists": False}},
                {"audit_status": {"$ne": "completed"}},  # ne = not equal
            ]
        }
        # 只取需要的字段，减少网络传输（同时保证审核链路有足够信息）
        projection = {
            "_id": 1,
            "note_id": 1,
            "content": 1,
            "image_list": 1,
            "video_url": 1,
            "audit_status": 1,
            "created_at": 1,
        }

        return list(self.db["weibo_contents"].find(query, projection).limit(batch_size))

    def _bulk_update_audit(self, collection_name: str, updates: List[Dict]):
        """通用批量更新逻辑"""
        if not updates:
            return

        operations = []
        for item in updates:
            try:
                # 兼容处理字符串 ID 和 ObjectId
                oid = (
                    ObjectId(item["id"])
                    if isinstance(item["id"], str) and len(item["id"]) == 24
                    else item["id"]
                )
            except:
                oid = item["id"]

            op = UpdateOne(
                {"_id": oid},
                {
                    "$set": {
                        "is_violation": item.get("is_violation", True),
                        "violation_info": item.get(
                            "violation_info", {}
                        ),  # 包含证据链、标签、风险等级
                        "audit_status": "completed",
                        "audit_time": datetime.now(),
                    }
                },
            )
            operations.append(op)

        if operations:
            result = self.db[collection_name].bulk_write(operations)
            print(f"⚖️ [{collection_name}] 已回写 {result.modified_count} 条审核记录")

    def update_post_audit(self, updates: List[Dict]):
        """回写帖子的审核结果 (weibo_contents)"""
        self._bulk_update_audit("weibo_contents", updates)

    def update_comment_audit(self, updates: List[Dict]):
        """回写评论的审核结果 (weibo_comments)"""
        self._bulk_update_audit("weibo_comments", updates)

    def save_report_session(self, session_data: Dict):
        self.db["report_sessions"].insert_one(session_data)

    def get_report_history(self, limit: int = 10):
        return list(
            self.db["report_sessions"].find().sort("created_at", -1).limit(limit)
        )


mongo_db = MongoManager()
# comment_like_count

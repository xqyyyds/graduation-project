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
from datetime import datetime
import re
from app.core.config import settings
from app.core.logger import logger


def _is_date_only(value: str) -> bool:
    """判断字符串是否为纯 'YYYY-MM-DD' 日期格式。"""
    if not value:
        return False
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", value.strip()))


from datetime import timedelta, timezone


def _parse_date_or_datetime(value: str) -> datetime:
    """解析日期或日期时间字符串，尽量兼容常见格式：

    支持：
      - YYYY-MM-DD                -> 返回该日 00:00:00 (tz +08:00)
      - YYYY-MM-DD HH:MM:SS       -> 返回对应时刻 (tz +08:00)
      - YYYY-MM-DDTHH:MM:SS       -> 返回对应时刻 (tz +08:00)
      - ISO 8601 带时区偏移的格式也会被接受（如 YYYY-MM-DDTHH:MM:SS+08:00）

    当解析到无时区信息的 datetime 时，会默认设置为 +08:00。
    若字符串为空或无法解析会抛出 ValueError。
    """
    s = (value or "").strip()
    if not s:
        raise ValueError("Empty date string")

    tz_cn = timezone(timedelta(hours=8))

    # 1) 直接尝试 ISO 格式（支持 'T' 或空格作为分隔）
    try:
        # datetime.fromisoformat 支持 'YYYY-MM-DD'、'YYYY-MM-DD HH:MM:SS' 和带偏移的 ISO
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz_cn)
        return dt
    except Exception:
        pass

    # 2) 常见明确格式： 'YYYY-MM-DD HH:MM:SS'
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=tz_cn)
    except Exception:
        pass

    # 3) 只包含日期 YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        dt = datetime.strptime(s, "%Y-%m-%d")
        return dt.replace(tzinfo=tz_cn, hour=0, minute=0, second=0, microsecond=0)

    # 无法解析
    raise ValueError(
        f"无法解析的日期格式，支持 YYYY-MM-DD 或 带时间的 ISO 格式，收到: {value}"
    )


class MongoManager:
    def __init__(self):
        """
        初始化 MongoDB 连接。
        """
        try:
            self.client = MongoClient(settings.MONGO_URI)
            self.db = self.client[settings.MONGO_DB_NAME]
            logger.info(" MongoDB 连接成功。")
        except Exception as e:
            logger.error(f" MongoDB 连接失败: {e}")
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
                logger.warning(
                    " 结束日期必须大于或等于开始日期，默认返回最近一天的数据。"
                )
                delta_days = 1

            default_limit = delta_days * 3
            limit = (
                user_limit
                if user_limit is not None and user_limit <= default_limit
                else default_limit
            )

            logger.info(
                f"ℹ️ 查询日期范围: {d1.isoformat(sep=' ')} 至 {d2.isoformat(sep=' ')}, 计划使用{limit}个热搜快照."
            )
        except Exception as e:
            logger.error(f" [ETL] 日期解析错误: {e}")
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
        logger.info(f" 获取到 {len(results)} 条热搜快照数据。")
        return results

    def get_raw_trend_items(self, start_date: str, end_date: str) -> List[Dict]:
        """
        获取所有快照中的 top_n 数组，并炸开成平铺列表
        用于给 EventMerger 做本地预聚合
        返回的每个 item 包含：word, num, collected_at, category(如有)
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
                            "category": item.get("category"),  # 可能为 None
                        }
                    )

        return raw_items

    def get_existing_categories(self, start_date: str, end_date: str) -> Dict[str, str]:
        """
        获取指定日期范围内已有分类的热搜词条
        :return: {word: category} 字典
        """
        snapshots = self.get_raw_hot_searches(start_date, end_date)
        existing = {}

        for snap in snapshots:
            if "top_n" in snap:
                for item in snap["top_n"]:
                    word = item.get("word")
                    category = item.get("category")
                    if word and category:
                        existing[word] = category

        return existing

    def update_hot_search_categories(
        self, category_map: Dict[str, str], start_date: str, end_date: str
    ):
        """
        批量更新热搜词条的类别
        :param category_map: {word: category} 字典
        :param start_date: 开始日期
        :param end_date: 结束日期
        """
        if not category_map:
            logger.warning(" 无分类数据可更新")
            return

        # 获取日期范围内的快照
        snapshots = self.get_raw_hot_searches(start_date, end_date)

        operations = []
        updated_count = 0

        for snap in snapshots:
            snap_id = snap.get("_id")
            top_n = snap.get("top_n", [])

            # 检查是否需要更新
            needs_update = False
            new_top_n = []

            for item in top_n:
                word = item.get("word")
                if word in category_map and not item.get("category"):
                    # 需要更新：该词条在 map 中且当前无分类
                    new_item = dict(item)
                    new_item["category"] = category_map[word]
                    new_top_n.append(new_item)
                    needs_update = True
                    updated_count += 1
                else:
                    new_top_n.append(item)

            if needs_update:
                operations.append(
                    UpdateOne({"_id": snap_id}, {"$set": {"top_n": new_top_n}})
                )

        if operations:
            result = self.db["hot_trends_history"].bulk_write(operations)
            logger.info(
                f" [分类回写] 已更新 {result.modified_count} 个快照，共 {updated_count} 个词条分类"
            )

    def save_core_events(self, events: List[Dict]):
        """
        保存清洗后的热度TOP事件到'events'集合
        """
        if not events:
            logger.warning(" 无事件数据可保存。")
            return
        self.db["events"].delete_many({})
        self.db["events"].insert_many(events)
        logger.info(f" 已保存 {len(events)} 条核心事件数据到 'events' 集合。")

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
            logger.warning(" 关键词列表为空，无法查询帖子。")
            return []

        query = {"source_keyword": {"$in": keywords}}
        # 按点赞数倒序，取最热的帖子
        #  修正：使用 collation 做数值排序，解决字符串 "10" < "2" 的问题
        try:
            return list(
                self.db["weibo_contents"]
                .find(query)
                .sort("liked_count", DESCENDING)
                .collation({"locale": "en_US", "numericOrdering": True})
                .limit(limit)
            )
        except Exception as e:
            # 万一 DB 版本过低不支持 collation，降级为普通查询
            logger.warning(f" [MongoDB] Collation 排序失败，降级为普通排序: {e}")
            return list(
                self.db["weibo_contents"]
                .find(query)
                .sort("liked_count", DESCENDING)
                .limit(limit)
            )

    def get_comments_by_post_ids(
        self,
        note_ids: List[str],
        limit: int = 200,
        sort_field: str = "comment_like_count",
        descending: bool = True,
    ) -> List[Dict]:
        """
        根据帖子 note_id 列表，获取对应的评论数据。
         修改点：按 'comment_like_count' 倒序排列，优先获取高赞评论。
        """
        if not note_ids:
            logger.warning(" 帖子 note_id 列表为空，无法查询评论。")
            return []

        query = {"note_id": {"$in": note_ids}}

        sort_order = DESCENDING if descending else 1

        # 这里加上 sort，确保 Agent B 分析的是热门观点
        #  修正：使用 collation 做数值排序
        try:
            return list(
                self.db["weibo_comments"]
                .find(query)
                .sort(sort_field, sort_order)
                .collation({"locale": "en_US", "numericOrdering": True})
                .limit(limit)
            )
        except Exception as e:
            logger.warning(f" [MongoDB] Collation 排序失败，降级为普通排序: {e}")
            return list(
                self.db["weibo_comments"]
                .find(query)
                .sort(sort_field, sort_order)
                .limit(limit)
            )

    def get_grouped_comments_by_post_ids(
        self,
        note_ids: List[str],
        limit_per_post: int = 20,
        sort_field: str = "comment_like_count",
        descending: bool = True,
    ) -> Dict[str, List[Dict]]:
        """
        批量获取多个帖子的评论，并按 note_id 分组后截取每个帖子的前 N 条。
        用于替代逐帖 N+1 查询，显著降低 Node A 的评论抓取次数。
        """
        if not note_ids:
            return {}

        sort_order = -1 if descending else 1
        sort_expr = f"${sort_field}"
        pipeline: List[Dict[str, Any]] = [{"$match": {"note_id": {"$in": note_ids}}}]

        if sort_field in {"comment_like_count"}:
            pipeline.append(
                {
                    "$addFields": {
                        "__sort_value": {
                            "$convert": {
                                "input": sort_expr,
                                "to": "double",
                                "onError": 0,
                                "onNull": 0,
                            }
                        }
                    }
                }
            )
            sort_key = "__sort_value"
        else:
            sort_key = sort_field

        pipeline.extend(
            [
                {"$sort": {"note_id": 1, sort_key: sort_order}},
                {"$group": {"_id": "$note_id", "docs": {"$push": "$$ROOT"}}},
                {"$project": {"docs": {"$slice": ["$docs", limit_per_post]}}},
            ]
        )

        grouped: Dict[str, List[Dict]] = {}
        try:
            for row in self.db["weibo_comments"].aggregate(pipeline, allowDiskUse=True):
                grouped[str(row.get("_id") or "")] = row.get("docs") or []
        except Exception as e:
            logger.warning(f" [MongoDB] 批量分组抓取评论失败，降级逐帖查询: {e}")
            for note_id in note_ids:
                grouped[str(note_id)] = self.get_comments_by_post_ids(
                    [note_id],
                    limit=limit_per_post,
                    sort_field=sort_field,
                    descending=descending,
                )
        return grouped

    def get_comment_candidates_by_post_id(
        self,
        note_id: str,
        hot_limit: int = 60,
        recent_limit: int = 40,
    ) -> List[Dict]:
        """
        为审核链准备评论候选池：
        - 高赞前 hot_limit 条
        - 最新前 recent_limit 条
        - 合并后按 comment_id / _id 去重
        """
        if not note_id:
            return []

        hot_comments = self.get_comments_by_post_ids(
            [note_id],
            limit=hot_limit,
            sort_field="comment_like_count",
            descending=True,
        )
        recent_comments = self.get_comments_by_post_ids(
            [note_id],
            limit=recent_limit,
            sort_field="create_date_time",
            descending=True,
        )

        merged: List[Dict] = []
        seen = set()
        for item in hot_comments + recent_comments:
            if not isinstance(item, dict):
                continue
            key = (
                item.get("comment_id")
                or (str(item.get("_id")) if item.get("_id") else "")
                or item.get("content")
            )
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    def get_comment_candidates_by_post_ids(
        self,
        note_ids: List[str],
        hot_limit: int = 60,
        recent_limit: int = 40,
    ) -> Dict[str, List[Dict]]:
        """
        为多个帖子一次性准备评论候选池：
        - 每帖高赞前 hot_limit 条
        - 每帖最新前 recent_limit 条
        - 按 comment_id / _id / content 去重
        """
        if not note_ids:
            return {}

        hot_grouped = self.get_grouped_comments_by_post_ids(
            note_ids=note_ids,
            limit_per_post=hot_limit,
            sort_field="comment_like_count",
            descending=True,
        )
        recent_grouped = self.get_grouped_comments_by_post_ids(
            note_ids=note_ids,
            limit_per_post=recent_limit,
            sort_field="create_date_time",
            descending=True,
        )

        result: Dict[str, List[Dict]] = {}
        for note_id in note_ids:
            key = str(note_id)
            merged: List[Dict] = []
            seen = set()
            for item in (hot_grouped.get(key) or []) + (recent_grouped.get(key) or []):
                if not isinstance(item, dict):
                    continue
                dedup_key = (
                    item.get("comment_id")
                    or (str(item.get("_id")) if item.get("_id") else "")
                    or item.get("content")
                )
                if not dedup_key or dedup_key in seen:
                    continue
                seen.add(dedup_key)
                merged.append(item)
            result[key] = merged
        return result

    def get_pending_posts(self, batch_size: int = 50) -> List[Dict]:
        """
         新增：获取需要审核的帖子（即还没有 'audit_status' 字段，或状态不是 'completed' 的）
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
            logger.info(
                f"⚖️ [{collection_name}] 已回写 {result.modified_count} 条审核记录"
            )

    def update_post_audit(self, updates: List[Dict]):
        """回写帖子的审核结果 (weibo_contents)"""
        self._bulk_update_audit("weibo_contents", updates)

    def update_comment_audit(self, updates: List[Dict]):
        """回写评论的审核结果 (weibo_comments)"""
        self._bulk_update_audit("weibo_comments", updates)

    def save_report_session(self, session_data: Dict):
        payload = dict(session_data or {})
        report_json = payload.get("report_json") or {}
        meta = report_json.get("meta") or {}
        payload.setdefault("render_version", meta.get("render_version") or "report_json_v2")
        self.db["report_sessions"].insert_one(payload)

    def get_report_session_by_filename(self, filename: str) -> Optional[Dict]:
        escaped = re.escape(filename)
        query = {
            "$or": [
                {"md_path": {"$regex": f"{escaped}$"}},
                {"json_path": {"$regex": f"{re.escape(filename.replace('.md', '.json'))}$"}},
                {"html_path": {"$regex": f"{re.escape(filename.replace('.md', '.html'))}$"}},
                {"pdf_path": {"$regex": f"{re.escape(filename.replace('.md', '.pdf'))}$"}},
            ]
        }
        return self.db["report_sessions"].find_one(query, sort=[("created_at", DESCENDING)])

    def get_report_history(self, limit: int = 10):
        return list(
            self.db["report_sessions"].find().sort("created_at", -1).limit(limit)
        )

    # ------------------------------------------------------------------
    #  新增：从 report_sessions 聚合全局违规统计
    # ------------------------------------------------------------------
    def get_dashboard_violation_stats(self) -> Dict[str, int]:
        """
        读取最新一条 report_sessions 中的违规统计（violation_stats 字段），仅返回最新报告的统计数据。
        """
        try:
            cursor = (
                self.db["report_sessions"]
                .find()
                .sort("created_at", DESCENDING)
                .limit(1)
            )
            sessions = list(cursor)
            if not sessions:
                logger.info(" [MongoDB] 未找到 report_sessions，返回空统计")
                return {}

            latest = sessions[0]
            stats = (
                latest.get("violation_stats")
                or latest.get("violation_category_counts")
                or {}
            )

            if not isinstance(stats, dict):
                logger.warning(
                    " [MongoDB] 最新 report_sessions 中的 violation_stats 非字典类型，返回空统计"
                )
                return {}

            logger.info(f" [MongoDB] 获取最新报告违规统计，覆盖 {len(stats)} 个类别")
            return stats
        except Exception as e:
            logger.error(f" [MongoDB] 读取最新报告违规统计失败: {e}")
            return {}


mongo_db = MongoManager()
# comment_like_count

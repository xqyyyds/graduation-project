# app/etl/event_merger.py
"""
 重构版 ETL：移除 LLM 聚类，改用简单的精确匹配热度累加
只有当热搜关键词完全相同（字符串精确匹配）时才累加热度
返回热度 Top 20 的热搜词条
支持按类别筛选：综合(不筛选)、社会、高校、生活、科技、政治、其他
"""
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any, Optional

from app.core.logger import logger
from app.db.mongo_manager import mongo_db


class EventMerger:
    """
    简化版事件管理器：不再使用 LLM 聚类
    只对完全相同的热搜词条进行热度累加
    支持按类别筛选
    """

    def __init__(self):
        #  移除所有 LLM 相关初始化
        # 不再需要 structured_llm 和 review_llm
        pass

    def run_merge_task(
        self, start_date: str, end_date: str, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
         重构版：简单的精确匹配热度累加
        只有当热搜关键词完全相同（字符串精确匹配）时才累加热度
        返回热度 Top 20 的热搜词条

        :param start_date: 开始日期
        :param end_date: 结束日期
        :param category: 类别筛选，None 或 "综合" 表示不筛选
        :return: Top 20 热搜事件列表
        """
        # 处理类别参数
        filter_category = category if category and category != "综合" else None

        category_label = f"【{category}】" if filter_category else "【综合】"
        logger.info(
            f" [ETL] 开始执行 {category_label} 事件归并 ({start_date} ~ {end_date})..."
        )
        logger.info("    策略：精确匹配累加热度，不使用 LLM 聚类")

        if filter_category:
            logger.info(f"    类别筛选：{filter_category}")

        # 1. 捞取快照数据
        raw_items = mongo_db.get_raw_trend_items(start_date, end_date)
        if not raw_items:
            logger.warning(" [ETL] 无可用数据")
            return []

        logger.info(f"    [ETL] 获取到 {len(raw_items)} 条原始数据")

        # 2. 精确匹配累加：只有完全相同的词条才累加热度
        word_heat_map: Dict[str, int] = defaultdict(int)
        word_first_seen: Dict[str, str] = {}  # 记录每个词的最早出现时间
        word_category_map: Dict[str, str] = {}  # 记录每个词的类别

        for item in raw_items:
            try:
                word = str(item.get("word", "")).strip()
                if not word:
                    continue

                item_category = item.get("category")

                #  类别筛选：如果指定了类别，只处理该类别的词条
                if filter_category:
                    if item_category != filter_category:
                        continue

                # 兼容处理 '123,456' 这种带逗号的字符串
                heat_val = int(str(item.get("num", 0)).replace(",", ""))

                #  精确匹配：只有完全相同的字符串才累加
                word_heat_map[word] += heat_val

                # 记录最早时间
                collected_at = item.get("collected_at")
                if collected_at:
                    if (
                        word not in word_first_seen
                        or collected_at < word_first_seen[word]
                    ):
                        word_first_seen[word] = collected_at

                # 记录类别
                if item_category and word not in word_category_map:
                    word_category_map[word] = item_category

            except Exception as e:
                logger.debug(f"    [ETL] 跳过无效数据: {e}")
                continue

        logger.info(f"    [ETL] 筛选后共 {len(word_heat_map)} 个热搜词条")

        # 3. 按热度排序，取 Top 20
        sorted_items = sorted(word_heat_map.items(), key=lambda x: x[1], reverse=True)[
            :20
        ]

        # 4. 构建最终事件列表
        final_events: List[Dict[str, Any]] = []

        def _clean_hashtag(s: str) -> str:
            """清理 # 号"""
            if not s:
                return s
            return s.strip().strip("#").strip()

        for word, total_heat in sorted_items:
            # 获取最早时间
            first_seen = word_first_seen.get(word)
            if first_seen:
                try:
                    # 尝试解析时间字符串
                    if isinstance(first_seen, str):
                        created_at = datetime.fromisoformat(
                            first_seen.replace("Z", "+00:00")
                        )
                    else:
                        created_at = first_seen
                except:
                    created_at = datetime.now()
            else:
                created_at = datetime.now()

            # 清理事件名称
            event_name = _clean_hashtag(word)

            # 获取类别
            item_cat = word_category_map.get(word, "未分类")

            final_events.append(
                {
                    "event_name": event_name,
                    "related_keywords": [word],  # 保留原始关键词（含 #）
                    "total_heat": total_heat,
                    "heat_score": total_heat,
                    "category": item_cat,  #  新增类别字段
                    "merge_reason": "精确匹配累加",  # 说明这是简单累加，非 LLM 聚类
                    "period": f"{start_date} to {end_date}",
                    "created_at": created_at,
                }
            )

        # 5. 存入数据库
        mongo_db.save_core_events(final_events)

        logger.info(f" [ETL] 归并完成，已生成 Top {len(final_events)} 热搜事件")
        for i, evt in enumerate(final_events[:5]):
            cat_label = f"[{evt.get('category', '未分类')}]" if filter_category else ""
            logger.info(
                f"    Top{i+1}: {cat_label} {evt['event_name']} (热度: {evt['total_heat']})"
            )

        return final_events


# 单例导出
event_merger = EventMerger()

# app/etl/event_merger.py
import json
from collections import defaultdict
from datetime import datetime
from typing import List

# 引入 LangChain 组件
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.core.logger import logger
from app.db.mongo_manager import mongo_db
from app.core.prompts import ETL_EVENT_MERGE_PROMPT

# 引入刚定义的 Pydantic 模型
from app.core.schemas import EventList


class EventMerger:
    def __init__(self):
        # 1. 初始化 ChatOpenAI
        # 即使是智谱 GLM-4，也完美支持 OpenAI 的 SDK 规范
        self.llm = init_chat_model(
            model=settings.LLM_MODEL,  # 例如 "glm-4-flash"
            model_provider="openai",  # 关键点：指定提供商为 openai (因为智谱兼容 OpenAI 接口)
            api_key=settings.ZHIPU_API_KEY,
            base_url=settings.LLM_BASE_URL,  # 这里的 URL 必须是智谱的地址
            temperature=0.1,  # 其他参数直接传
        )
        # 2. 核心魔法：绑定结构化输出
        # 这会让模型强制输出符合 EventList 定义的 JSON
        self.structured_llm = self.llm.with_structured_output(EventList)

    def run_merge_task(self, start_date: str, end_date: str):
        """执行语义归并与热度计算主流程"""
        logger.info(f"🚀 [ETL] 开始执行高可靠事件归并 ({start_date} ~ {end_date})...")

        # 1. 捞取快照数据
        raw_items = mongo_db.get_raw_trend_items(start_date, end_date)
        if not raw_items:
            logger.warning("⚠️ [ETL] 无可用数据")
            return []

        # 2. 本地预处理：去重并累加热度，同时记录每个词的最早出现时间
        word_map = defaultdict(int)
        word_first_seen = {}  # 新增：记录每个词的最早 collected_at

        for item in raw_items:
            try:
                # 兼容处理 '123,456' 这种带逗号的字符串
                val = int(str(item["num"]).replace(",", ""))
                word = item["word"]
                word_map[word] += val

                # 记录最早时间
                collected_at = item.get("collected_at")
                if collected_at:
                    # 数据库存储为 ISO 格式字符串，直接比较字符串即可获取最早时间
                    if (
                        word not in word_first_seen
                        or collected_at < word_first_seen[word]
                    ):
                        word_first_seen[word] = collected_at
            except:
                continue

        # 使用所有排序后的关键词（热搜数量本身不多，无需人为截断）
        sorted_keys = sorted(word_map.keys(), key=lambda x: word_map[x], reverse=True)

        # 3. 调用结构化 LLM 获取结果
        logger.info(
            f"🤖 [ETL] 正在调用 LLM 进行语义聚类 (处理 {len(sorted_keys)} 个词条)..."
        )
        merged_data = self._get_structured_groups(sorted_keys)

        # 4. 构建最终事件并保存
        if not merged_data or not merged_data.events:
            logger.error("❌ [ETL] 归并结果为空")
            return []

        final_events = []
        # 用于记录哪些词已经被归类了，防止重复或遗漏
        covered_keywords = set()

        for event in merged_data.events:
            # 验证关键词有效性：必须存在于原始数据中
            valid_kws = []
            for kw in event.keywords:
                if kw in word_map:
                    valid_kws.append(kw)
                    covered_keywords.add(kw)
                else:
                    # 尝试简单的模糊修复 (去除空格等)
                    clean_kw = kw.strip()
                    if clean_kw in word_map:
                        valid_kws.append(clean_kw)
                        covered_keywords.add(clean_kw)
                    else:
                        logger.warning(f"⚠️ [ETL] 忽略无效/幻觉词条: {kw}")

            if not valid_kws:
                continue

            # 计算该事件的总热度 (把该组内所有关键词的原始热度加起来)
            total_heat = sum(word_map.get(kw, 0) for kw in valid_kws)

            # 🔥 核心修复：计算该事件的最早发生时间
            # 取该组内所有关键词中，最早的 collected_at
            earliest_time = None
            for kw in valid_kws:
                t = word_first_seen.get(kw)
                if t:
                    if earliest_time is None or t < earliest_time:
                        earliest_time = t

            # 如果实在没找到时间，才用当前时间兜底
            final_created_at = earliest_time if earliest_time else datetime.now()

            final_events.append(
                {
                    "event_name": event.event_name,
                    "related_keywords": valid_kws,
                    "total_heat": total_heat,
                    "heat_score": total_heat,  # 用于排序
                    "merge_reason": event.reasoning,  # 保存理由，增加可解释性
                    "period": f"{start_date} to {end_date}",
                    "created_at": final_created_at,  # 🔥 使用真实的最早时间
                }
            )

        # 5. (可选) 兜底处理：将未被 LLM 归类的词条单独作为事件保留
        # 遵循“全量保留原则”
        all_keys = set(word_map.keys())
        missing_keys = all_keys - covered_keywords
        if missing_keys:
            logger.info(
                f"ℹ️ [ETL] 发现 {len(missing_keys)} 个未归类词条，正在自动补全..."
            )
            for kw in missing_keys:
                heat = word_map[kw]
                # 同样获取最早时间
                final_created_at = word_first_seen.get(kw) or datetime.now()

                final_events.append(
                    {
                        "event_name": kw,  # 孤立词条直接用原名
                        "related_keywords": [kw],
                        "total_heat": heat,
                        "heat_score": heat,
                        "merge_reason": "自动补全：未被LLM归类的独立词条",
                        "period": f"{start_date} to {end_date}",
                        "created_at": final_created_at,
                    }
                )

        # 按热度倒序排列
        final_events = sorted(final_events, key=lambda x: x["total_heat"], reverse=True)

        # 存入数据库
        mongo_db.save_core_events(final_events)

        logger.info(f"✅ [ETL] 归并完成，已生成 {len(final_events)} 个核心事件")
        return final_events

    def _get_structured_groups(self, word_list: List[str]) -> EventList:
        """利用 LangChain + Pydantic 进行聚类"""

        # 构建 Prompt 模板
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一个专业的数据清洗专家，擅长从非结构化文本中提取结构化信息。",
                ),
                ("user", ETL_EVENT_MERGE_PROMPT),
            ]
        )

        # 链式调用：Prompt -> LLM (带结构约束)
        chain = prompt | self.structured_llm

        try:
            # 直接传入参数，invoke 返回的直接就是 EventList 对象
            # 不需要再 json.loads 了！
            result = chain.invoke(
                {"topic_list_json": json.dumps(word_list, ensure_ascii=False)}
            )
            return result

        except Exception as e:
            logger.error(f"❌ [LLM Structured Output Error]: {e}")
            # 返回一个空对象防止程序崩溃
            return EventList(events=[])


# 单例导出
event_merger = EventMerger()

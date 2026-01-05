# app/etl/event_merger.py
import json
from collections import defaultdict
from datetime import datetime
from typing import List

# 引入 LangChain 组件
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
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
        print(f"🚀 [ETL] 开始执行高可靠事件归并 ({start_date} ~ {end_date})...")

        # 1. 捞取快照数据
        raw_items = mongo_db.get_raw_trend_items(start_date, end_date)
        if not raw_items:
            print("⚠️ [ETL] 无可用数据")
            return []

        # 2. 本地预处理：去重并累加热度
        word_map = defaultdict(int)
        for item in raw_items:
            try:
                # 兼容处理 '123,456' 这种带逗号的字符串
                val = int(str(item["num"]).replace(",", ""))
                word_map[item["word"]] += val
            except:
                continue

        # 取热度最高的 Top 150 个词送入大模型
        # 数量太多会撑爆 Token 且浪费钱，150个足够覆盖主要舆情
        ###这里可能需要更改！！！
        sorted_keys = sorted(word_map.keys(), key=lambda x: word_map[x], reverse=True)[
            :150
        ]

        # 3. 调用结构化 LLM 获取结果
        print(f"🤖 [ETL] 正在调用 LLM 进行语义聚类 (处理 {len(sorted_keys)} 个词条)...")
        merged_data = self._get_structured_groups(sorted_keys)

        # 4. 构建最终事件并保存
        if not merged_data or not merged_data.events:
            print("❌ [ETL] 归并结果为空")
            return []

        final_events = []
        for event in merged_data.events:
            # 计算该事件的总热度 (把该组内所有关键词的原始热度加起来)
            total_heat = sum(word_map.get(kw, 0) for kw in event.keywords)

            final_events.append(
                {
                    "event_name": event.event_name,
                    "related_keywords": event.keywords,
                    "total_heat": total_heat,
                    "heat_score": total_heat,  # 用于排序
                    "merge_reason": event.reasoning,  # 保存理由，增加可解释性
                    "period": f"{start_date} to {end_date}",
                    "created_at": datetime.now(),
                }
            )

        # 按热度倒序排列
        final_events = sorted(final_events, key=lambda x: x["total_heat"], reverse=True)

        # 存入数据库
        mongo_db.save_core_events(final_events)

        print(f"✅ [ETL] 归并完成，已生成 {len(final_events)} 个核心事件")
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
            print(f"❌ [LLM Structured Output Error]: {e}")
            # 返回一个空对象防止程序崩溃
            return EventList(events=[])


# 单例导出
event_merger = EventMerger()

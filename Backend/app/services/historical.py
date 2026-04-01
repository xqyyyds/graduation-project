import os
import calendar
from datetime import datetime
from typing import Dict, Any, List, Optional
from dateutil.relativedelta import relativedelta
import concurrent.futures

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.core.logger import logger
from app.core.schemas import HistoricalDailyEvent, HistoricalEventsList, HistoricalSummary
from app.core.prompts import AGENT_HISTORICAL_DAILY_EXTRACT_TEMPLATE, AGENT_HISTORICAL_SUMMARY_TEMPLATE
from app.services.utils import get_web_context


class AgentHistorical:
    """
    Agent Historical: 历史同期热门事件回顾
    职责：搜索去年同月每天的代表性热点事件
    """

    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            openai_api_key=settings.ZHIPU_API_KEY,
            openai_api_base=settings.LLM_BASE_URL,
            temperature=0.3,
            request_timeout=60,
            max_retries=2,
        )

    def analyze(self, end_date: str) -> Dict[str, Any]:
        """
        分析历史同期热门事件

        参数:
            end_date: 用户输入的结束时间，格式 "YYYY-MM-DD HH:MM:SS"

        返回:
            Dict: 包含 historical_events (HistoricalEventsList 字典格式)
        """
        logger.info("\n [Agent Historical] 启动：历史同期热门事件回顾...")

        # 1. 解析结束日期并计算去年同月
        try:
            dt = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
        except Exception:
            # 尝试其他格式
            try:
                dt = datetime.strptime(end_date.split()[0], "%Y-%m-%d")
            except Exception:
                logger.error(f" [Agent Historical] 无法解析日期: {end_date}")
                return {"historical_events": None, "current_step": "Historical_Error"}

        # 计算去年同月
        last_year_date = dt - relativedelta(years=1)
        year = last_year_date.year
        month = last_year_date.month

        # 使用 calendar 模块获取该月的天数
        days_in_month = calendar.monthrange(year, month)[1]

        logger.info(
            f"    [Agent Historical] 目标时间: {year}年{month}月 (共{days_in_month}天)"
        )

        # 2. 构造日期列表
        dates = [
            datetime(year, month, day).strftime("%Y-%m-%d")
            for day in range(1, days_in_month + 1)
        ]

        # 3. 并发搜索每天的代表性事件
        daily_events = self._fetch_daily_events_parallel(dates)

        # 4. 生成导语（使用 LLM）
        year_month_str = f"{year}年{month}月"
        summary = self._generate_summary(year_month_str, daily_events)

        # 5. 构建结果
        result = HistoricalEventsList(
            year_month=f"{year}-{month:02d}", events=daily_events
        )

        # 转换为字典格式以便在 state 中传递
        result_dict = {
            "year_month": result.year_month,
            "events": [e.model_dump() for e in result.events],
            "summary": summary,  # 添加导语
        }

        logger.info(
            f" [Agent Historical] 完成。共获取 {len(daily_events)} 个历史事件。"
        )

        return {"historical_events": result_dict, "current_step": "Historical_Done"}

    def _fetch_daily_events_parallel(
        self, dates: List[str], max_workers: int = 8
    ) -> List[HistoricalDailyEvent]:
        """
        并发搜索每天的代表性事件

        参数:
            dates: 日期列表 ["2024-01-01", "2024-01-02", ...]
            max_workers: 最大并发数

        返回:
            List[HistoricalDailyEvent]: 每天的事件列表（失败的日期会被跳过）
        """
        results = []

        def fetch_single_day(date_str: str) -> Optional[HistoricalDailyEvent]:
            """搜索单天的代表性事件"""
            try:
                # 构造搜索查询
                query = f"{date_str} 最热门事件 热搜 新闻 头条"

                # 执行搜索（只搜索1条结果，节省费用）
                search_results = get_web_context(query, search_depth="basic", max_results=1)

                # 如果搜索结果为空，返回 None
                if not search_results or "未检索到" in search_results:
                    logger.warning(f"    [Agent Historical] {date_str}: 无搜索结果")
                    return None

                # 使用 LLM 提取事件
                event = self._extract_event_from_search(date_str, search_results)
                return event

            except Exception as e:
                logger.error(f"    [Agent Historical] {date_str}: 搜索失败 - {e}")
                return None

        # 使用线程池并发执行
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_date = {executor.submit(fetch_single_day, d): d for d in dates}

            for future in concurrent.futures.as_completed(future_to_date):
                date_str = future_to_date[future]
                try:
                    event = future.result()
                    if event:
                        results.append(event)
                        logger.info(
                            f"    [Agent Historical] ✓ {date_str}: {event.event_title[:30]}..."
                        )
                except Exception as e:
                    logger.error(f"    [Agent Historical] ✗ {date_str}: 处理失败 - {e}")

        # 按日期排序
        results.sort(key=lambda x: x.date)
        return results

    def _extract_event_from_search(
        self, date_str: str, search_results: str
    ) -> Optional[HistoricalDailyEvent]:
        """
        从搜索结果中使用 LLM 提取当天最热门的事件

        参数:
            date_str: 日期 "2024-01-01"
            search_results: Tavily 搜索结果文本

        返回:
            HistoricalDailyEvent 或 None
        """
        try:
            structured_llm = self.llm.with_structured_output(HistoricalDailyEvent)
            prompt = ChatPromptTemplate.from_template(
                AGENT_HISTORICAL_DAILY_EXTRACT_TEMPLATE
            )

            chain = prompt | structured_llm

            result = chain.invoke(
                {"target_date": date_str, "search_results": search_results}
            )

            return result

        except Exception as e:
            logger.warning(f"    [Agent Historical] LLM 提取失败 ({date_str}): {e}")
            return None

    def _generate_summary(self, year_month: str, events: List[HistoricalDailyEvent]) -> str:
        """
        生成历史回顾章节的导语

        参数:
            year_month: 年月，如 "2024年1月"
            events: 事件列表

        返回:
            str: 导语文本
        """
        if not events:
            return f"以下为{year_month}每日代表性热点事件回顾，为研判提供历史参考。"

        try:
            # 提取所有事件的完整标题（不截断）
            event_titles = [e.event_title for e in events if e.event_title]
            events_list_str = "\n".join([f"{i+1}. {title}" for i, title in enumerate(event_titles)])

            # 使用结构化输出
            structured_llm = self.llm.with_structured_output(HistoricalSummary)
            prompt = ChatPromptTemplate.from_template(AGENT_HISTORICAL_SUMMARY_TEMPLATE)
            chain = prompt | structured_llm

            result = chain.invoke({
                "year_month": year_month,
                "events_list": events_list_str
            })

            return result.summary_text if result.summary_text else f"以下为{year_month}每日代表性热点事件回顾，为研判提供历史参考。"

        except Exception as e:
            logger.warning(f"    [Agent Historical] 导语生成失败: {e}，使用默认文本")
            return f"以下为{year_month}每日代表性热点事件回顾，为研判提供历史参考。"


# 单例导出
agent_historical = AgentHistorical()

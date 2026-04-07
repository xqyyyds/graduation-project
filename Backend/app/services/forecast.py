import datetime
from typing import Any, Dict, List, Optional

from dateutil.relativedelta import relativedelta
from langchain_core.prompts import ChatPromptTemplate

from app.core.llm_factory import get_main_llm
from app.core.logger import logger
from app.core.prompts import AGENT_D_FORECAST_TEMPLATE
from app.core.schemas import TrendForecastReport
from app.services.utils import get_web_context


class AgentForecast:
    """
    单模型版 Agent D：
    - 固定三类搜索
    - 主模型压缩联网情报
    - 主模型生成结构化预测
    """

    def __init__(self):
        self.context_llm = get_main_llm(
            temperature=0.2,
            request_timeout=120,
            max_retries=2,
        )
        self.forecast_llm = get_main_llm(
            temperature=0.5,
            request_timeout=180,
            max_retries=2,
        )

    def _compute_period(
        self, forecast_range: str, category: str, time_period_desc: Optional[str]
    ) -> str:
        now = datetime.datetime.now()
        range_map = {
            "1w": ("未来一周", 7, "days"),
            "2w": ("未来两周", 14, "days"),
            "1m": ("未来一个月", 1, "months"),
            "2m": ("未来两个月", 2, "months"),
        }
        range_desc, delta_val, delta_unit = range_map.get(
            forecast_range, ("未来一个月", 1, "months")
        )

        if delta_unit == "days":
            target_date = now + datetime.timedelta(days=delta_val)
        else:
            target_date = now + relativedelta(months=delta_val)

        if time_period_desc:
            base_period = time_period_desc
        else:
            base_period = f"{now.strftime('%Y年%m月%d日')}至{target_date.strftime('%Y年%m月%d日')}（{range_desc}）"

        if category and category not in ["综合", "其他", "全部"]:
            return f"【{category}领域】{base_period}"
        return base_period

    def _build_search_queries(
        self,
        category: str,
        forecast_range: str,
        current_opinion_analysis: str,
    ) -> Dict[str, str]:
        category_prefix = "" if category in ["综合", "其他", "全部", ""] else f"{category} "
        main_axis = (current_opinion_analysis or "").split("\n", 1)[0][:40]
        range_hint = {
            "1w": "未来一周",
            "2w": "未来两周",
            "1m": "未来一个月",
            "2m": "未来两个月",
        }.get(forecast_range, "未来一个月")

        return {
            "future_schedule": f"{category_prefix}{range_hint} 日程 政策 考试 活动",
            "historical_pattern": f"{category_prefix}往年同期 舆情 热点 风险",
            "current_axis": f"{category_prefix}{main_axis} 下阶段 风险 争议 发酵",
        }

    def _compress_web_context(self, raw_context: str, title: str) -> str:
        if not raw_context.strip():
            return f"【{title}】暂无有效联网情报"
        return f"【{title}】\n{raw_context[:900]}"

    def _collect_online_contexts(
        self,
        category: str,
        forecast_range: str,
        current_opinion_analysis: str,
    ) -> Dict[str, str]:
        queries = self._build_search_queries(category, forecast_range, current_opinion_analysis)
        results = {}
        for key, query in queries.items():
            try:
                results[key] = get_web_context(query, max_results=4, search_depth="basic")
            except Exception as e:
                logger.warning(f" [Agent D] 联网搜索失败({key}): {e}")
                results[key] = ""
        return {
            "history_context": self._compress_web_context(
                results.get("historical_pattern", ""), "历史同期"
            ),
            "future_context": "\n\n".join(
                [
                    self._compress_web_context(results.get("future_schedule", ""), "未来节点"),
                    self._compress_web_context(results.get("current_axis", ""), "主线延伸"),
                ]
            ).strip(),
            "evidence_sources": [
                queries["historical_pattern"],
                queries["future_schedule"],
                queries["current_axis"],
            ],
        }

    def run(
        self,
        current_opinion_analysis: str,
        audit_risks: str,
        history_context: str = "",
        future_context: str = "",
        forecast_range: str = "1m",
        time_period_desc: Optional[str] = None,
        category: str = "综合",
        improvement_hint: str = "",
    ) -> Dict[str, Any]:
        target_period = self._compute_period(forecast_range, category, time_period_desc)
        logger.info(f" [Agent D] 启动趋势预测: {target_period}")

        evidence_sources: List[str] = []
        if not history_context or not future_context:
            web_payload = self._collect_online_contexts(
                category=category,
                forecast_range=forecast_range,
                current_opinion_analysis=current_opinion_analysis,
            )
            history_context = history_context or web_payload["history_context"]
            future_context = future_context or web_payload["future_context"]
            evidence_sources = web_payload["evidence_sources"]

        prompt = ChatPromptTemplate.from_template(AGENT_D_FORECAST_TEMPLATE)
        chain = prompt | self.forecast_llm.with_structured_output(TrendForecastReport)

        try:
            report_obj = chain.invoke(
                {
                    "forecast_range": forecast_range,
                    "target_period": target_period,
                    "current_opinion_analysis": current_opinion_analysis,
                    "audit_risks": audit_risks,
                    "history_context": history_context,
                    "future_context": future_context,
                    "improvement_hint": improvement_hint or "",
                }
            )
            report = report_obj.model_dump() if hasattr(report_obj, "model_dump") else dict(report_obj)
            report["_context_history"] = history_context
            report["_context_future"] = future_context
            report["target_period"] = report.get("target_period") or target_period
            if evidence_sources and not report.get("evidence_sources"):
                report["evidence_sources"] = evidence_sources
            return report
        except Exception as e:
            logger.error(f" [Agent D] 预测生成失败: {e}")
            return {
                "target_period": target_period,
                "evidence_sources": evidence_sources,
                "topics": [],
                "_error": str(e),
            }


agent_forecast = AgentForecast()

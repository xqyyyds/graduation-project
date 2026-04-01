import datetime
from typing import Dict, Any, Optional
from dateutil.relativedelta import relativedelta

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from app.core.config import settings
from app.core.logger import logger
from app.services.utils import get_web_context

#  引入重构后的 Schema 和 Prompt
from app.core.schemas import TrendForecastReport
from app.core.prompts import AGENT_D_FORECAST_TEMPLATE


class AgentForecast:
    """
    Agent D: 舆情战略预警师 (Ultimate Edition)
    职责：结合【全网专家智慧】+【历史规律】+【当下情绪】，进行大师级风险推演。
    """

    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            openai_api_key=settings.ZHIPU_API_KEY,
            openai_api_base=settings.LLM_BASE_URL,
            temperature=0.6,  # 保持灵活性，让思维链能发散
            request_timeout=180,  #  增加超时时间
            max_retries=3,
        )

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

        logger.info(f" [Agent D] 启动{category}领域研判 (Master CoT Mode)...")

        # 1. 时间计算逻辑 (保留用于计算 target_period，但 target_year/month 变量本身不再传给 Prompt)
        now = datetime.datetime.now()
        range_map = {
            "1w": ("一周", 7, "days"),
            "2w": ("半个月", 14, "days"),
            "1m": ("一个月", 1, "months"),
            "2m": ("两个月", 2, "months"),
        }
        range_desc, delta_val, delta_unit = range_map.get(
            forecast_range, ("一个月", 1, "months")
        )

        if delta_unit == "days":
            target_date = now + datetime.timedelta(days=delta_val)
        else:
            target_date = now + relativedelta(months=delta_val)

        # 构造目标时间描述 (target_period)
        # 优先使用传入的精准描述 (time_period_desc)，否则兜底生成
        if time_period_desc:
            base_period = time_period_desc
        else:
            base_period = f"{now.strftime('%Y年%m月%d日')}起未来{range_desc}"

        # 处理领域前缀
        if category and category not in ["综合", "其他", "全部"]:
            final_target_period = f"【{category}领域】{base_period}"
            final_future_context = f"以下是{category}领域的全网情报：\n{future_context}"
        else:
            final_target_period = base_period
            final_future_context = future_context

        logger.info(f" [Agent D] 研判目标: {final_target_period}")

        # 2. 构造 Prompt 链
        structured_llm = self.llm.with_structured_output(TrendForecastReport)
        prompt = ChatPromptTemplate.from_template(AGENT_D_FORECAST_TEMPLATE)
        chain = prompt | structured_llm

        try:
            # 3. 执行推理
            # 【修改】移除了 target_year 和 target_month，与 Prompt 保持一致
            report_obj = chain.invoke(
                {
                    "forecast_range": range_desc,
                    "target_period": final_target_period,
                    "current_opinion_analysis": current_opinion_analysis,
                    "audit_risks": audit_risks,
                    "history_context": history_context,
                    "future_context": final_future_context,
                    "improvement_hint": improvement_hint or "",
                }
            )

            logger.info(" [Agent D] 深度战略研判完成 (JSON Generated)。")

            report = (
                report_obj.model_dump()
                if hasattr(report_obj, "model_dump")
                else dict(report_obj)
            )

            # 挂载上下文 (供 Agent E 报告生成使用)
            report["_context_history"] = history_context
            report["_context_future"] = future_context
            report["_forecast_range"] = range_desc

            # 确保 target_period 字段有值（LLM 可能返回空）
            if not report.get("target_period"):
                report["target_period"] = final_target_period

            return report

        except Exception as e:
            logger.error(f" [Agent D] 结构化解析失败: {e}")
            return {
                "target_period": final_target_period,
                "topics": [],
            }


# 单例导出
agent_forecast = AgentForecast()

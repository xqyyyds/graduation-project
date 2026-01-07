import datetime
from dateutil.relativedelta import relativedelta
from typing import Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

# from langchain_core.output_parsers import JsonOutputParser # 已移除

from app.core.config import settings
from app.core.logger import logger
from app.agents.tools import get_web_context

# 🔥 引入重构后的 Schema 和 Prompt
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
            request_timeout=180,  # 🔥 增加超时时间
            max_retries=3,
        )
        # 移除旧的 parser
        # self.parser = JsonOutputParser(pydantic_object=TrendForecastReport)

    def run(
        self,
        current_opinion_analysis: str,
        audit_risks: str,
        history_context: str = "",
        future_context: str = "",
        forecast_range: str = "1m",
    ) -> Dict[str, Any]:
        logger.info("🔮 [Agent D] 启动全域时空研判系统 (Master CoT Mode)...")

        # 1. 根据预测范围锁定时间坐标
        now = datetime.datetime.now()

        # 解析预测范围
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

        target_year = target_date.year
        target_month = target_date.month

        # 构造目标时间描述
        target_period = f"{now.strftime('%Y年%m月%d日')}起未来{range_desc}"

        logger.info(f"📅 [Agent D] 研判目标: {target_period}")

        # 2. 构造 Prompt 链
        # 🔥 升级：使用 with_structured_output，不再需要 format_instructions
        structured_llm = self.llm.with_structured_output(TrendForecastReport)
        prompt = ChatPromptTemplate.from_template(AGENT_D_FORECAST_TEMPLATE)

        chain = prompt | structured_llm

        try:
            # 3. 执行推理
            report_obj = chain.invoke(
                {
                    "target_year": target_year,
                    "target_month": target_month,
                    "forecast_range": range_desc,
                    "target_period": target_period,
                    "current_opinion_analysis": current_opinion_analysis,
                    "audit_risks": audit_risks,
                    "history_context": history_context,
                    "future_context": future_context,
                }
            )

            logger.info("✅ [Agent D] 深度战略研判完成 (JSON Generated)。")

            # 转换为字典
            report = (
                report_obj.model_dump()
                if hasattr(report_obj, "model_dump")
                else dict(report_obj)
            )

            # 🔥 将上下文挂载到返回结果中，供报告生成使用
            report["_context_history"] = history_context
            report["_context_future"] = future_context
            report["_forecast_range"] = range_desc

            return report

        except Exception as e:
            logger.error(f"❌ [Agent D] 结构化解析失败: {e}")
            # 降级返回，保证流程不断 (适配新 Schema)
            return {
                "target_month": target_period,
                "topics": [],  # 新 Schema 只有 topics
            }


# 单例导出
agent_forecast = AgentForecast()

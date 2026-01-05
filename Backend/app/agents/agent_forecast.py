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
        )
        # 移除旧的 parser
        # self.parser = JsonOutputParser(pydantic_object=TrendForecastReport)

    def run(
        self,
        current_opinion_analysis: str,
        audit_risks: str,
        history_context: str = "",
        future_context: str = "",
    ) -> Dict[str, Any]:
        logger.info("🔮 [Agent D] 启动全域时空研判系统 (Master CoT Mode)...")

        # 1. 锁定时间坐标 (下个月)
        now = datetime.datetime.now()
        next_month_date = now + relativedelta(months=1)
        target_year = next_month_date.year
        target_month = next_month_date.month

        logger.info(f"📅 [Agent D] 研判目标: {target_year}年{target_month}月")

        # 2. 构造 Prompt 链
        # 🔥 升级：使用 with_structured_output，不再需要 format_instructions
        structured_llm = self.llm.with_structured_output(TrendForecastReport)
        prompt = ChatPromptTemplate.from_template(AGENT_D_FORECAST_TEMPLATE)

        chain = prompt | structured_llm

        # 修正：不再手动混合，而是直接传给 Prompt 中对应的插槽
        # combined_current_analysis = ... (已移除)

        try:
            # 3. 执行推理
            report_obj = chain.invoke(
                {
                    "target_year": target_year,
                    "target_month": target_month,
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

            return report

        except Exception as e:
            logger.error(f"❌ [Agent D] 结构化解析失败: {e}")
            # 降级返回，保证流程不断 (适配新 Schema)
            return {
                "target_month": f"{target_year}年{target_month}月",
                "topics": [],  # 新 Schema 只有 topics
            }


# 单例导出
agent_forecast = AgentForecast()

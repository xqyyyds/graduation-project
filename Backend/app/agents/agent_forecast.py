import datetime
from dateutil.relativedelta import relativedelta
from typing import Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from app.core.config import settings
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
        # 绑定 Pydantic 解析器
        self.parser = JsonOutputParser(pydantic_object=TrendForecastReport)

    def run(self, current_opinion_analysis: str, audit_risks: str) -> Dict[str, Any]:
        print("🔮 [Agent D] 启动全域时空研判系统 (Master CoT Mode)...")

        # 1. 锁定时间坐标 (下个月)
        now = datetime.datetime.now()
        next_month_date = now + relativedelta(months=1)
        target_year = next_month_date.year
        target_month = next_month_date.month

        print(f"📅 [Agent D] 研判目标: {target_year}年{target_month}月")

        # 2. 构建“高维”搜索指令
        # 搜历史铁律
        query_history = (
            f"历年{target_month}月 中国网络舆情 高发领域 复盘 "
            f"历年{target_month}月 社会矛盾 典型舆情案例"
        )

        # 搜未来前瞻 (专家预测 + 宏观变量)
        query_future = (
            f"{target_year}年{target_month}月 中国 社会舆情风险点 专家预测 "
            f"{target_year}年{target_month}月 舆情研判 重点关注领域 "
            f"{target_year}年{target_month}月 政策施行 经济形势 民生痛点前瞻"
        )

        print(f"🌍 [Agent D] 正在调取全网情报库...")
        history_context = get_web_context(query_history)
        future_context = get_web_context(query_future)

        # 3. 构造 Prompt 链
        # 将我们精心设计的 Prompt 与解析器指令结合
        prompt = ChatPromptTemplate.from_template(AGENT_D_FORECAST_TEMPLATE).partial(
            format_instructions=self.parser.get_format_instructions()
        )

        chain = prompt | self.llm | self.parser

        # 混合 Agent B 和 Agent C 的情报作为底色
        combined_current_analysis = (
            f"{current_opinion_analysis}\n\n【补充：当前合规风险高发点】\n{audit_risks}"
        )

        try:
            # 4. 执行推理
            report = chain.invoke(
                {
                    "target_year": target_year,
                    "target_month": target_month,
                    "current_opinion_analysis": combined_current_analysis,
                    "history_context": history_context,
                    "future_context": future_context,
                }
            )

            print("✅ [Agent D] 深度战略研判完成 (JSON Generated)。")
            return report

        except Exception as e:
            print(f"❌ [Agent D] 结构化解析失败: {e}")
            # 降级返回，保证流程不断
            return {
                "target_month": f"{target_year}年{target_month}月",
                "overall_judgment": "（数据解析异常，请查看日志）",
                "top_risks": [],
                "strategic_advice": [],
            }


# 单例导出
agent_forecast = AgentForecast()

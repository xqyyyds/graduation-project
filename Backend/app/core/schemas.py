# app/core/schemas.py
from typing import List, Optional
from pydantic import BaseModel, Field


# =====================================================
# 1. ETL 阶段 (数据清洗与归并)
# =====================================================


class MergedEvent(BaseModel):
    """定义单个归并后的事件结构"""

    event_name: str = Field(
        ..., description="归并后的事件名称，要求简短、客观、标准，不带#号"
    )
    keywords: List[str] = Field(..., description="属于该事件的所有原始热搜词列表")
    reasoning: str = Field(
        ..., description="简要说明为什么将这些词归为一类，例如'均讨论小洛熙事件'"
    )


class EventList(BaseModel):
    """定义最终输出的列表容器"""

    events: List[MergedEvent] = Field(description="归并后的事件列表")


# =====================================================
# 2. Agent B: 舆情观点分析 (Map 阶段)
# =====================================================


class OpinionCluster(BaseModel):
    """
    观点簇：将相似的评论归为一类
    """

    viewpoint: str = Field(description="该类人群的核心观点 (例如: '认为学校处置过慢')")
    emotion: str = Field(description="该观点的对应情绪 (例如: '不满/愤怒')")
    estimated_ratio: str = Field(
        description="该观点在评论区的预估占比 (例如: '约60%', '少数')"
    )


class PostOpinionSummary(BaseModel):
    """
    Map阶段产物：单贴深度扫描
    """

    opinion_clusters: List[OpinionCluster] = Field(
        description="提取出的3-5个主要观点阵营及其占比"
    )
    conflict_analysis: str = Field(
        description="评论区是否存在骂战或对立？简要描述冲突点。"
    )


# =====================================================
# 3. Agent B: 舆情观点分析 (Reduce 阶段)
# =====================================================


class EventAnalysisReport(BaseModel):
    """
    Reduce阶段产物：事件深度报告
    """

    # 1. 事实层
    event_overview: str = Field(
        description="【事件概述】客观还原时间、地点、经过、官方通报结果。"
    )

    # 2. 观点层
    public_opinions: List[str] = Field(
        description="【舆论观点】分点列出(如: 一是...; 二是...)，需体现不同阵营的声音。"
    )

    # 3. 深度层
    depth_analysis: str = Field(
        description="【舆情分析】深度的社会归因 (如: 留学生管理体制、资源公平焦虑等)。"
    )


# =====================================================
# 4. Agent C: 合规审查 (单条模式 & Batch 模式)
# =====================================================


class AuditAnalysis(BaseModel):
    """Agent C 的第一阶段思考结果：违规定性 (单条模式用)"""

    is_violation: bool = Field(description="初步判断是否违规，True为违规，False为正常")
    category: str = Field(
        description="违规大类，必须从预定义的规则库标签中选择。若无违规，填 '无'。"
    )
    risk_level: str = Field(description="预估风险等级: High/Medium/Low/None")
    reasoning: str = Field(description="简短的判断依据")


class ComplianceResult(BaseModel):
    """Agent C 的最终输出结构 (单条模式用)"""

    verdict: str = Field(description="最终结论 (✅ 通过 / ❌ 违规)")
    analysis: AuditAnalysis = Field(description="详细分析对象")
    report: str = Field(description="生成的简短审核报告")
    evidence: Optional[str] = Field(None, description="违规内容的原文摘录")


# 🔥 [新增] Batch 模式专用：单个违规项详情
class ViolatedItem(BaseModel):
    """
    批量审查中的单个违规记录
    """

    index: int = Field(
        ...,
        description="违规内容在输入列表中的序号 (主贴填 -1，评论填对应的序号 0,1,2...)",
    )
    content_snippet: str = Field(..., description="违规内容的原文片段 (用于存证)")
    category: str = Field(..., description="违规类别 (如: 政治敏感, 色情, 暴恐, 谩骂)")
    risk_level: str = Field(..., description="风险等级 (High/Medium/Low)")
    reasoning: str = Field(..., description="判定违规的具体理由")


# 🔥 [新增] Batch 模式专用：整体审查结果
class BatchComplianceResult(BaseModel):
    """
    Agent C 的最终输出：批量审查结果容器
    """

    is_post_violated: bool = Field(..., description="主贴本身是否违规")
    violated_comments: List[ViolatedItem] = Field(
        ..., description="违规的评论列表，若无违规，返回空列表"
    )
    overall_risk_level: str = Field(
        ..., description="当前这组内容的整体风险等级 (High/Medium/Low)"
    )


# =====================================================
# 4.1 Agent C: 合规审查 (Batch + RAG 证据链)
# =====================================================


class LawReference(BaseModel):
    """向量库命中的法规/公约条款引用"""

    category: str = Field(..., description="法规/公约的大类标签（用于溯源与过滤）")
    article: str = Field(..., description="条款编号/章节（如：第九条）")
    risk_level: str = Field(..., description="规则库给出的风险等级（High/Medium/Low）")
    rule: str = Field(..., description="命中条款的原文或摘要（来自向量库文档）")


class ComplianceEvidenceReport(BaseModel):
    """对一条帖子（含评论列表）的合规判决书/证据链（用于回写数据库与报告引用）"""

    overall_risk_level: str = Field(..., description="综合风险等级（High/Medium/Low）")
    violated_categories: List[str] = Field(..., description="本次命中的违规标签列表")
    cited_laws: List[LawReference] = Field(
        ..., description="命中的法规/公约条款（来自 Chroma 检索）"
    )
    evidence_chain: List[str] = Field(
        ..., description="证据链（要点列表，引用具体违规片段/现象）"
    )
    reasoning: str = Field(
        ..., description="违规原因分析（合并解释：为何构成违规、危害是什么）"
    )


# =====================================================
# 5. Agent D: 舆情战略预警师
# =====================================================


class RiskFocusArea(BaseModel):
    """单项风险预测"""

    domain: str = Field(
        ..., description="风险领域名称 (如: 文旅消费、公共安全、基层治理)"
    )
    deduction_logic: str = Field(
        ...,
        description="【风险成因推演】必须体现'当下情绪'与'未来节点'的叠加效应。",
    )
    warning_keywords: List[str] = Field(
        ...,
        description="预测可能上热搜的3-5个具体敏感词",
    )


class TrendForecastReport(BaseModel):
    """Agent D 的最终产出"""

    target_month: str = Field(..., description="研判的目标月份 (如: '2026年1月')")

    overall_judgment: str = Field(
        ...,
        description="【总体研判】用一段极具洞察力的话，概括下个月的舆情压力等级与核心矛盾。",
    )

    top_risks: List[RiskFocusArea] = Field(
        ..., description="【重点风险前瞻】列出 3 个最可能爆发的风险领域。"
    )

    strategic_advice: List[str] = Field(
        ...,
        description="【决策锦囊】3条高维度的治理建议。",
    )


# =====================================================
# 6. Agent E: 报告总编
# =====================================================


class PrefaceSection(BaseModel):
    """前言部分的完整结构"""

    # 🔥 [补全] 之前漏掉的 report_period，生成报告时必须用到
    report_period: str = Field(
        ..., description="报告覆盖及研判周期 (如: '2025年10月回顾及11月前瞻')"
    )

    macro_phenomenon: str = Field(
        ...,
        description="【宏观现象】总结这段时间舆情的总体特点（如：高度碎片化、信任危机频发等）。",
    )

    compliance_analysis: str = Field(
        ...,
        description="【底线审视】概括违规内容的特征。是谣言为主？还是非理性宣泄？",
    )

    future_abstraction: str = Field(
        ...,
        description="【趋势承接】结合当下与历史，对未来做一个概括性预判。",
    )

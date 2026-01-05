# app/core/schemas.py
from typing import List, Optional
from pydantic import BaseModel, Field


# =====================================================
# 1. ETL 阶段 (数据清洗与归并)
# =====================================================


class MergedEvent(BaseModel):
    """定义单个归并后的事件结构"""

    event_name: str = Field(
        ...,
        description="归并后的标准事件名称。必须是客观中立的新闻标题风格（主谓宾结构），严禁包含情绪化词汇、饭圈用语及'#'符号。",
    )
    keywords: List[str] = Field(
        ...,
        description="必须严格从输入的【待处理列表】中复制原始词条，严禁修改任何字符（包括空格、标点）。",
    )
    reasoning: str = Field(
        ...,
        description="归并理由。简述这些词条共同指向的核心实体或事件锚点（例如：'均涉及某明星的某具体争议事件'）。",
    )


class EventList(BaseModel):
    """定义最终输出的列表容器"""

    events: List[MergedEvent] = Field(
        description="归并后的独立事件列表。确保输入的所有热搜词都被包含在内，无遗漏。"
    )


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
        description="提取出的主要观点阵营（1-5个，视实际舆论分歧程度而定）及其占比"
    )
    conflict_analysis: str = Field(
        description="分析评论区的舆论对立程度。若存在激烈争论或群体冲突，请指出核心矛盾点；若氛围和谐，填'无'。"
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
        description="【事件概述】必须以新闻调查记者的笔触，高密度还原核心事实（关键时间节点、冲突爆发点、官方通报）。"
    )

    # 2. 观点层
    public_opinions: List[str] = Field(
        description="【舆论观点】必须分层级梳理：1.主流声浪 2.次生质疑 3.深层情绪 4.对立博弈。每一点作为列表的一项。"
    )

    # 3. 深度层
    depth_analysis: str = Field(
        description="【舆情分析】必须进行社会学归因。覆盖：社会痛点映射、群体心理画像、制度与治理反思。"
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
    quote: str = Field(
        ...,
        description="【精准摘录】违规的核心词汇或句子（如：'zf'、'杀'、'造谣内容'）。",
    )
    category: str = Field(
        ...,
        description="违规类别，必须严格从提供的【可选违规大类】列表中选择，不得自造。",
    )
    reasoning: str = Field(
        ...,
        description="判定理由。格式必须为 '违规标签: 具体原因' (例如 '时政有害-国家安全: 涉及...')。",
    )


# 🔥 [新增] Batch 模式专用：整体审查结果
class BatchComplianceResult(BaseModel):
    """
    Agent C 的最终输出：批量审查结果容器
    """

    is_post_violated: bool = Field(..., description="主贴本身是否违规")
    violated_comments: List[ViolatedItem] = Field(
        ..., description="违规的评论列表。仅包含确认为违规的项。"
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
    disposal_suggestion: str = Field(
        ..., description="处置建议（如：建议删除评论、建议封禁账号、建议上报网信办等）"
    )


# =====================================================
# 5. Agent D: 舆情战略预警师
# =====================================================


class ForecastPoint(BaseModel):
    """单个风险点或建议点"""

    subtitle: str = Field(
        ...,
        description="子标题，格式如：'（一）跨区域标准不一易引发争议' 或 '（二）警惕政策调整忽视从业者权益'",
    )
    content: str = Field(
        ..., description="详细内容。包含风险描述、案例引用（如有）及具体的防范建议。"
    )


class ForecastTopic(BaseModel):
    """预测报告的一个核心议题板块"""

    topic_name: str = Field(
        ...,
        description="议题标题，采用动宾结构或对仗句式，如：'如何打好烟花爆竹管控攻坚战，考验政府治理能力' 或 '推动矛盾纠纷化解，维护基层社会和谐稳定'",
    )
    background: str = Field(
        ...,
        description="背景导语。简述该议题的宏观背景、时间节点特征（如'元旦春节临近...'）。",
    )
    points: List[ForecastPoint] = Field(
        ..., description="该议题下的具体风险点列表（通常3-5点）。"
    )


class TrendForecastReport(BaseModel):
    """Agent D 的最终产出 (Government Report Style)"""

    target_month: str = Field(..., description="研判的目标月份 (如: '2026年1月')")

    topics: List[ForecastTopic] = Field(
        ...,
        description="【核心议题预测】列出 3-4 个下个月最需要关注的舆情风险议题。每个议题包含背景和若干具体风险点。",
    )


# =====================================================
# 6. Agent E: 报告总编
# =====================================================


class PrefaceSection(BaseModel):
    """前言部分的完整结构"""

    report_period: str = Field(
        ..., description="报告覆盖及研判周期 (如: '2025年10月回顾及11月前瞻')"
    )

    overview: str = Field(
        ...,
        description="【开篇综述】简述时间跨度、涉及范围及核心议题概览（如：'从10月底至11月，全国各地高校的相关舆情频繁出现...'）。",
    )

    characteristics: List[str] = Field(
        ...,
        description="【特征分析】提炼三个核心特征（其一、其二、其三）。每点必须包含：现象描述 + 深度归因（如：'敏感性显著提升'、'议题碎片化'、'负面标签固化'）。",
    )

    compliance_perspective: str = Field(
        ...,
        description="【违规透视】基于合规数据，分析舆论场的非理性程度（如：谣言传播、情绪宣泄、群体极化）。",
    )

    trend_connection: str = Field(
        ...,
        description="【时空承接】结合当下情绪与历史规律，对未来做一个结论性概括，并引导读者阅读正文。",
    )

    conclusion: str = Field(
        ...,
        description="【结语】总体研判与宏观治理建议（如：'总体来看，当下舆情环境的脆弱性呈现强化趋势...'）。",
    )

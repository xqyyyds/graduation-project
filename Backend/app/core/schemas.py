# app/core/schemas.py
from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field, conlist


# =====================================================
# 1. ETL 阶段 (数据清洗与归并)
# =====================================================


class MergedEvent(BaseModel):
    """定义单个归并后的事件结构"""

    event_name: str = Field(
        ...,
        description="归并后的标准事件名称。必须是具体的新闻事件（如'某地发生某事'）。【绝对禁止】使用'独立事件'、'其他'、'社会新闻'、'新年及春节'等垃圾桶式命名。如有疑虑，直接使用关键词中最核心的一个作为名称。",
    )
    keywords: List[str] = Field(
        ...,
        description="必须严格从输入的【待处理列表】中复制原始词条，不得修改任何字符，不得遗漏。",
    )
    reasoning: str = Field(
        ...,
        description="归并理由。必须基于5W1H（时间、地点、人物、起因、经过、结果）证明这些词条描述的是同一具体事件。如果仅仅是主语相同（如都是女子）但事情不同，请明确标注'无法合并'并要求拆分。",
    )


class EventList(BaseModel):
    """定义最终输出的列表容器"""

    events: List[MergedEvent] = Field(
        description="归并后的独立事件列表。确保输入的所有热搜词都被包含在内，无遗漏。"
    )


# =====================================================
# 1.5 ETL 二次审核 (聚类质量检查)
# =====================================================


class EventReviewItem(BaseModel):
    """单个事件的审核结果"""

    original_event_name: str = Field(..., description="原始事件名称（来自第一次聚类）")
    is_valid: bool = Field(
        ...,
        description="该聚类是否有效。判定标准：是否存在'垃圾桶命名'？是否存在'强行拼凑'？只有100%确信是同一事件才选True。",
    )
    issue_type: Optional[str] = Field(
        None,
        description="问题类型（仅当 is_valid=False 时填写）。可选值：'垃圾桶命名'（如独立事件）、'宽泛聚合'（如日本事件）、'同名异事'（主语同行为不同）、'时间线混淆'、'其他'",
    )
    corrected_events: Optional[List[MergedEvent]] = Field(
        None,
        description="修正后的事件列表。将错误聚类彻底打散，拆分为多个独立事件。",
    )
    review_reason: str = Field(
        ...,
        description="审核理由。指出违反了哪条红线（如：'违背5W1H原则'，'属于垃圾桶分类'等）。",
    )


class EventReviewResult(BaseModel):
    """二次审核的完整结果"""

    reviews: List[EventReviewItem] = Field(description="对每个事件的审核结果列表")


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
        description="【事件概述】必须不少于150字/8句话。以新闻调查记者的笔触，高密度还原核心事实，必须包含：关键时间节点、冲突爆发点、官方处置动作、媒体定性引用。若时间不确定必须写'时间待核实'，严禁编造年份日期。【重要：严禁使用任何Emoji表情符号，保持严肃专业的报告风格】"
    )

    # 2. 观点层
    public_opinions: List[str] = Field(
        description="【舆论观点】必须至少4项，每项不少于50字/2句话。分层级梳理：1.主流声浪（占优势的网民态度）2.次生质疑（对处置过程的延伸批判）3.深层情绪（隐藏的群体心理）4.对立博弈（正反双方逻辑交锋）。必须基于舆情切片中的观点分布/评论摘录进行概括，不得捏造。【重要：严禁使用任何Emoji表情符号，使用规范的书面语】"
    )

    # 3. 深度层（深度点评，禁止复述事件概述）
    depth_analysis: str = Field(
        description="【舆情分析-深度点评】必须不少于200字/3个自然段。🚨严禁复述事件概述中的内容，严禁描述事件经过/时间线。必须是独立观点输出：(1)对事件本质的判断(2)社会意义与警示价值(3)对涉事各方的评价与反思(4)社会学归因分析。风格要像社论评论，而非新闻报道。【重要：严禁使用任何Emoji表情符号，保持深度与严肃性】"
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
        description="判定理由。必须只基于文本本身，逐字对齐到 quote 的具体词句，禁止使用潜在影响/动机推断（如'可能引发'）。仅在恶毒辱骂/明确仇恨歧视/明确教唆违法暴力等高阈值情形下输出。",
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
        ...,
        description="违规原因分析。只基于文本本身说明为何构成违规，禁止写潜在影响/间接后果（如'可能造成'）。文字应可直接对应到 evidence_chain 与 cited_laws。",
    )
    disposal_suggestion: str = Field(
        ..., description="处置建议（如：建议删除评论、建议封禁账号、建议上报网信办等）"
    )


# =====================================================
# Agent D: 舆情战略预警师 (Schema Definition)
# =====================================================


class ForecastPoint(BaseModel):
    """单个风险点详情"""

    subtitle: str = Field(
        ...,
        description="子标题，高度概括该风险点。格式如：'（一）跨区域执法标准不一易引发舆论争议'。严禁使用Emoji。",
    )
    content: str = Field(
        ...,
        min_length=80,
        description="【深度研判内容】必须包含三个要素：1.触发场景（未来什么具体事件或时间节点会触发此风险）；2.演化路径（舆情将如何从点扩散到面）；3.落地建议（具体的防范或应对措施）。禁止空泛的废话。",
    )
    likelihood: Literal["高", "中", "低"] = Field(
        ..., description="该风险在预测周期内发生的概率评估。"
    )
    evidence_basis: List[str] = Field(
        ...,
        description="【预测依据】必须列出支撑该预测的逻辑来源。例如：['历史规律：往年3月均为高校心理危机高发期', '未来情报：预计XX新规将于下月实施']。禁止仅引用'当前舆论情绪'。",
        min_length=1,
    )


class ForecastTopic(BaseModel):
    """预测报告的一个核心议题板块"""

    topic_name: str = Field(
        ...,
        description="议题标题，采用动宾结构或对仗句式，风格严肃。如：'如何打好...攻坚战' 或 '警惕...风险叠加'。",
    )
    background: str = Field(
        ...,
        description="【未来视角背景】简述下个周期（研判目标月）的特殊性（如：适逢开学季/政策窗口期/敏感纪念日/特定季节特征）。说明为何在该时间节点此议题会爆发。",
        min_length=60,
    )
    points: List[ForecastPoint] = Field(
        ...,
        min_length=3,
        max_length=5,
        description="该议题下的具体风险演化点（3-5个）。",
    )


class TrendForecastReport(BaseModel):
    """Agent D 的最终产出 (Government Report Style)"""

    target_period: str = Field(..., description="研判的周期与领域范围描述")

    evidence_sources: List[str] = Field(
        ...,
        description="【参考文献/宏观依据】列出推演时参考的宏观依据来源，如：'教育部历年工作要点'、'国家统计局季节性数据'、'XX行业发展规划'等。",
    )

    topics: List[ForecastTopic] = Field(
        ...,
        min_length=3,
        max_length=5,
        description="【核心议题预测】列出 3-5 个下个月最需要关注的舆情风险议题。要求各议题维度互不重复（正交）。",
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
        description="【开篇综述】必须不少于200字/2个自然段。概括本周期舆情的时间跨度、涉及领域（如社会/高校/生活/综合等提示词传递的领域）、总体态势，并提炼热点领域分布与主导情绪结构。严禁空泛套话，必须结合素材中的具体事件类型进行归纳。风格严肃，严禁使用Emoji。",
    )

    characteristics: List[str] = Field(
        ...,
        description="【特征分析】提炼3个核心特征（其一、其二、其三）。每个特征必须不少于80字/5句话，必须同时包含：(1)现象层：从素材中抽象出的共性规律；(2)机制层：用社会学/传播学概念解释成因；(3)影响层：该特征如何影响公众情绪或治理成本。禁止写成固定的'敏感性/碎片化/传播速度'三件套。风格严肃，严禁使用Emoji。",
    )

    compliance_perspective: str = Field(
        ...,
        description="【违规透视】必须不少于100字/6句话。基于合规数据分析舆论场的非理性程度，必须给出2-3条典型风险形态的概括性例子（可基于素材转述），指明主要违规类型集中在哪些领域。风格严肃，严禁使用Emoji。",
    )

    trend_connection: str = Field(
        ...,
        description="【时空承接】必须不少于80字/5句话。结合趋势预测指出下阶段可能与特定议题产生共振的风险点，必须包含引导语'未来风险的详细推演，请见报告正文'。风格严肃，严禁使用Emoji。",
    )

    conclusion: str = Field(
        ...,
        description="【结语】必须不少于100字/6句话。总结当下核心风险（如脆弱性、情绪驱动性），并给出至少3条可落地的宏观治理建议（如前置预警、澄清机制、平台治理、舆情监测系统完善等）。风格严肃，严禁使用Emoji。",
    )


# =====================================================
# 7. 事件去重判断 (Agent B 深度分析前)
# =====================================================


class EventDuplicateCheck(BaseModel):
    """判断两个热搜是否指向同一新闻事件"""

    is_same_event: bool = Field(
        ...,
        description="是否为同一新闻事件。只有当两个热搜词确定指向同一具体事件（同一时间、同一地点、同一主体、同一事件链）时才为 True。",
    )
    reasoning: str = Field(
        ...,
        description="判断理由。简要说明为什么是/不是同一事件。如果是同一事件，需说明它们的关联（如：都是关于小洛熙案件的不同角度报道）。",
    )

# app/core/schemas.py
from __future__ import annotations

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field


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
    trigger_summary: str = Field(
        default="",
        description="该帖在本期舆情中的触发点：什么内容最容易点燃讨论、引发转发或集中跟评。",
    )
    propagation_hint: str = Field(
        default="",
        description="该帖评论区主要把议题往哪个方向推进（如从价格焦虑滑向质量质疑或维权成本讨论）。",
    )


# =====================================================
# 3. Agent B: 舆情观点分析 (Reduce 阶段)
# =====================================================


class EventAnalysisReport(BaseModel):
    """
    Reduce阶段产物：事件深度报告
    """

    editorial_title: str = Field(
        default="",
        description="更有传播力和成品感的深读标题，不是简单复述热搜词。标题可以有钩子，但不能低俗、夸张或标题党式空喊。",
    )
    one_line_verdict: str = Field(
        default="",
        description="一句话判断该事件的本质矛盾或舆情主轴。必须先下判断，再展开，不得写成空泛导语。",
    )

    # 1. 事实层
    event_overview: str = Field(
        description="【事件概述】输出为1-2段连贯文字，按“触发点 -> 放大过程 -> 争议外溢 -> 周期末状态”的顺序还原事件推进。必须以官方事实与时间推进线为主干，评论区内容仅可补充公众反应，不得替代事实进展。若输入含明确时间点（如3月24日/3月25日），应自然写入叙事；若时间线混乱、冲突或缺失，需改按“事件主矛盾 -> 争议升级 -> 当前悬而未决点”自组织成合理段落，不得硬凑伪时间线。必须写成自然叙事，不要使用“事件概况：”开头，不要写成“研判周期：”“核心事实：”“关键节点与处置：”“讨论点包括：”等标签化模板句。若时间不确定必须写'时间待核实/未见权威通报'，严禁编造年份日期。"
    )

    # 2. 观点层
    public_opinions: List[str] = Field(
        description="【舆论观点画像】固定输出4条，按顺序对应：主流声浪、次生质疑、深层情绪、对立博弈。四条必须分别以“主流声浪：”“次生质疑：”“深层情绪：”“对立博弈：”开头。每条都要体现谁在这样想、为什么这样想、这种声音会把讨论推向哪里；若对立博弈不显著，第4条需明确写出“对立博弈不显著”。"
    )

    # 3. 深度层（深度点评，禁止复述事件概述）
    depth_analysis: str = Field(
        description="【深度研判】写成2段连贯文字。第一段回答本期被引爆的关键机制，第二段回答其折射出的更大治理/信任/传播结构问题。严禁复述事件概述，不能写成模板评论或要点清单；不得重复具体时间点、传播顺序、截图链条或回应顺序等事实性叙述。"
    )
    key_quotes: List[str] = Field(
        default_factory=list,
        description="最能代表舆论气氛的关键引述，2-5条即可。要保留现场感，避免无信息量的短句。",
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

    verdict: str = Field(description="最终结论 ( 通过 /  违规)")
    analysis: AuditAnalysis = Field(description="详细分析对象")
    report: str = Field(description="生成的简短审核报告")
    evidence: Optional[str] = Field(None, description="违规内容的原文摘录")


#  [新增] Batch 模式专用：单个违规项详情
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


#  [新增] Batch 模式专用：整体审查结果
class BatchComplianceResult(BaseModel):
    """
    Agent C 的最终输出：批量审查结果容器
    """

    is_post_violated: bool = Field(..., description="主贴本身是否违规")
    violated_comments: List[ViolatedItem] = Field(
        ..., description="违规的评论列表。仅包含确认为违规的项。"
    )


class ViolationCaseStage1(BaseModel):
    """第一阶段审核判定结果（仅模型判定字段）"""

    index: int = Field(..., description="主贴为 -1，评论为对应序号。")
    quote: str = Field(..., description="用于判定的关键摘录。")
    category: str = Field(
        ...,
        description="第一阶段判定类别；必须来自白名单。必须先做语境与对象识别：若仅为公共事件讨论、对涉事方/品牌/平台/机构/带货者/公众人物的追责批评、消费吐槽、短句情绪表达或对象不明表达，应输出空字符串。",
    )
    reasoning: str = Field(
        ...,
        description="第一阶段判定依据。需按“语境→对象→行为强度→处罚阈值”说明结论；不得把负面评价、愤怒语气、道德谴责或平台质疑直接等同于造谣/网暴。若判定不违规，应优先采用固定执法结论句式并说明未达到社区处罚阈值。",
    )
    is_violation: bool = Field(
        ...,
        description="是否判定为违规。仅当存在明确对象、明确越线行为且达到社区处罚阈值，并有可定位证据时为 true；证据不足、对象不明、短句情绪化表达或仅属公共讨论批评时应为 false。",
    )


class ViolationCaseStage1Batch(BaseModel):
    """第一阶段审核判定批次"""

    cases: List[ViolationCaseStage1] = Field(
        default_factory=list, description="本批第一阶段审核结果。"
    )


class ViolationCase(BaseModel):
    """第二阶段增强后的最终违规结果"""

    source_type: Literal["post", "comment"] = Field(
        ..., description="违规来源类型：主贴或评论。"
    )
    source_id: str = Field(..., description="主贴 note_id 或评论 comment_id。")
    index: int = Field(..., description="主贴为 -1，评论为对应序号。")
    quote: str = Field(..., description="用于展示的违规摘录。")
    category: str = Field(..., description="最终违规类别。")
    risk_level: Literal["High", "Medium", "Low"] = Field(..., description="风险等级。")
    reasoning: str = Field(..., description="逐条判定理由。")
    disposal_suggestion: str = Field(
        ...,
        description=(
            "逐条处置建议（六选一）："
            "限制/更改/屏蔽/删除相关内容的展示；"
            "撤销/删除/禁止修改账号认证、个人信息；"
            "禁言、禁点赞、禁被关注、禁发送及接收私信；"
            "扣除信用积分、中止或扣除广告共享收益、暂停/终止服务、注销账号；"
            "向有关监管部门或国家机关报告；"
            "其他合理措施。"
        ),
    )
    is_violation: bool = Field(..., description="是否最终认定违规。")
    primary_law: Optional[str] = Field(
        default="",
        description="后处理挂接的主要依据条款文本；由法规检索补充，不强制模型生成。",
    )
    law_reason: Optional[str] = Field(
        default="",
        description="后处理生成的法规匹配说明；用于报告附录和展示层解释。",
    )
    evidence_chain: List[str] = Field(
        default_factory=list,
        description="后处理拼装的证据链要点，通常包含违规摘录、判定要点、主要依据与匹配说明。",
    )


class ViolationCaseBatch(BaseModel):
    """第二阶段增强后的最终结果批次"""

    cases: List[ViolationCase] = Field(
        default_factory=list, description="本批终裁结果。"
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
    audience: str = Field(
        default="",
        description="最容易被卷入这一风险的人群、机构或平台角色。",
    )
    scene: str = Field(
        default="",
        description="一个具体、可感知的生活场景或舆论现场，用来说明这类风险最可能从哪里被点燃。",
    )
    evolution_path: str = Field(
        default="",
        description="从初始触发到舆情放大的演化路径。要写清先因为什么起、再滑向什么争议、最后可能升级到什么公共议题。",
    )

    # 兼容旧数据字段：新链路不再要求模型主动输出
    trigger: str = Field(
        default="",
        description="【兼容字段】旧版触发节点。新链路优先使用 scene。",
    )
    spread_path: str = Field(
        default="",
        description="【兼容字段】旧版传播路径。新链路优先使用 evolution_path。",
    )
    offline_scene: str = Field(
        default="",
        description="【兼容字段】旧版线下场景。新链路优先合并至 scene。",
    )
    online_scene: str = Field(
        default="",
        description="【兼容字段】旧版线上场景。新链路优先合并至 scene。",
    )
    content: str = Field(
        ...,
        description="内部推演底稿。说明风险为何在目标周期内容易出现、谁会推动扩散、哪类节点最危险。禁止空泛套话。",
    )
    summary_paragraph: str = Field(
        default="",
        description="面向读者展示的成品段落（建议140-240字）。首句必须从具体、可传播的起火场景切入，禁止以“当前/未来/这一风险/值得关注”等抽象判断开头；中段要自然写清争议如何被推大，不能机械履约或逐项翻译字段；结尾必须明确落到更大的公共议题（如规则公平、责任分配、平台治理、机构公信力、群体对立、消费信任等），不得只用“值得警惕/需重视”收尾。",
    )
    likelihood: Literal["高", "中", "低"] = Field(
        ..., description="该风险在预测周期内发生的概率评估。"
    )
    evidence_basis: List[str] = Field(
        ...,
        description="预测依据(至少1条)，必须列出支撑该预测的逻辑来源。例如：['历史规律：往年3月均为高校心理危机高发期', '未来情报：预计XX新规将于下月实施']。必须至少包含1条历史数据或未来情报，禁止仅引用当前舆论情绪。",
    )


class ForecastTopic(BaseModel):
    """预测报告的一个核心议题板块"""

    topic_name: str = Field(
        ...,
        description="议题标题，要有判断和记忆点，能概括这一组风险的主轴，不要写成行政口号。",
    )
    background: str = Field(
        ...,
        description="【未来视角背景】说明为何在这个预测周期内，该议题值得优先关注。要交代时间节点、现实压力或社会节奏，而不是空泛背景。",
    )
    main_tension: str = Field(
        default="",
        description="该议题最核心的矛盾，必须一句话说透，不要泛泛而谈。",
    )

    # 兼容旧数据字段：新链路已下沉到 point 级
    audience: str = Field(
        default="",
        description="【兼容字段】旧版 topic 级涉及人群。新链路优先使用 point.audience。",
    )
    scene_opening: str = Field(
        default="",
        description="【兼容字段】旧版 topic 级场景。新链路优先使用 point.scene。",
    )
    points: List[ForecastPoint] = Field(
        ...,
        min_length=2,
        max_length=4,
        description="该议题下的具体风险演化点。要求角度彼此区分，避免重复改写同一个风险。",
    )


class TrendForecastReport(BaseModel):
    """Agent D 的最终产出 (Government Report Style)"""

    target_period: str = Field(..., description="研判的周期与领域范围描述")

    evidence_sources: List[str] = Field(
        ...,
        description="【参考依据】列出推演时参考的关键来源类别，建议 3-8 条，不要长串堆砌。",
    )

    topics: List[ForecastTopic] = Field(
        ...,
        min_length=3,
        max_length=5,
        description="【核心议题预测】列出 3-5 个(必须3-5个)下个月最需要关注的舆情风险议题。要求各议题维度互不重复（正交）。",
    )


# =====================================================
# 6. Agent E: 报告总编
# =====================================================


class PrefaceSection(BaseModel):
    """前言部分的完整结构"""

    report_period: str = Field(
        ..., description="报告覆盖及研判周期 (如: '2025年10月回顾及11月前瞻')"
    )

    paragraphs: List[str] = Field(
        ...,
        description="【主输出】前言成品正文，严格输出1-2段。必须像压缩型新闻综述前言，而不是报告导读、正文摘要或提纲拼接。第一段先拎出本期主轴，再自然带出议题分布与总体情绪；第二段只压缩风险压力、治理难点与未来关注方向，不得展开成正文分析。",
    )


# =====================================================
# 7. 历史同期热门事件回顾 (Agent Historical)
# =====================================================


class HistoricalDailyEvent(BaseModel):
    """历史同期每天的热门事件"""

    date: str = Field(..., description="日期，格式: YYYY-MM-DD")
    event_title: str = Field(
        ...,
        description="事件标题，简洁明了的描述（如：成都官方通报游客遭强迫购物）",
    )
    event_summary: str = Field(
        ...,
        description="事件简短总结，50-100字，概括事件核心内容和影响",
    )


class HistoricalEventsList(BaseModel):
    """历史同期事件列表容器"""

    year_month: str = Field(..., description="年份-月份，格式: YYYY-MM")
    events: List[HistoricalDailyEvent] = Field(
        ..., description="该月每天的热门事件列表"
    )


class HistoricalSummary(BaseModel):
    """历史同期回顾章节导语"""

    summary_text: str = Field(
        ...,
        description="导语文本，一段话，80-200字(不少于80字)。客观说明历史回顾的意义，分析该月舆情特点。风格严肃，严禁使用 Emoji。",
    )


# =====================================================
# 8. 事件去重判断 (Agent B 深度分析前)
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


# =====================================================
# 质量门控 Schema (Agent 协作架构)
# =====================================================


class QualityScore(BaseModel):
    """兼容旧字段的质量检查记录（已不再作为主门控评分模型）"""

    agent_name: str = Field(..., description="对应的节点名称，用于兼容旧状态结构")
    completeness: int = Field(
        ..., ge=0, le=10, description="兼容旧字段：不再作为主门控评分依据"
    )
    accuracy: int = Field(
        ..., ge=0, le=10, description="兼容旧字段：不再作为主门控评分依据"
    )
    depth: int = Field(
        ..., ge=0, le=10, description="兼容旧字段：不再作为主门控评分依据"
    )
    overall: int = Field(
        ..., ge=0, le=10, description="兼容旧字段：不再作为主门控评分依据"
    )
    passed: bool = Field(..., description="兼容旧字段：是否通过检查")
    feedback: str = Field(..., description="兼容旧字段：检查反馈信息")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="可选的额外元数据(如: check_type, rule_violations, llm_rationale)",
    )

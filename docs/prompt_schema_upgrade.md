# Prompt 与 Schema 升级方案

> 本文是 `agent_refactor_proposal.md` 的配套文档，专门讨论 Agent 化改造中 Prompt 和 Schema 的升级策略。

---

## 1. 当前 Prompt/Schema 问题诊断

### 1.1 Prompt 层面问题

| # | 问题 | 具体表现 | 影响 |
|---|------|---------|------|
| PP1 | **角色定义与工具调用脱节** | 当前 Prompt 直接指令LLM"输出JSON"，未设计为Agent思考链 | 无法支持 ReAct 推理 |
| PP2 | **无输出质量自检指令** | Prompt 不要求 LLM 对自己的输出做质量评估 | 无法支持反思机制 |
| PP3 | **过度冗长的格式约束** | 如 AGENT_B_REDUCE_TEMPLATE 约420行，大量篇幅是格式规则 | 消耗 Token，适得其反 |
| PP4 | **硬编码搜索策略** | Agent D 的搜索词在 nodes.py 中硬编码构造 | Agent 无法自主调整搜索策略 |
| PP5 | **无思维链(CoT)引导** | 仅 Agent D 有 THINKING PROTOCOL，B/C/E 缺失 | 分析深度不一致 |
| PP6 | **反面约束过多** | "严禁X"、"绝对禁止Y"占大量篇幅 | LLM 注意力分散，正面指令被稀释 |

### 1.2 Schema 层面问题

| # | 问题 | 具体表现 | 影响 |
|---|------|---------|------|
| SP1 | **description 过长** | 如 `EventAnalysisReport.event_overview` 的 description 有 100+ 字 | 结构化输出 Token 开销大 |
| SP2 | **缺少评分/置信度字段** | Agent 输出无 `quality_score` 或 `confidence` 字段 | 无法支持质量门控 |
| SP3 | **缺少元数据字段** | 无 `tool_calls_used`、`retry_count`、`reasoning_trace` | 无法追踪Agent决策过程 |
| SP4 | **Prompt指令嵌入description** | Schema field description 中包含大量写作指导 | 职责混淆（Schema管结构，Prompt管内容） |

---

## 2. Prompt 升级策略

### 2.1 总体原则

1. **角色+目标+工具** 三段式：先定义角色，再说明目标，最后列出可用工具
2. **正面指令优先**：用"必须做X"替代"严禁做Y"，减少否定句
3. **CoT 引导通用化**：所有 Agent 统一使用思维链引导
4. **质量自检嵌入**：在输出指令中加入自评环节
5. **精简格式约束**：将格式要求转移到 Schema description 中，Prompt 只管内容质量

### 2.2 Agent System Prompt 模板（通用）

```
## ROLE
你是舆情研判系统中的{agent_name}。
你的核心能力是{core_competency}。

## GOAL
{specific_goal}

## AVAILABLE TOOLS
你可以使用以下工具完成任务：
{tools_description}

## THINKING PROTOCOL
在执行任务前，请先思考：
1. 我需要哪些数据？→ 选择合适的工具获取
2. 数据是否充分？→ 不足则补充获取
3. 我的分析是否有深度？→ 不够则加深

## QUALITY CHECKLIST
完成任务后，请自检：
- [ ] 内容是否覆盖了所有必要维度？
- [ ] 数据引用是否准确？
- [ ] 分析是否有独立观点（非复述）？
- [ ] 输出质量自评分: ___/10
```

### 2.3 各 Agent Prompt 升级要点

#### Analysis Agent (现 AGENT_B)

**当前问题**：
- MAP_TEMPLATE 和 REDUCE_TEMPLATE 分离，但 ReAct Agent 不需要这种分离
- Prompt 中包含大量格式强制（"不少于8句"、"不少于200字"）

**升级方案**：
```
## ROLE
你是舆情研判系统的舆情分析专家（Analysis Agent）。
擅长从海量微博帖子和评论中提炼深层舆论结构。

## GOAL
对指定事件进行深度舆情分析，输出结构化的分析报告。

## TOOLS
- search_web(query): 搜索事件背景与官方通报
- analyze_single_event(event, posts, comments): 对事件的帖子评论做观点聚类
- reduce_opinions(analyses): 将多次分析汇总为综合报告
- search_supplementary(query): 发现观点单一时补充搜索

## THINKING PROTOCOL
1. 先搜索事件的官方口径和新闻背景
2. 分析每个帖子的评论观点分布
3. 检查是否存在观点盲区（如只有支持没有反对）
4. 若观点不够多样，发起补充搜索
5. 汇总为多层次分析报告

## QUALITY STANDARD
- 每个事件至少2个对立观点
- 分析需区分"主流声浪/次生质疑/深层情绪"
- 禁止复述事件概况当作分析
```

**关键变化**：
- 删除了"不少于8句"等硬性长度要求（改为Schema的min_length控制）
- 删除了"严禁使用Emoji"等反复出现的禁令（统一到System Prompt一次性说明）
- 增加了工具使用思维链
- 增加了质量标准（正面表述）

#### Compliance Agent (现 AGENT_C)

**当前问题**：
- BATCH_TEMPLATE 有大量"SAFE_MODE"、"SYSTEM CONFIGURATION"等越狱防护
- 审查原则过于复杂（审查标准本身约占50%的Prompt Token）

**升级方案**：
```
## ROLE
你是内容安全分类器（Compliance Agent）。
任务是客观识别微博文本中的违规内容。

## TOOLS
- batch_audit(post, comments): 批量审查帖子与评论的合规性
- search_laws(category): 从法规库检索违规依据
- generate_evidence(violations, laws): 生成合规证据链

## AUDIT PRINCIPLES (精简为3条)
1. 只基于文本本身判定，不做"可能引发"等推断
2. 高容忍度：负面情绪/吐槽/讽刺/轻度脏话默认合规
3. 仅在恶毒辱骂/明确仇恨/教唆犯罪时才判定违规

## WORKFLOW
1. 使用 batch_audit 检测违规项
2. 如检测到违规，使用 search_laws 检索法规依据
3. 使用 generate_evidence 生成证据链
4. 自检：违规率>50%时重新审视标准是否过严
```

**关键变化**：
- 将50+违规类别从Prompt移到工具参数（`batch_audit` 工具内部注入 categories）
- 审查原则从10+条精简为3条核心原则
- 越狱防护转移到 System Message 层面（一次性设置，而非每次重复）
- 新增自检逻辑

#### Forecast Agent (现 AGENT_D)

**当前亮点**：已有 THINKING PROTOCOL，保留并增强。

**升级方案**：
```
## TOOLS
- search_historical(query): 搜索历年同期规律
- search_future_intel(query): 搜索未来日历/政策
- generate_forecast(opinion, audit, history, future): 生成预测报告

## THINKING PROTOCOL (增强版)
1. 先用 search_historical 获取历史同期规律（必须引用）
2. 再用 search_future_intel 获取未来情报（必须引用）
3. 排除法：剔除当前已发生的事件
4. 风险耦合：[未来节点] + [当前压抑情绪] = [新爆发点]
5. 自检：每个预测是否有"具体时间+具体事件+具体群体"？
```

**关键变化**：
- 搜索词从 nodes.py 硬编码移到 Agent 自主构造
- Agent 可看到搜索结果后决定是否补充搜索
- 时间计算从 nodes.py 的130行代码简化为工具参数

#### Report Agent (现 AGENT_E)

**当前问题**：PREFACE_TEMPLATE 约180行，其中大量是写作范式约束。

**升级方案**：
```
## TOOLS
- generate_preface(events, audit, forecast): 生成前言
- assemble_chapter(chapter_name, data): 按模板组装章节
- apply_styling(markdown): 应用CSS样式
- save_report(report, metadata): 保存到数据库

## WORKFLOW
1. 使用 generate_preface 生成前言（传入所有素材）
2. 按固定顺序组装五章：热点概览 → 舆情洞察 → 合规审计 → 趋势预判 → 全文
3. 使用 apply_styling 添加CSS
4. 自检：五章是否齐全？数据引用是否一致？
5. 使用 save_report 保存
```

**关键变化**：
- 前言写作范式精简50%（核心要求保留，范文示例移到 few-shot examples）
- 章节组装逻辑从919行的 `agent_report.py` 拆分为独立工具
- 写作风格要求统一维护在一个配置中，而非每个 Prompt 重复

---

## 3. Schema 升级策略

### 3.1 通用改进：添加质量/元数据字段

为所有 Agent 输出 Schema 添加以下通用字段：

```python
class AgentOutputMeta(BaseModel):
    """所有 Agent 输出的通用元数据"""
    quality_self_score: int = Field(
        ..., ge=0, le=10,
        description="Agent 对自身输出的质量自评分(0-10)"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Agent 对输出结果的置信度(0.0-1.0)"
    )
    reasoning_summary: str = Field(
        ..., max_length=200,
        description="Agent的推理摘要：用了哪些工具、做了几次尝试、关键决策点"
    )
```

### 3.2 EventAnalysisReport 升级

**当前问题**：description 中嵌入了大量写作指导（如"必须不少于150字/8句话"）

```python
# ===== 当前（问题版本）=====
class EventAnalysisReport(BaseModel):
    event_overview: str = Field(
        description="【事件概述】必须不少于150字/8句话。以新闻调查记者的笔触..."  # 100+字的description
    )

# ===== 升级后 =====
class EventAnalysisReport(BaseModel):
    """单个事件的深度舆情分析报告"""
    
    event_overview: str = Field(
        ..., min_length=150,
        description="事件概述：还原核心事实，含时间节点、冲突焦点、官方处置"
    )
    public_opinions: list[str] = Field(
        ..., min_length=4,
        description="舆论观点列表：分层梳理主流声浪/次生质疑/深层情绪/对立博弈"
    )
    depth_analysis: str = Field(
        ..., min_length=200,
        description="深度点评：事件本质判断、社会警示、各方反思、社会学归因(禁止复述概述)"
    )
    
    # 新增字段
    key_entities: list[str] = Field(
        default_factory=list,
        description="事件涉及的关键实体(人物/机构/地点)"
    )
    risk_level: Literal["高", "中", "低"] = Field(
        ..., description="事件舆情风险等级"
    )
    meta: AgentOutputMeta = Field(
        ..., description="Agent输出元数据"
    )
```

**关键变化**：
- description 从100+字精简到30字（写作指导移到Prompt）
- 用 `min_length` 替代"必须不少于X字"的文本描述
- 新增 `key_entities`（便于去重和报告引用）
- 新增 `risk_level`（便于 Supervisor 决策）
- 新增 `meta`（支持反思和质量门控）

### 3.3 BatchComplianceResult 升级

```python
# ===== 升级后 =====
class BatchComplianceResult(BaseModel):
    """合规审计结果"""
    
    is_post_violated: bool = Field(..., description="主贴是否违规")
    violated_comments: list[ViolatedItem] = Field(
        default_factory=list,
        description="违规评论列表"
    )
    
    # 新增
    total_scanned: int = Field(
        ..., description="本次扫描的总内容条数(主贴+评论)"
    )
    violation_rate: float = Field(
        ..., ge=0.0, le=1.0,
        description="违规率(违规条数/总条数)"
    )
    meta: AgentOutputMeta = Field(
        ..., description="Agent输出元数据"
    )
```

**新增字段价值**：
- `total_scanned`：便于计算和展示审计覆盖范围
- `violation_rate`：便于反思机制判断审查标准是否合理
- `meta`：支持质量门控

### 3.4 TrendForecastReport 升级

```python
# ===== 升级后 =====
class ForecastPoint(BaseModel):
    subtitle: str = Field(..., description="风险点标题")
    content: str = Field(..., min_length=200, description="深度研判内容")
    likelihood: Literal["高", "中", "低"] = Field(..., description="发生概率")
    evidence_basis: list[str] = Field(
        ..., min_length=1,
        description="预测依据(必须引用历史数据或未来情报)"
    )
    # 新增
    trigger_date: str = Field(
        ..., description="预计触发时间点(如'3月15日'、'开学季')"
    )
    verifiable: bool = Field(
        ..., description="该预测是否可在未来验证"
    )


class TrendForecastReport(BaseModel):
    target_period: str = Field(..., description="研判周期")
    topics: list[ForecastTopic] = Field(
        ..., min_length=3, max_length=5,
        description="核心议题预测(3-5个，维度互斥)"
    )
    evidence_sources: list[str] = Field(
        ..., description="参考依据来源"
    )
    # 新增
    meta: AgentOutputMeta = Field(..., description="Agent输出元数据")
```

**新增字段价值**：
- `trigger_date`：强制 Agent 给出具体时间，避免"可能会发展"
- `verifiable`：让 Agent 标注预测是否可验证，提升严谨性

### 3.5 PrefaceSection 升级

```python
# ===== 升级后 =====
class PrefaceSection(BaseModel):
    """前言（精简description，写作指导移到Prompt）"""
    
    report_period: str = Field(..., description="报告研判周期")
    overview: str = Field(..., min_length=200, description="开篇综述：时间跨度、涉及领域、总体态势")
    characteristics: list[str] = Field(
        ..., min_length=3, max_length=3,
        description="3个核心特征，每个含现象-机制-影响三层分析"
    )
    compliance_perspective: str = Field(
        ..., min_length=100,
        description="违规透视：基于审计数据分析非理性程度"
    )
    trend_connection: str = Field(
        ..., min_length=80,
        description="时空承接：下阶段风险共振点"
    )
    conclusion: str = Field(
        ..., min_length=100,
        description="结语：核心风险+至少3条治理建议"
    )
```

**精简效果对比**：

| 字段 | 当前description长度 | 升级后长度 | 减少 |
|------|-------------------|-----------|------|
| overview | 180字 | 25字 | -86% |
| characteristics | 220字 | 30字 | -86% |
| compliance_perspective | 130字 | 25字 | -81% |
| trend_connection | 100字 | 18字 | -82% |
| conclusion | 140字 | 22字 | -84% |

> Schema description 精简后，结构化输出的 Token 开销减少约 **60%**，写作质量要求转由 Prompt 承担。

### 3.6 新增 Schema: SupervisorState & QualityScore

```python
class QualityScore(BaseModel):
    """Supervisor 对 Agent 输出的质量评分"""
    agent_name: str
    completeness: int = Field(..., ge=0, le=10, description="内容完整性")
    accuracy: int = Field(..., ge=0, le=10, description="专业准确性")
    coherence: int = Field(..., ge=0, le=10, description="逻辑连贯性")
    overall: int = Field(..., ge=0, le=10, description="综合评分")
    passed: bool = Field(..., description="是否通过(overall>=7)")
    feedback: str = Field(default="", description="不通过时的改进建议")


class ReflectionResult(BaseModel):
    """Agent 自我反思结果"""
    quality_score: int = Field(..., ge=0, le=10)
    passed: bool = Field(...)
    issues: list[str] = Field(default_factory=list, description="发现的问题")
    suggestions: list[str] = Field(default_factory=list, description="改进建议")
    retry_hint: str = Field(default="", description="重试时的提示")
```

---

## 4. Prompt Token 优化估算

### 4.1 当前 Prompt Token 消耗

| Prompt | 估算Token |
|--------|----------|
| AGENT_B_MAP_TEMPLATE | ~400 |
| AGENT_B_REDUCE_TEMPLATE | ~800 |
| AGENT_C_BATCH_TEMPLATE | ~900 |
| AGENT_C_EVIDENCE_TEMPLATE | ~600 |
| AGENT_D_FORECAST_TEMPLATE | ~700 |
| AGENT_E_PREFACE_TEMPLATE | ~1200 |
| Schema descriptions (合计) | ~800 |
| **总计(每次完整运行)** | **~5400** |

### 4.2 优化后预估

| 优化措施 | Token节省 |
|---------|----------|
| Schema description精简(-80%) | -640 |
| 违规类别从Prompt移到工具参数 | -200 |
| 合并重复的禁令到System Message | -300 |
| 精简格式约束(长度要求改用min_length) | -400 |
| **总节省** | **~1540 (-28%)** |

> 但新增 Supervisor 评估 Prompt (~300/次) 和反思 Prompt (~200/次)，净效果约 **-20%** Prompt Token，同时输出质量显著提升。

---

## 5. 升级实施建议

### 5.1 Prompt 升级顺序

1. **先升级 Schema**（添加 meta 字段、精简 description）—— 影响最小，收益最大
2. **再升级 Agent C Prompt**（精简审查原则）—— 当前最冗长
3. **然后升级 Agent E Prompt**（精简前言模板）—— 第二冗长
4. **最后升级 Agent B Prompt**（合并 MAP+REDUCE 为 Agent 工具链）—— 改动最大

### 5.2 兼容性处理

- Schema 新增字段全部设 `default` 或 `default_factory`，不破坏现有数据
- Prompt 修改后先在测试任务中验证输出质量，再上线
- 旧报告数据在 MongoDB 中不受影响（新字段只在新报告中出现）

# 基于多-Agent 协同与 RAG 的舆情研判系统：系统设计、实现与评估

作者：
导师：
单位：
日期：2026-01-14

关键词：舆情研判；多-Agent 系统；RAG（检索增强生成）；结构化 LLM 输出；可审计报告；断点续传

---

## 摘要 (Abstract)

随着社交媒体规模的爆发性增长，公共舆情呈现短平快、碎片化和高时效性的特征。传统人工监测无法实时、系统化地应对大规模信息流，因此亟需工程化、自动化且可审计的舆情研判系统。本文提出并实现了一套基于多-Agent 协同、RAG（检索增强生成）与结构化 LLM 输出的端到端舆情研判系统。系统通过五个职责分离的 Agent（A：热度统计，B：观点分析，C：合规审查，D：趋势预测，E：报告生成）完成从数据采集、清洗、观点抽取、合规判定、证据链生成到结构化报告的闭环。工程上采用 LangGraph 工作流编排与 SqliteSaver Checkpointer 实现断点续传；Chroma 向量库作为法规检索的 RAG 基座；前端基于 Vue 3 + Pinia 实现任务控制与可视化。我们设计了结构化的 Pydantic schema 严格约束 Agent 输出，并提出一套人工＋量化的评估方法用于验证观点分析与证据链质量。实验与案例分析表明，该系统在保证可解释性与可审计性的前提下能够稳定产出高质量研判报告，为公共舆情监测与风险预警提供工程化解决方案。

---

## 1. 引言 (Introduction)

背景与问题陈述：社交媒体平台（如微博、推特等）带来大量用户生成内容（UGC），在重大事件或政策议题上快速聚合公众情绪与观点。如何在海量、多变、嘈杂的数据中自动提炼出可操作、可审计的结论，成为公共治理与舆情应对的重要挑战。

研究目标：构建一套工程化的舆情研判系统，达到以下目标：
- 自动化：从数据采集到报告生成尽可能自动化，降低人工成本；
- 结构化：输出结构化、可机读的分析结果，支持后续检索与统计分析；
- 可审计：确保合规判定与引用的法规有可追溯的证据链；
- 可复现与可恢复：系统支持断点续传与任务重试，便于长任务可靠执行。

贡献：本文的主要贡献包括：
1) 将多-Agent 协同思想工程化为一套可运行、可复现的舆情研判管线；
2) 提出并实现了 RAG + LLM 的合规证据链构建方法，并设计审计回填机制以处理 RAG 无命中情形；
3) 通过 Pydantic schema 强化 LLM 输出的结构化约束，提升系统可校验性与鲁棒性；
4) 提供端到端实现与实践指南，含断点续传、并发控制、监控与运维策略，支撑从演示到生产化的平滑演进。

---

## 2. 相关工作 (Related Work)

本节综述三个方向的代表性研究与系统工程实践：舆情自动分析、RAG 与证据生成、LLM 驱动的结构化输出。

2.1 舆情分析与观点挖掘：过去的研究多依赖情感分析、主题模型（LDA）与图谱方法进行舆情抽样与主题追踪，但在面对长文本上下文与法律合规性判定时往往力不从心 [1,2]。

2.2 RAG（检索增强生成）在法律/医疗等具有事实依赖的领域显示出优势：通过外部检索提升生成文本的可证据性 [3,4]。然而，RAG 的检索覆盖率与检索-生成对齐问题仍是挑战，且需要审计机制避免 LLM 虚构条款。

2.3 结构化输出与 Schema 验证：采用 Pydantic 等 schema 约束 LLM 输出，能显著降低解析错误且便于下游程序处理 [5]。

我们的方法在这些方向上做工程化整合：在 RAG 之上实现合规证据链并用 schema 强制输出格式，同时增加审计回填与断点续传机制以提高工程可用性。

---

## 3. 方法概述 (System & Method Overview)

系统总体分为数据层、工作流引擎层、Agent 层、存储与前端展示层：

- 数据层负责采集热搜快照、帖子与评论并做 ETL 清洗；
- 工作流层使用 LangGraph 编排 Agent 顺序并注入 Checkpointer 实现断点续传；
- Agent 层由五个 Agent 组成（A–E），每个 Agent 关注单一职责并通过明确定义的 Pydantic schema 进行输入/输出规范化；
- 存储层使用 MongoDB 保存原始内容与报告会话，Chroma 保存法规向量；
- 前端负责任务创建、实时进度与日志展示、报告下载。

方法要点：
1) Map-Reduce 风格的观点分析：并行处理大量帖子（Map），再由 Reduce 阶段做跨贴的观点聚合（EventAnalysisReport）；
2) Batch + RAG 的合规审查：先做 LLM 批量判定，再用 Chroma 检索法规并以结构化 LLM 生成 ComplianceEvidenceReport；
3) 可审计的回填机制：若 RAG 无命中，系统允许 LLM 生成条款草案回填 matched_laws，并在 evidence 中标注 auto_fallback_cited_laws 以供人工复核；
4) 基于 schema 的质量控制：所有 Agent 输出均由 Pydantic 校验最小长度、列表数量等策略保证文本深度与一致性（例如 ForecastTopic min_length 和 list length），避免脆弱输出。

本方法兼顾语义质量、可审计性与工程可用性。

---

## 4. 数据与 ETL

4.1 数据源：以微博热搜与微博帖子/评论为主，数据来源包括定时抓取的热搜快照（`hot_trends_history`）、weibo_contents（posts）、weibo_comments（comments）。

4.2 时间窗口与采样策略：默认以近 24 小时为单周期，支持按天或按用户自定义起止日期范围。针对数据量大时，采样策略包含：取 top_n 快照的前若干条、按热度或点赞数排序、对评论限制最大条数（默认 200）。

4.3 ETL 清洗：包括日期解析、字段规范化、合并近义关键词（EventMerger）、去重以及对文本做基本清洗（去 emoji、超长截断、字符编码校验）。ETL 输出的是结构化的 `events` 集合，字段包含 `event_name`, `related_keywords`, `total_heat`, `merge_reason` 等。

---

## 5. Agent 设计与实现（概述）

下文将依次详细讨论 A–E 各 Agent 的任务、方法、Prompts 与工程实现要点：

- Agent A（热度统计）：用 MongoDB aggregation 提取 Top-N，并做字段标准化；输出为 `core_events`。
- Agent B（观点分析）：Map 阶段并行对帖子做观点聚类（PostOpinionSummary），Reduce 阶段聚合为 EventAnalysisReport；关键工程实践为并行控制、Prompt 工程与结构化解析。
- Agent C（合规审查）：Batch 审查 + Chroma 检索 + 证据链生成；实现细节包括 matched_laws 结构、risk_level 回填、证据链格式与回写策略。
- Agent D（趋势预测）：结合历史/未来情报做 3–5 个预测议题的结构化输出（TrendForecastReport），包含 likelihood、evidence_basis 与落地建议。
- Agent E（报告生成）：汇编 A–D 产物为 Markdown/PDF，保存报告会话并返回文件路径。

（注：接下来章节将展开每个 Agent 的算法细节、Prompt 片段、Schema 定义与工程实现）

---

## 6. 后端实现详述（细化）
本节对后端的关键实现逐一展开，涵盖：Agent A–E 的内部算法、Prompt 工程、结构化输出细则、并发模型、错误处理与回写策略；同时讨论 Checkpointer 的使用、DB 读写优化、API 设计与安全约束。

### 6.1 Agent A（热度统计）的工程化实现

目标回顾：从 ETL 的归并事件中计算热度分值并筛选 Top‑N 事件，输出带完整元数据的 `core_events`。

关键实现说明：

1) 数据采样与窗口控制
- 采用用户参数或默认窗口（24 小时）从 `hot_trends_history` 读取 snapshots，若输入为日期（YYYY-MM-DD），窗口自动扩展至整日时间区间。实现时保证查询使用索引（`collected_at`）以减少 I/O 延迟。

2) 多因子热度模型
- 公式：

  total_heat(e) = α * norm_exposure(e) + β * norm_interaction(e) + γ * recency(e)

  其中：
  - norm_exposure：基于该事件在不同 snapshot 的出现频数做 min-max 标准化后（或 log1p 后再标准化）；
  - norm_interaction：综合 top posts 的 liked_count、comment_count、share_count（先做 log1p 转换，按权重合并）；
  - recency：时间衰减函数 r(t)=exp(-λ * Δt_hours)，λ 可配置以控制对新热点的敏感性；
  - α,β,γ 为可配置权重（默认 α=0.5, β=0.4, γ=0.1），在实验阶段可用小规模人工标注数据做网格搜索调整。

3) 归一化与稳健性处理
- 对于稀疏或异常值（例如单个帖子获得极高点赞），采用 trimmed-mean 或 percentile cap（例如 99th percentile capping）来避免极端值影响；
- 算法复杂度：单次统计 O(N)（N 为快照内平铺后事件数），排序 Top‑N 采用堆选择 O(N log K) 优化。

4) 工程实现要点
- 函数封装：`agents/agent_stats.py::run()` 做三步（读取->计算->格式化）；
- 日志：输出榜首摘要与 top N 的热度，以便调试；
- 输出格式：每个事件包含 `id`, `topic`, `related_keywords`, `total_heat`, `summary`, `created_at`，并将其写入 `events` 集合。

测试建议：
- 单元：对 `norm`、`recency` 函数进行边界与分布测试；
- 集成：用合成数据来验证 Top‑N 的稳定性并通过 A/B 测试验证权重调整的影响。

*参考实现片段（伪代码）*：

```python
# compute total heat for each event
for e in events:
    exposure = compute_exposure(e)
    interaction = compute_interaction(e)
    decay = math.exp(-lam * hours_since(e))
    e['total_heat'] = alpha * norm(exposure) + beta * norm(interaction) + gamma * decay
# select top-N
top_events = heapq.nlargest(K, events, key=lambda x: x['total_heat'])
```

---

### 6.2 Agent B（舆情观点分析）详解

目的：对候选事件内的帖子与评论进行深度观点抽取与分层汇总，输出 `EventAnalysisReport`，供合规审查与趋势预测使用。

实现组件与流程：

- Map 阶段（单贴分析）：
  - 输入：每帖的 `content`, `comments[]`, `media_context`；
  - 处理：选取每帖前 M 条代表性评论（按 `comment_like_count` 排序），对评论做去噪/去重/截断；
  - 调用：`ChatOpenAI.with_structured_output(PostOpinionSummary)`，Prompt 使用 `AGENT_B_MAP_TEMPLATE`。
  - 输出样式：`opinion_clusters`（每项含 viewpoint, emotion, estimated_ratio），`conflict_analysis`。

- Reduce 阶段（事件级聚合）：
  - 输入：排序后的 map 输出片段；
  - 聚合方法：使用 LLM 做高阶抽象，将多个帖子观点进行语义归并并生成 `EventAnalysisReport`。

并行化与吞吐控制：
- Map 阶段采用 `ThreadPoolExecutor` 并发执行以提升吞吐，`max_workers` 的设置需考虑 LLM 限额与 CPU 资源；
- 对 LLM 的调用采用限速器（token bucket 或 leaky bucket）以避免突破外部服务配额。

Prompt 与 Schema 设计：
- Map Prompt 强调“去噪、阵营划分、量化占比、冲突检测”，要求结构化 JSON 输出；
- Reduce Prompt 强调“零复述原则”，要求深度分析（非事件复述），并在 Schema 中强制 `event_overview` 与 `depth_analysis` 的最小长度。

鲁棒性策略：
- Map 超时或失败降级为 extractive summary（基于规则的简短摘要），并记录失败原因；
- Reduce 若生成结构化失败，则触发 fallback：合并 Map 输出的 `cluster` 文本并用模板生成短版报告；
- 所有 LLM 调用均记录 `prompt_hash`, `model`, `temperature`, `response_time` 以及 `token_usage` 至 provenance 字段以便审计。

评估方法：
- 定性：组织专家对若干事件的 `EventAnalysisReport` 进行盲评（可信度、完整性、深度）打分；
- 定量：可采用自动化度量（BERTScore、ROUGE）对 Map 输出与 gold summaries 的相似度进行评估，但主观评估仍关键。

---

### 6.3 Agent C（合规审查）详解

本 Agent 的目标是对帖子与评论生成可审计的违规判定与证据链，并回写数据库供报告引用。

核心流程：
1. Batch Audit：使用结构化 LLM（`BatchComplianceResult`）对主贴与评论批量判定；
2. 标签收集：从 `violated_items` 中提取违规类别作为 RAG 查询词；
3. Chroma 检索：针对每个违规类别检索 `top_k` 条法规文档（带 metadata）；
4. 证据链生成：将违规项与匹配法规送入 `AGENT_C_EVIDENCE_TEMPLATE` 的 LLM Chain，生成 `ComplianceEvidenceReport`；
5. 审计回填：若没有匹配法规（RAG 空结果），允许 LLM 生成 `cited_laws` 并在 `evidence_report` 标注 `auto_fallback_cited_laws = true`；
6. 回写数据库：把 `batch_result`, `matched_laws`, `evidence_report` 写回 `weibo_contents` 与 `weibo_comments`。

技术细节：
- Chroma metadata 设计：每条法规包含 `category`、`article`、`full_desc`、`risk_level`，并在构建索引时把`category` 作为 filter 字段以支持精准过滤检索；
- risk_level 合并逻辑：对多条匹配结果取最高风险级别并回填至 `violated_items`；
- 证据链要求：每一点要引用原始文本片段（comment index、snippet）并标注匹配法律条款 ID。

审计与安全：
- 将 LLM 回退生成的法律条款标注为“LLM-suggested”并附带生成时的 prompt 与 model metadata；
- 在界面/报告中把这类回填条目高亮并建议人工审核。

评估指标：
- 违规检测的准确率/召回率（相对人工标注集）；
- 证据链的正确性（人工检验匹配到正确条款的比例）；
- RAG 覆盖率与 LLM 回填占比。

---

### 6.4 Agent D（趋势预测）

目标：生成 3–5 个互斥（正交）的预测议题（TrendForecastReport），对每个议题给出 likelihood、演化路径与落地建议。

方法要点：
- 时间锚化：通过 `forecast_range`（1w/2w/1m/2m）生成 `time_period_desc`，并把其作为 prompt 的显式锚点以减少模糊性；
- 风险耦合（Risk Coupling）：采用规则化推理模板：Future Node + Current Pressure -> 新的爆发点；示例公式：

  Risk = f(Exposure, Vulnerability, Trigger)

  其中 Trigger 来自未来情报（policy changes、calendar events），Exposure 来自当前观点情绪与传播速率，Vulnerability 来自已检出的合规/治理短板。

- 输出结构化：每个 `ForecastTopic` 要求 `points`（3–5 个 `ForecastPoint`），每个 `ForecastPoint` 包含 subtitle、content（≥80 字）、likelihood（高/中/低）、evidence_basis（至少一条历史或情报引用）。

评估：通过历史回测（若有历史数据）验证预测在一段时间内的命中率；若无大量历史数据，采用专家盲评法评判预测的合理性与可操作性。

---

### 6.5 Agent E（报告生成）

职责：将所有模块产物编排为标准化的研判报告（Markdown，转 PDF），并保存报告元数据至 MongoDB。

实现细节：
- 模板化：AGENT_E_PREFACE_TEMPLATE 指定前言要求与风格，Agent E 使用 LLM 生成前言并把 A–D 的摘要插入报告章节；
- Markdown 构建：把各模块输出格式化为 Markdown 章节（表格、引用、列表），并用 Pandoc 或 markdown -> WeasyPrint/PDFkit 生成 PDF；
- 元数据持久化：写入 `report_sessions` 包含 task_id, created_at, category, pdf_path, markdown。

可复现性与校验：
- 每次生成报告附带 provenance（所用 prompts 版本、模型、token 用量、map/reduce 的中间输出引用），以保证外推与复盘。

---

## 7. Checkpointer 与任务恢复细节

Checkpointer（SqliteSaver）在每个节点完成后按配置写入 State snapshot（LangGraph 的 State），包含当前节点产生的关键字段（如 core_events、analyzed_events 等），并保存时间戳与版本信息。恢复流程为：
1. 服务重启或故障后，运行 `run_task --id <thread_id>`，LangGraph 在 compile 时检测到已有 snapshot 将直接加载并从中断节点继续执行；
2. 为保证数据一致性，要求 snapshot 写入时使用短事务并在写入日志中记录操作完成标志；
3. 定期备份 SQLite 文件到持久存储以便在节点或磁盘故障时恢复。

---

## 8. 数据库与索引策略

MongoDB：
- 对 `hot_trends_history.collected_at`、`weibo_contents.note_id`、`weibo_comments.note_id` 建立索引以加速查询；
- 对 `events.total_heat` 做索引以加速 top-N 查询；
- 对审计相关字段（`is_violation`, `audit_status`）建立复合索引以便批量回写查询。

Chroma：
- Persistent collection 使用 `collection_name='weibo_audit_rules'`，metadata 包括 `category`、`article`、`risk_level`；
- 定期 reindex 与增量更新支持法规文本升级。

---

## 9. API 设计与错误处理

关键端点：
- POST /api/tasks：创建任务并返回 task_id；
- GET /api/tasks/{task_id}：返回 TaskStatus（含 progress/start_time/end_time）；
- POST /api/settings/llm/test：测试 LLM 连接并返回响应样例。

错误处理策略：
- 统一错误返回格式：{ code:int, message:str, details:opt }，并对外记录 request_id 与 task_id；
- 对于任务执行中发生的异常，返回 500 并在后端记录完整 traceback 与 snapshot；
- 前端在收到 404 或 500 时展示用户友好提示并记录日志以便工程追查。

---

## 10. 单元与集成测试建议

- 单元测试覆盖率目标 80%+：函数级别测试（日期解析、归一化、DB wrapper）；
- 集成测试：使用测试 Mongo 实例与 Mock LLM 运行 `run_task` 的简化配置并验证状态流与 DB 写回；
- 合规模块特化测试：生成若干违规/非违规样例并检查 `evidence_report` 的字段完整性与可回溯性。

---

（后续章节：前端实现、实验设计与评估、部署文档、参考文献与附录将在下轮迭代继续扩写。）
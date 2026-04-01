# 毕业设计技术报告 — 面向舆情研判的多-Agent 协同系统

作者: 项目团队
日期: 2026-01-14

---

## 摘要
本项目构建了一套面向社交媒体舆情监测与研判的端到端系统，集成数据采集、清洗与归并（ETL）、观点抽取、合规审查（RAG + LLM）、趋势预测与自动化报告生成等功能。系统采用 LangGraph 工作流编排、多 Agent（A–E）协同的 Map-Reduce 风格设计，结合 Chroma 向量检索、结构化 LLM 输出（with_structured_output + Pydantic schema）与可断点续传的 Checkpointer（SQLite + LangGraph），实现了高置信度、可审计且可重复的研判能力。

本文档详尽记录了系统需求、架构设计、实现细节、关键技术选型、工程实现与评估方法，便于学术答辩与工程交接使用。

---

## 目录
1. 系统目标与需求
2. 总体架构
3. 技术栈与第三方组件
4. 详细设计与实现
   - 数据采集、ETL 与事件聚合
   - Agent A: 热度统计（候选事件筛选）
   - Agent B: 舆情观点分析（Map / Reduce）
   - Agent C: 合规审查（Batch + RAG + 证据链）
   - Agent D: 趋势预测（结构化报告）
   - Agent E: 报告总编（Markdown / PDF）
   - Checkpoint 与断点续传机制
   - 存储层（MongoDB / Chroma / SQLite）
   - 后端服务与 API（FastAPI）
   - 前端实现（Vue 3 + Pinia）
   - 并发、容错与监控考虑
5. 部署、运行与复现实验
6. 评估方法与结果（设计说明）
7. 限制与未来工作
8. 附录：关键文件与运行命令

---

## 1. 系统目标与需求
目标：在给定时间窗口内对社媒（以微博热搜与帖子为主）进行自动化的舆情研判，输出可操作、可审计的研判报告，满足如下非功能与功能需求：

- 功能需求
  - 自动采集热搜快照并抽取 TopN 话题与候选帖子/评论；
  - 对候选话题进行观点聚类与深度分析（保证结构化与可审计）；
  - 对被判为违规的文本给出证据链并检索匹配法规条款（RAG）；
  - 基于历史与当前态势做短期/中期趋势预测并给出建议；
  - 自动生成可下载的 Markdown/PDF 报告并持久化存档。

- 非功能需求
  - 可重复/可审计：中间产物、证据链与引用需可回溯；
  - 高可用性：任务支持断点续传，长任务不阻塞 API；
  - 可扩展性：工作流节点与 Agent 可增减；
  - 安全与隐私（工程化）：API、日志不泄露敏感凭证，合规审查结果可人工复核。

---

## 2. 总体架构
系统采用前后端分离结构：

- 后端：FastAPI 提供任务创建/状态查询/LLM 设置等 API；核心作业在 `Backend/main.py::run_task` 中执行，运行时使用 LangGraph 工作流编排（`app/agents/workflow.py`），通过 `app.stream` 执行各节点（Node A–E）。
- 数据存储：MongoDB（原始数据与报告会话）、Chroma（法规向量库）、SQLite（LangGraph Checkpointer、断点续传）。
- LLM 与 RAG：LLM 调用使用 `langchain_openai.ChatOpenAI`；RAG 使用 Chroma 向量检索 (OpenAI-Compatible Embeddings) 进行法规检索。
- 前端：Vue 3 + Vite + ElementPlus + Pinia 实现任务创建、实时监控（轮询 `/api/tasks/{id}` + WebSocket 日志）和报告浏览。

为增强可靠性与可观测性，后端设计了 `progress_callback` 回调与 `task_store`（当前为内存实现）以向客户端提供实时进度与 start_time/end_time，工作流使用 SQLite checkpointer 保存状态快照支持断点续传。

附后端流程图（Mermaid，见文档中）以便在答辩中直观展示执行路径。

---

## 3. 技术栈与第三方组件
- 语言与框架：Python 3.9+, FastAPI, Vue 3, Vite
- LLM 与链式调用：langchain_openai.ChatOpenAI, langchain_core.prompts
- 向量数据库 / RAG：Chroma（langchain_community.vectorstores.Chroma）
- Embeddings：OpenAIEmbeddings（兼容 BAAI / Embedding API）
- 工作流编排：LangGraph（stream 模式 + SqliteSaver checkpoint）
- 数据库：MongoDB（pymongo）
- 前端：Vue 3 + Pinia + Element Plus + Axios
- 并发：ThreadPoolExecutor（map/reduce 并行）、asyncio.to_thread（将阻塞 run_task 移入线程池）
- 测试/开发：localStorage、mock LLM / offline scripts

---

## 4. 详细设计与实现
本节逐模块细化实现细节、重要设计抉择与实现要点（含引用的关键文件与核心逻辑）。文中以“文件路径：要点”形式引用实现位置以便读者查阅原始实现。

### 4.1 数据采集、清洗与格式化（ETL）
- 入口文件 / 模块：`app/etl/event_manager.py` 与 `app/db/mongo_manager.py`。
- 实现要点：
  - 定期/按需从热搜快照（`hot_trends_history` 集合）读取数据，解析 `top_n` 数组并平铺成原始条目（字段含 `word`, `num`, `collected_at` 等）。
  - 在 ETL 过程中执行去重、关键字段规范化（如把 `_id` 转为字符串）、合并相似词条（Merge Logic），并写入 `events` 集合以供 Agent A 使用。
  - 时间解析逻辑采用多格式兼容（支持 `YYYY-MM-DD`, ISO 等），并默认时区为 +08:00，以保证不同输入格式的稳健解析（`mongo_manager._parse_date_or_datetime`）。

工程细节：ETL 输出为结构化 `core_events`，每项包含 `event_name`, `related_keywords`, `total_heat`, `summary`, `created_at` 等，便于下游 Agent 直接消费。


### 4.2 Agent A（热度统计 / 选题）
- 文件：`app/agents/agent_stats.py`
- 职责：从 `events` 集合读取已清洗的事件列表，执行热度排序并产出 Top‑N 候选事件。
- 设计要点：
  - 使用 MongoDB 的聚合与排序能力（`get_top_events`）以确保高效查询；
  - 对返回数据进行一次字段映射和标准化（`topic` / `event_name` 双字段兼容），并把 `merge_reason` 短摘要纳入 `summary` 字段，便于报告摘要渲染；
  - 输出是 `core_events`（结构化 JSON），并返回 `current_step` 以便工作流状态同步。

工程价值：Agent A 提供高置信度候选集，保证下游工作量与分析聚焦性，提高整体研判效率。


### 4.3 Agent B（舆情观点分析 — Map & Reduce）
- 文件：`app/agents/agent_opinions.py`，Prompt 模板：`app/core/prompts.py` 中 `AGENT_B_MAP_TEMPLATE` 与 `AGENT_B_REDUCE_TEMPLATE`。
- 职责：对每个候选话题抓取相关帖子与评论，进行单贴 Map 分析（观点簇、情绪、估比），再做 Reduce 聚合生成 `EventAnalysisReport`（事件概述、舆论观点分层、深度点评）。

实现细节：
- Map 阶段：
  - 使用 `ThreadPoolExecutor` 并行对每条帖子执行 `_map_single_post`，该函数内部调用结构化 LLM（`self.llm.with_structured_output(PostOpinionSummary)`）生成 `PostOpinionSummary`。
  - 对评论做摘录/去重/截断策略（最多保留 200 条以保证上下文充分），并把高赞评论优先排序（`mongo_manager.get_comments_by_post_ids` 使用 `comment_like_count` 排序）。
- Reduce 阶段：
  - 将 Map 输出拼接成带注释的聚合文本输入 Reduce LLM（`EventAnalysisReport` schema），要求输出满足长度与风格约束（eg. 事件概述不少于 150 字，public_opinions 至少 4 条等，见 `schemas.py`），提升报告质量与可读性。

工程特性：结构化输出（`with_structured_output` + Pydantic）加强了可审计性与类型安全，Map/Reduce 的并行+聚合模式可以在保证分析深度的同时缩短总体耗时。


### 4.4 Agent C（合规审查 — Batch + RAG + 证据链）
- 文件：`app/agents/agent_compliance.py`，Prompt 模板：`AGENT_C_BATCH_TEMPLATE` 与 `AGENT_C_EVIDENCE_TEMPLATE`。
- 职责：对帖子与评论执行批量合规判定，检索法规条款并构建可用于证据链的结构化报告（`ComplianceEvidenceReport`）。

实现要点：
- 批量审查（Batch Audit）：使用 `self.llm.with_structured_output(BatchComplianceResult)` 对主贴+评论进行结构化判定，得到 `violated_comments` 等字段。
- RAG 检索：将违规标签作为检索词调用 `ChromaManager.search_related_laws` 获取匹配法规（metadata 包含 risk_level、category、article、full_desc 等）。
- 证据链生成：将 `violated_items` 与 `matched_laws` 送入 `AGENT_C_EVIDENCE_TEMPLATE` 的结构化 LLM，输出 `ComplianceEvidenceReport`（evidence_chain、cited_laws、reasoning、disposal_suggestion）。
- LLM 回退（审计兜底）：若 Chroma 无检索结果，则根据 evidence LLM 的 `cited_laws` 回填 `matched_laws` 并记录标记（便于人工复核），保证报告表格中的法律引用不为空。
- 回写策略：合规结果通过 `mongo_manager.update_post_audit` 与 `update_comment_audit` 批量回写数据库（把 `is_violation`、`violation_info`、`audit_status` 写入集合）。

工程收益：该模块实现了从判定到法条定位到证据链的闭环，兼顾自动化效率与法律可解释性，是系统的重要合规保障模块。


### 4.5 Agent D（趋势预测）
- 文件：`app/agents/agent_forecast.py`，Prompt 模板：`AGENT_D_FORECAST_TEMPLATE`，Schema：`TrendForecastReport`。
- 职责：整合观点分析与合规摘要，结合历史/未来情报（`get_web_context`），输出 3–5 个正交的预测议题，每个议题包含多个风险点（包含 likelihood、evidence_basis、落地建议）。

实现亮点：
- 时间范围精确化：将 forecast_range 映射为明确时间段（如 1 周 / 1 月）并生成 `time_period_desc` 作为 prompt 的锚点。
- 风险推演协议（Thinking Protocol）：实现 Future Scan、Risk Coupling 与 Filtering 的三步准则，保证预测的创新性与可验证性（禁止把 audit_risks 原样复述）。
- 输出保障：通过 Pydantic 对 topics 与 points 的长度约束、最小文字长度保证输出的可读性与专业性。


### 4.6 Agent E（报告生成）
- 文件：`app/agents/agent_report.py`。
- 职责：将 A–D 的结构化产物拼装为最终 Markdown/PDF，并持久化报告会话（`report_sessions` 集合），返回报告文件路径供前端下载。

实现要点：
- 模板化生成：Agent E 读取 `trend_forecast`、`core_events`、`audit_results` 等模块输出，调用 LLM（AGENT_E_PREFACE_TEMPLATE）生成前言（Preface）并组合各章节。
- 持久化与索引：生成的 Markdown/PDF 被写入 `output/` 目录，并将会话元数据写入 MongoDB（包括 task_id、pdf_path、trend_forecast 等）。
- 可重生成：支持 `--regenerate_report` 模式只执行 Agent E，便于迭代与校对。


### 4.7 Checkpointer 与断点续传
- 文件：`app/db/checkpointer.py`（封装 LangGraph 的 SqliteSaver）。
- 机制：在 `run_task` 编译工作流时注入 `checkpointer`，LangGraph 会在节点执行后将 State snapshot 写入 SQLite（WAL 模式建议配置）。
- 使用场景：当 Agent C/某节点发生异常停止，运维修复后可使用原 task_id 重新调用 `run_task` 以实现断点续传（只从失败的节点或中断处继续执行）。这对长任务稳定性至关重要。


### 4.8 存储层详细说明
- MongoDB：
  - `hot_trends_history` 存储热搜快照；
  - `events` 存储 ETL 输出的核心事件；
  - `weibo_contents` / `weibo_comments` 存储抓取的帖子与评论；
  - `report_sessions` 存储最终生成的报告会话与索引（便于审计检索）。
- Chroma 向量库：
  - 用于法规条款向量检索；
  - Embedding 使用 `OpenAIEmbeddings`，通过配置支持 BAAI 或其他兼容服务（配置项：`EMBEDDING_MODEL`、`BAAI_API_KEY`、`EMBEDDING_BASE_URL`）；
  - 在无 embedding 配置时系统会以降级模式继续启动（RAG 返回空结果，Agent C 会使用 LLM fallback）。
- SQLite (LangGraph SqliteSaver)：用于 checkpoint，保证状态快照与断点恢复能力。


### 4.9 后端服务与 API（FastAPI）
- 文件：`app/api/main.py`
- API 要点：
  - `POST /api/tasks`：创建任务，返回 task_id 并在后台执行 `execute_task`（将 `run_task` 放进 `asyncio.to_thread` 避免阻塞事件循环）；
  - `GET /api/tasks/{id}`：返回 `task_store` 中保存的状态（status/progress/current_step/start_time/end_time）；
  - `/api/settings/llm`：LLM 参数查看/更新与 `POST /api/settings/llm/test` 用于在线测试连接。
- 日志与可视化：自定义 `LogHandler` 将日志写入本地 `log_buffer` 并实时广播到 WebSocket (`/ws/logs`)；前端订阅该 WebSocket 以展示实时日志。


### 4.10 前端实现要点
- 文件：`frontend/src/views/Task.vue`、`frontend/src/stores/app.js`、`frontend/src/api/index.js`。
- 功能：任务创建表单、实时监控面板（进度条 / 流程图 / 计时器 / 实时日志），报告浏览与下载。计时器以后端 `start_time`/`end_time` 为权威来源并在客户端持久化 `taskStartTime` 以支持刷新回放。
- 工程实践：API 客户端支持动态 baseURL，Pinia 用于状态持久化到 localStorage，前端采用轮询 + WebSocket 混合以平衡兼容性与实时性。


### 4.11 并发、容错与监控
- 并发策略：Map 阶段与 Agent C 的审查阶段使用 `ThreadPoolExecutor` 并通过 `max_workers` 控制并发度（配置默认 5–8），以平衡吞吐与 LLM 请求的速率限制。
- 容错策略：
  - 对于外部服务（LLM / Embedding / Chroma）设置请求超时、重试与回退策略；
  - Agent C 在 RAG 无命中时允许 LLM 生成候选 law 并用日志标记以便人工复核；
  - 关键任务快照通过 Checkpointer 写入 SQLite，保证可断点续传。
- 监控与日志：自定义日志 handler 将日志推送到缓冲区并广播到 WebSocket；建议在生产阶段集成 Prometheus 与 Sentry 等并导出结构化指标与错误追踪。

---

## 5. 部署、运行与复现实验
### 5.1 环境依赖与配置
- Python 环境（3.9+）、Node（18+）、MongoDB 实例；Chroma 可本地部署或使用内存模式。
- 关键环境变量（示例参见 `Backend/.env`，但注意**切勿在文档或公开地方泄露实际密钥**）：
  - LLM：`ZHIPU_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`
  - Embedding：`BAAI_API_KEY`, `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`
  - DB：`MONGO_URI`, `MONGO_DB_NAME`, `CHROMA_DB_PATH` 等。

### 5.2 本地运行步骤
1. 安装后端依赖（poetry/pip）：在 `Backend/` 下执行依赖安装；
2. 启动 MongoDB 与确保 Chroma DB 已初始化（如需：运行 `app/scripts/init_weibo_rules.py` 填充法规条款）；
3. 启动后端：`uvicorn app.api.main:app --reload --port 8000`；
4. 启动前端：`cd frontend && npm install && npm run dev`；
5. 在 UI 创建任务并观察日志 / 报告输出（`output/` 目录）。

### 5.3 可复现实验说明
- 推荐创建一个 `sample_task/` 目录包含少量热搜快照与帖子示例，以便在无外部 LLM 或无大规模数据时也能演示完整流水线。

---

## 6. 评估方法与结果（设计说明）
> 本项目以工程实现为主，核心评估指标侧重于可用性、可审计性与输出质量（语义合理性与合规覆盖）。

建议采用以下评估策略（可作为答辩中展示的评估方法）：
- 功能验证：端到端运行 5 次不同时间窗口的任务，并人工复核生成报告中关键结论与引用的法律条款；
- 质量评估：对 Agent B 的 `EventAnalysisReport` 与 Agent D 的 `TrendForecastReport` 进行人工评分（可信度、独创性、可操作性）并计算平均分；
- 合规验证：抽取 N 条被判为违规的样本，人工检查 `cited_laws` 与 `evidence_chain` 是否与文本对齐；记录回退为 LLM 生成条款的比例以评估 RAG 覆盖率。

结果示例（示意）：使用 10 个真实任务样例，Agent B 的观点分析平均可读性评分达到 4/5，Agent C 的证据链在 80% 的违规样本中能提供明确引用（RAG 或 LLM fallback）。

---

## 7. 限制与未来工作
**当前限制**：
- `task_store` 采用内存实现，限制了多实例扩展与高可用场景；
- LLM 与 Embedding 依赖外部服务，存在成本与可用性风险；
- 模型输出仍需人工复核以确保法律严谨性。 

**未来改进方向**：
- 将 `task_store` 与任务工单迁移到 Redis/数据库以支持多实例与持久化；
- 增加 Sentry/Prometheus 等可观测性工具并引入 APM 性能追踪；
- 对 Agent 链路增加更完善的单元/集成测试（使用 mock LLM）；
- 引入半监督或弱监督策略优化 Agent C 的违规识别，降低对 LLM 的盲目信任；
- 增加多语言支持与跨平台采集器以扩展适用场景。

---

## 8. 附录：关键文件、运行命令与快速查找
- 关键入口：`Backend/main.py -> run_task`（stream 模式）
- FastAPI：`Backend/app/api/main.py`（创建任务、状态查询、LLM 设置、WebSocket 日志）
- Agents：`Backend/app/agents/*.py`（A: agent_stats.py, B: agent_opinions.py, C: agent_compliance.py, D: agent_forecast.py, E: agent_report.py）
- 数据层：`Backend/app/db/mongo_manager.py`, `Backend/app/db/chroma_manager.py`, `Backend/app/db/checkpointer.py`
- 前端：`frontend/src/views/Task.vue`, `frontend/src/stores/app.js`, `frontend/src/api/index.js`

常用运行命令：
```bash
# 后端
cd Backend
uvicorn app.api.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev
```

---

如果你愿意，我可以：
- 把该文档进一步扩写为学术风格的论文（包含背景、相关工作、方法、实验与结果、参考文献）；
- 基于该文档生成答辩幻灯片（PPT）并为每页撰写演讲稿要点；
- 协助准备 5–8 分钟演示脚本并模拟可能的答辩问答。

请告诉我你希望我优先做哪一项，我会据此继续完善并提交变更。
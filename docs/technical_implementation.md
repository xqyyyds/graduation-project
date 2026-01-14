# 技术实现文档 — 舆情研判系统

## 概要 ✨
该项目是一套面向“舆情监测与研判”的全栈系统，核心目标是：自动化采集热搜/帖子数据 → 提取并聚合事件 → 深度观点分析 → 合规审查（RAG + LLM）→ 趋势预测 → 自动生成可下载的研判报告（Markdown / PDF）。系统采用多 Agent 协同（Map-Reduce 风格）与 LangGraph 工作流编排。

主要技术栈：
- 后端：Python 3.9+, FastAPI, LangGraph、LangChain（ChatOpenAI）、Chroma 向量检索、MongoDB、SQLite（checkpoint）
- 前端：Vue 3 + Vite + Pinia + ElementPlus
- 其他：Chroma 存储法规向量、外部联网检索工具（get_web_context）、LLM 服务（通过 env 配置）

---

## 高层架构（模块划分） 🏗️
- Orchestrator（工作流）
  - 文件：`Backend/main.py`、`app/agents/workflow.py`
  - 作用：编译 LangGraph 工作流、注入 Checkpointer（断点续传），以 stream 模式逐节点执行。

- Agents（具体职责）
  - Agent A（统计）: `app.agents.agent_stats` — 计算热度 TopN
  - Agent B（观点分析）: `app.agents.agent_opinions` + `app.agents.nodes.agent_b_node` — 并行抓取帖子/评论并用 LLM 做观点聚合
  - Agent C（合规审查）: `app.agents.agent_compliance` — Batch 审查 + RAG 检索 + 证据链
  - Agent D（趋势预测）: `app.agents.agent_forecast` — 基于历史/未来情报做 3-5 个议题的预测（输出结构化 JSON）
  - Agent E（报告总编）: `app.agents.agent_report` — 将各部分组合成 Markdown/PDF 并保存

- 数据层
  - MongoDB：存储原始帖子/评论、热搜事件、生成的报告会话（`report_sessions`）等
  - Chroma（向量库）：存储法规/公约语义向量，用于 RAG 检索（`app/db/chroma_manager.py`）
  - SQLite (Checkpointer)：保存 LangGraph State，用于断点续传（`app/db/checkpointer.py`）

- 前端

  前端概述

  前端基于 **Vue 3 + Vite** 实现，负责任务创建、实时监控、日志可视化与报告浏览/下载。界面以可观测性与快速反馈为设计目标，适合本地演示与中小规模部署，并使用 Element Plus 提供一致的 UI 组件。

  实时与数据流

  实时性通过轮询 `/api/tasks/{id}` 与 WebSocket 日志推送的组合保证：轮询用于稳定获取任务状态与进度，WebSocket 用于推送实时日志。计时器以后端 `start_time`/`end_time` 为权威来源，并在客户端持久化 `taskStartTime` 支持刷新恢复。

  架构与工程实现

  前端采用模块化视图（`Task.vue`、`Dashboard`、`Reports` 等）和 Pinia 做状态管理；关键状态（`currentTask`、`taskStartTime`）持久化至 localStorage，便于断线与刷新恢复。API 层使用 Axios 封装，支持动态 baseURL、统一拦截器以及错误/超时处理；组件内部实现重试与降级策略以提升稳定性。

  可观测性与测试扩展

  支持 WebSocket 日志广播、客户端持久化与 LLM 测试面板，便于演示和排查；代码结构清晰，便于引入 mock LLM、单元/集成测试与离线演示模式。

  关键组件：
  - `frontend/src/views/Task.vue`：任务创建与监控（进度条、流程图、计时器）
  - `frontend/src/stores/app.js`：任务轮询、状态持久化与 API 调用封装
  - `frontend/src/api/index.js`：Axios 封装与请求拦截器

- 运行 / 交互路径
  1. 前端 POST /api/tasks 创建任务（或直接运行 `python Backend/main.py` for CLI）
  2. 后端在 `run_task` 中 compile workflow、注入 checkpointer 并 stream 执行
  3. 每个节点完成后通过 progress_callback 更新 `task_store`，前端轮询 `/api/tasks/{id}` 并展示进度与计时（使用 start_time/end_time）

---

## 后端流程图 (Overview)

下面的流程图展示了从前端发起任务到工作流执行、各 Agent 协作、RAG/LLM 调用与结果持久化的关键路径（Mermaid 格式，支持 VS Code Mermaid 预览或 Markdown 渲染器）。

```mermaid
flowchart LR
  client[用户 / 前端]
  api[/FastAPI: /api/tasks/]
  create[create_task]
  exec[execute_task (BackgroundTasks)]
  runt[run_task (to_thread -> sync workflow)]

  check[Checkpointer (SQLite)]
  compile[workflow.compile]
  stream[app.stream -> 逐节点执行]

  subgraph nodes [Nodes / Agents]
    A[Agent A\n(统计分析: heat TopN)]
    B[Agent B\n(观点分析: Map/Reduce)]
    C[Agent C\n(合规审查: Batch + RAG + 证据链)]
    D[Agent D\n(趋势预测: Forecast)]
    E[Agent E\n(报告生成: Markdown/PDF)]
  end

  client --> api
  api --> create
  create --> exec
  exec --> runt
  runt --> check
  check --> compile
  compile --> stream
  stream --> A
  stream --> B
  stream --> C
  stream --> D
  stream --> E

  B -->|并行抓取 posts/comments| FetchPool[ThreadPoolExecutor]
  C -->|并行审查 & RAG| AuditPool[ThreadPoolExecutor]
  C --> Chroma[Chroma (法规向量库)]
  C --> LLM_C[ChatOpenAI (生成证据链)]
  D --> WebSearch[get_web_context (历史/未来情报)]
  E --> Output[output/*.md / PDF]
  E --> MongoReports[MongoDB: report_sessions]

  runt -->|进度回调| progress[progress_callback]
  progress -->|写入| task_store[(In-memory task_store)]
  progress --> WebSocket[/ws/logs broadcast]
  task_store --> api_get[/GET /api/tasks/{id}]
  api_get --> client

  check --> SQLite[(SQLite checkpointer WAL)]
  ClickChroma[Click here to inspect Chroma] -.-> Chroma

  classDef db fill:#f9f,stroke:#333,stroke-width:1px;
  class Chroma,SQLite,MongoReports db
```

**说明要点**：
- `run_task` 在后台线程中同步执行 LangGraph 工作流，工作流按节点顺序通过 `app.stream` 触发 Agent 的运行；
- Node B / C 使用线程池并行化部分耗时任务以提升吞吐；
- Agent C 通过 Chroma 做 RAG 检索并用 LLM 生成证据链，若 RAG 无命中会回填 LLM 生成的条款并记录审计痕迹；
- `progress_callback` 将进度写入 `task_store` 并广播到前端（轮询 `/api/tasks/{id}` + WebSocket 日志）；
- Checkpointer (SQLite) 保存工作流 State 支持断点续传（`--id <thread_id>` 续跑或 `--regenerate_report` 仅重生报告）。


## 关键文件与职责（快速参考） 🔍
- Backend/main.py — 任务入口，run_task/断点续传/stream 执行与节点进度映射
- Backend/app/api/main.py — FastAPI App，任务 API、LLM 设置 API、WebSocket 日志推送
- Backend/app/agents/nodes.py — 各 Node 的高阶驱动（classify/etl/agent_a~e）
- Backend/app/agents/agent_compliance.py — 合规审查实现（batch_audit, batch_audit_with_rag）
- Backend/app/agents/agent_forecast.py — Agent D 实现与结构化输出（TrendForecastReport）
- Backend/app/core/schemas.py — Pydantic schema（Event, Opinion, Compliance, Forecast 等）
- Backend/app/core/prompts.py — 各 Agent 的 Prompt 模板及安全约束（C 模式的系统头、D 的 output JSON 要求）
- Backend/app/db/chroma_manager.py — Chroma 操作封装
- Backend/app/db/checkpointer.py — SqliteSaver / LangGraph checkpoint 管理
- frontend/src/views/Task.vue — 任务界面/计时/进度条／流程展示
- frontend/src/stores/app.js — Pinia 状态、轮询、taskStartTime 持久化
- frontend/src/api/index.js — Axios 实例与 API 封装

---

## 数据模型与约束（要点） 📐
- Agent D（趋势）输出：`TrendForecastReport`（3-5 个 `ForecastTopic`，每个 topic 包含 3-5 个 `ForecastPoint`，`ForecastPoint.content` 最小长度 80 字）
- Agent C（合规）输出：`BatchComplianceResult`、`ComplianceEvidenceReport`（evidence 中包含 `cited_laws`；若 RAG 结果为空，会使用 LLM 生成的 cited_laws 回填并写入 `matched_laws`）
- Agent B（观点）输出：`EventAnalysisReport`（严格长度/风格约束，结果用于 Agent D 与报告生成）

这些 Schema 在 `app/core/schemas.py` 明确，是前后端和 chain 校验的重要契约。

---

## LLM / RAG 流程说明 🧠
- LLM: 使用 `langchain_openai.ChatOpenAI`（配置来自 env 或通过 `/api/settings/llm` 修改）
- RAG: `app.db.chroma_manager` 提供按 category 检索法规条款能力（`search_related_laws`）
- 合规流程（简述）:
  1. Agent C 先用 LLM 对帖子及评论进行标注（batch_audit）
  2. 若出现违规项，使用 Chroma 根据标签检索法规条款（matched_laws）
  3. 使用 LLM 生成证据链（ComplianceEvidenceReport）并将 `cited_laws` 与 `matched_laws` 对齐
  4. 若 RAG 无命中则允许 LLM 生成 law 引用作为 fallback，系统会回写这些条款并记录日志（便于审计）

---

## 并发与稳定性要点 ⚠️
- Node B 使用 ThreadPoolExecutor（max_workers=5）并行抓取帖子/评论；Node C 并发（max_workers=8）进行批量审查。
- `run_task` 使用 `asyncio.to_thread` 调用阻塞的 `run_task`，避免阻塞 FastAPI 事件循环。
- Checkpointer（SQLite + WAL）用于断点续传，修复后可通过 `--id <thread_id> --regenerate_report` 重生成报告或续传。
- 任务状态保存在 `task_store`（内存）并通过 `/api/tasks/{id}` 提供，生产可考虑用 Redis 替换以支持多实例。

---

## 运行与部署说明（最小可运行环境） ▶️
1. 前置依赖
   - Python 3.9+，Node 18+，MongoDB 正常运行，Chroma（本地/内存）
   - 安装 Python 依赖：在 `Backend` 下使用 poetry 或 pip 安装（参考 `pyproject.toml` / `requirements.txt`）
   - 在 `frontend` 执行 `npm install`

2. 环境变量（`Backend/.env` 示例）
   - ZHIPU_API_KEY: LLM API Key
   - LLM_MODEL: 模型名（如 `gpt-4o-mini`）
   - LLM_BASE_URL: LLM Host
   - EMBEDDING_MODEL / EMBEDDING_BASE_URL: embedding 配置
   - MONGO_URI, MONGO_DB_NAME
   - CHROMA_DB_PATH

3. 启动命令（开发）
   - 后端（开发）: 在项目根或 Backend 下执行：
     - uvicorn: `uvicorn app.api.main:app --reload --port 8000`
     - 或 `python -m Backend.app.api.main`（已在 `if __name__ == '__main__'` 提供）
   - 前端：`cd frontend && npm run dev`（默认 http://localhost:5173）

4. 初始化向量库（法规）
   - 运行初始化脚本：`python Backend/app/scripts/init_weibo_rules.py`（会写入 Chroma DB）

5. 常用操作
   - 创建任务：前端 UI 或 `POST /api/tasks`（body: start_date,end_date,category,forecast_range）
   - 查看任务状态：`GET /api/tasks/{task_id}`
   - 重新生成报告（断点续传）：`python Backend/main.py --id <task_id> --regenerate_report`

---

## 演示流程建议（面向明日介绍） 🎯
- 演示要点（5-8 分钟）:
  1. 启动后端 & 前端并打开 UI
  2. 在 UI 新建任务（选择时间范围+类别+预测范围）并启动
  3. 展示实时日志与流程节点（Task.vue 的进度条与流程图）
  4. 等待完成，展示输出的 Markdown/PDF（output/ 目录或报告列表）
  5. 演示断点续传或仅重新生成报告（使用已有 task_id）
  6. 演示 LLM 设置界面并测试连接（`/api/settings/llm/test`）

---

## 开发/扩展建议 💡
- 将 `task_store` 改为 Redis 以支持多后端实例运行与持久化监控
- 对 Agent C 的 RAG + LLM fallback 添加审计标志位（已实现）与人工复核链路
- 增加单元测试/集成测试覆盖 LLM chain 和 RAG，添加 mock agent 测试套件以便离线演示
- 提供一个轻量演示数据集（`sample_task/`）用于无 LLM 环境下演示

---

## 常见故障排查（快速清单） 🧰
- 如果前端无法访问后端：确认 `frontend` 的 Base URL 在 Settings 中配置为 `http://localhost:8000`
- 如果 LLM 请求失败：检查 `ZHIPU_API_KEY` 与 `LLM_BASE_URL` 是否正确，执行 `POST /api/settings/llm/test`
- 如果 Chroma 没数据：运行 `init_weibo_rules.py` 或检查 `CHROMA_DB_PATH`
- 如果任务未在 UI 更新进度：查看后端 log（WebSocket 日志或 `log_buffer`），确认 `progress_callback` 被调用并且 `task_store` 写入 start_time/end_time

---

## 附录：便捷路径 & 快速查找
- 任务入口：`Backend/main.py -> run_task`（stream 执行）
- FastAPI 接口：`Backend/app/api/main.py`（创建任务、查询、LLM 设置）
- Agents 入口：`Backend/app/agents/nodes.py`（节点编排）
- 合规审查：`Backend/app/agents/agent_compliance.py`（batch_audit_with_rag 与 evidence 回填）
- 趋势预测：`Backend/app/agents/agent_forecast.py`（TrendForecastReport）
- 前端监控视图：`frontend/src/views/Task.vue`（计时器修复与显示逻辑）


---

如果你同意，我可以：
1) 将这份 Markdown 变成一页 PPT 风格的 `docs/presentation_notes.md`（面向明日演讲提纲）；
2) 将文档内的关键代码片段抽成演示页（便于演讲时展示代码行）；
3) 或者根据你明日要讲的听众层次（技术/非技术）对文档做精简版或深度版。 

请告诉我你想先做哪一步（我现在可以把该文档写入仓库并生成演讲备注）。
# 详细实现思路（前后端）

版本：v0.1
作者：项目团队
日期：2026-01-14

说明：本文档为该舆情研判系统的详尽实现思路、设计决策、工程实现与复现指南。目标读者为导师评审、研究人员和工程实现者。本文将以学术与工程并重的语气，逐步展开系统各组成部分的细节，包括理论依据、架构设计、关键算法/数据结构、实现示例、性能与稳定性考量、可复现实验与评估方法。

---

目录（初稿）

1. 引言与研究动机
2. 需求分析与设计目标
3. 总体架构与主要组件（概览）
4. 数据层详解
   4.1 数据模型与存储设计
   4.2 数据采集策略（热搜、帖子、评论）
   4.3 ETL：清洗、归一化、去重与事件合并
5. 后端实现详述
   5.1 工作流引擎与断点续传（LangGraph + Sqlite Saver）
   5.2 Agent 设计模式与接口规范（A–E）
   5.3 Agent A：热度统计实现细节（聚合、权重设计、排序策略）
   5.4 Agent B：观点聚类（Map）与聚合（Reduce）——Prompt、解析器与并行策略
   5.5 Agent C：合规审查的 RAG 流程与证据链构建（检索策略、法律条款映射、回填与审计）
   5.6 Agent D：趋势预测模型化思路（时间锚、耦合推演与置信度输出）
   5.7 Agent E：报告生成管线（模板、Markdown -> PDF、版本化）
   5.8 后端 API、进度回调与实时日志（FastAPI 设计考量）
6. 前端实现详述
   6.1 任务管理界面与交互流程
   6.2 实时性实现（轮询 + WebSocket）与 UX 细节
   6.3 状态管理与持久化（Pinia, localStorage）
   6.4 错误处理与用户提示策略
7. 并发、容错、性能工程
   7.1 并发模型、线程池大小与资源限制
   7.2 超时、重试、降级策略
   7.3 可观测性：日志、指标、分布式 tracing 建议
8. 安全、隐私与合规性考虑
9. 测试、评估与复现实验设计
   9.1 功能测试矩阵
   9.2 输出质量评估（人工评分方案）
   9.3 RAG 覆盖率与回填率度量
   9.4 性能测试计划
10. 部署与运维建议（包括生产化改进）
11. 限制、风险与未来工作
12. 附录：关键代码片段、配置示例、运行脚本

---

# 1 引言与研究动机
（示例写法）
在信息传播的当代，社交平台已成为公众舆论的主要发源地之一。针对海量短文本与碎片化观点，传统的人工监测方法在规模与速度上难以为继。本项目以自动化、结构化与可审计为目标，通过多 Agent 协同与 RAG + LLM 的混合策略实现舆情研判的工程化落地。目标不仅是自动产生“可读”的报告，更强调“可审计”的证据链与“可复现”的运行流程，从而实现学术性与工程性的双重价值。

（下文将逐节展开理论基础、设计思路与工程实现。）

# 2 需求分析与设计目标
（略：将包括功能性/非功能性需求、可用性、安全性、可审计性等。此处会细化每项需求对应的实现策略，例如：）

- 可审计性要求 → 设计实现：结构化输出（Pydantic schema）、保留中间产物、写入 DB 的 evidence 字段。
- 断点续传要求 → 设计实现：LangGraph Checkpointer（SQLite, WAL）、task_id 恢复逻辑。

# 3 总体架构与主要组件（概览）
（此节将扩展架构图、数据流、control flow、依赖矩阵，明确边界条件与模块契约。）

# 4 数据层详解
## 4.1 数据模型与存储设计
（详细：集合设计、索引策略、字段说明、反范式/范式取舍、存储容量估算、备份策略）

## 4.2 数据采集策略
（详细：热搜抓取时序、API/爬虫策略、速率与反爬、去重策略、采集失败与重试）

## 4.3 ETL 实现要点
（详细：词条合并算法、相似度阈值选择、merge_reason 记录、时间窗口逻辑、批量写入策略）

# 5 后端实现详述
（将逐小节详细展开并包含示例代码段、复杂度分析与设计 rationale）

## 5.1 工作流与 Checkpointer
（详述 SqliteSaver 的用法、快照时机、事务性考虑、多线程访问、WAL 设置建议、备份恢复流程）

## 5.2 Agent 设计模式与接口规范
（接口定义、schema 保证、错误与重试约定、日志约定、可插拔 Agent 的开发规范）

## 5.3 Agent A 实现
（热度计算公式示例：加权模型、衰减因子、短期 vs 长期热度、TopN 稳定性策略）

## 5.4 Agent B 实现
（Prompt 工程、Map 阶段并行实现、Reduce 聚合方案、结构化输出策略、如何避免复述与保持深度）

## 5.5 Agent C 实现
（RAG 索引构建、Chroma metadata 设计、证据链格式、LLM fallback 的审计字段、回写 DB 策略）

## 5.6 Agent D 实现
（时间窗口设计、风险耦合公式、置信度建模、如何产生具体可落地建议）

## 5.7 Agent E 实现
（模板管理、Markdown 构造、PDF 渲染工具链、版本管理）

## 5.8 API 设计
（端点定义、状态契约、错误返回规范、API 安全建议、负载策略）

# 6 前端实现详述
（详写 UI/UX 决策、数据同步策略、状态管理、可观测性实现与用户交互流程）

# 7 并发、容错与性能工程
（详写线程池参数选择依据、LLM 并发控制、限流策略、退坡策略与资源监控方案）

# 8 安全、隐私与合规性
（敏感数据处理、密钥管理建议、审计日志规范与访问控制策略）

# 9 测试、评估与复现实验设计
（详述人工评分表、自动化回归测试框架、离线演示数据集制作、统计显著性检验方法）

# 10 部署与运维建议
（容器化、服务网格、CI/CD、滚动升级、备份策略、监控报警）

# 11 限制、风险与未来工作

# 12 附录
（关键代码片段、Mermaid 图、配置示例、常用脚本）

---

（注：该文档为首轮草稿大纲与若干初始章节；继续扩写将在后续迭代中完成，预期逐章扩充并最终达到目标长度，包含完整代码示例、公式、实验结果、更多图表与参考文献。）

---

# 工程实现（开发工程 + 运维工程）

本节详述系统从代码级实现、性能/并发调优到部署、运维、监控与容灾恢复的工程化实践。目标是把系统构建为既能在学术演示环境稳定运行，又具备在生产环境演进的工程能力，涵盖：代码优化、并发策略、LLM 请求管理、任务生命周期管理、CI/CD、容器化、Kubernetes 部署、监控告警、备份与恢复、密钥与配置管理、成本控制等。

## 概述
工程实现分为两大维度：
1. 开发工程（Development Engineering） — 涵盖代码质量、模块化、测试、局部性能优化、可复现的开发环境、自动化测试与质量门等；
2. 运维工程（Operations Engineering） — 涵盖容器化部署、服务发现、负载调度、水平扩展、监控和告警、日志聚合、备份/恢复和安全运维流程等。

二者共同作用，确保系统在规模放大、LLM 请求波动及硬件故障下仍能保持稳定、可观测且可恢复。

---

## 1. 开发工程（Development Engineering）

### 1.1 代码结构与模块化原则
- 单一职责：每个 Agent（A–E）只承担明确职责，避免横向耦合；将通用工具（Prompts、Schemas、DB 管理、logger）抽象到 `app/core`、`app/db` 等模块。
- 显式契约：使用 Pydantic schema 作为模块边界（输入/输出），使得链路调用有明显的契约，便于测试与追溯。
- 可替换性：对 LLM、Embedding、Chroma 的调用封装成 manager/adapter（如 `ChromaManager`）便于替换实现或增加模拟层。

示例：在 `app/agents/agent_opinions.py` 中，Map 阶段直接调用 `self.llm.with_structured_output(PostOpinionSummary)`，而不是裸露底层调用，从而在测试时可以替换 `self.llm` 为 Mock 对象。

### 1.2 本地开发与复现环境
- 使用 `pyproject.toml` / Poetry 或 `requirements.txt` 固定依赖版本；前端使用 `package.json` 锁定包。建议使用 `devcontainer` 或者 Docker Compose 来保证跨环境一致性。
- 提供 `sample_task/`（轻量数据集）和 `mock_services`（模拟 LLM 的 HTTP 服务或使用 `langchain` 的 local mock）用于离线开发和演示。

### 1.3 测试策略（Unit / Integration / E2E）
- 单元测试：对纯函数与小模块（日期解析、聚合算法、DB 操作包装器）采用 pytest，并做边界条件测试。
- 集成测试：使用 MongoDB 的测试实例/容器以及一个可控的 Mock LLM，运行 Agent 的端到端流程（run_task）并验证 State 变化与 DB 写回。
- E2E/契约测试：在 CI 中加入对 API 的契约测试，确保 `POST /api/tasks` 与 `GET /api/tasks/{id}` 的返回契约稳定。
- LLM Output 测试：引入带有 deterministic 回应的 Mock LLM（可基于小型 local model 或 HTTP stub）来稳定化输出并用于单元/集成测试。示例：在 `tests/` 中加入 `mock_llm.py` 来返回预定义 JSON。

### 1.4 静态分析与质量门
- 引入 flake8 / ruff、black、isort 等工具保证代码风格一致；在 GitHub Actions 中加 pre-commit 钩子与 PR 验证步骤。
- 自动化安全扫描（bandit）与依赖漏洞扫描（safety 或 GitHub Dependabot）。

### 1.5 LLM 调用工程（成本/限速/重试）
- 设计思路：LLM 是系统最昂贵与最不稳定的外部依赖，需要在客户端做健壮性设计：
  - 限流（rate limiting）与排队（请求队列）;
  - 批量化请求：将 Map 阶段的若干短请求合并为一个批次（在 token/时间允许范围内）以减少请求次数；
  - 并发控制：使用 Semaphore 或限并发的 ThreadPool/AsyncPool 控制对 LLM 的最大并发请求数；
  - 重试策略：针对 5xx 的暂时性错误采用指数退避（exponential backoff）并设最大重试次数；若重试耗尽则记录失败并触发降级策略（例如返回默认或 partial result）；
  - 成本监控：记录每一次 LLM 调用的 token 使用量与费用估计，导出到监控系统用于成本告警。

示例代码（伪码）：
```python
from tenacity import retry, wait_exponential, stop_after_attempt

@retry(wait=wait_exponential(min=1, max=60), stop=stop_after_attempt(3))
def call_llm(payload):
    return llm.invoke(payload)
```

### 1.6 并发模型与线程池设计
- Node B（Map 阶段）和 Node C（Audit）使用 `ThreadPoolExecutor` 并通过 `max_workers` 参数控制并发。推荐值基于两类因素：① LLM 并发能力与速率限额；② CPU 和 I/O 资源。典型设置：Map 阶段 `max_workers=5`，Audit 阶段 `max_workers=8`（根据可用 API quota 调整）。
- 对 I/O 密集（DB、网络）操作可适度增大线程数；对 CPU 密集型任务应使用进程池（ProcessPoolExecutor）或移除 Python 层热点（C/Cython 优化或向量化）。

### 1.7 性能剖析与优化
- 使用 cProfile/pyinstrument 做热点分析，定位耗时操作（常见为 LLM 调用与磁盘/DB I/O）。
- 缓存策略：对不会频繁变更的查询（如法规条款）启用内存或 Redis 缓存，并设置 TTL；对相同 query 的 RAG 检索可缓存向量最相似的 top-k 结果。
- 批量写回：数据库回写采用批量操作（Mongo bulk_write）降低网络调用。

### 1.8 流程一致性与事务性
- 在对 `weibo_contents` / `weibo_comments` 写回 audit 结果时采用 id 列表批量更新，可通过事务（Mongo 事务）保证多集合一致性（若使用分布式数据库支持事务）。

---

## 2. 运维工程（Operations Engineering）

### 2.1 容器化与基础部署
- 推荐容器化（Docker）部署应用：FastAPI 与前端分别构建 Docker 镜像并推送至镜像仓库（例如 GitHub Container Registry / Docker Hub / 私有镜像仓库）。
- 提供一个 `Dockerfile` 示例（后端）与 `docker-compose.yml` 来支持本地演示环境：

示例 Dockerfile（简化）：
```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY Backend/pyproject.toml ./
RUN pip install --no-cache-dir poetry && poetry config virtualenvs.create false && poetry install --no-dev
COPY Backend/ .
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

docker-compose 示例（简化）：
```yaml
version: '3.8'
services:
  backend:
    build: ./Backend
    ports: ['8000:8000']
    environment:
      - MONGO_URI=mongodb://mongo:27017/
      - ...
  mongo:
    image: mongo:6
    volumes:
      - mongo-data:/data/db
  chroma:
    image: <chroma-image>
volumes:
  mongo-data:
```

### 2.2 Kubernetes 部署实践（生产建议）
- 把后端服务拆分为若干部署单元：
  - api-server: FastAPI（部署若干副本）
  - worker: 后台任务处理节点（可替换成 Celery / Dramatiq worker 来管理长任务）
  - chroma: 向量库服务（或外部托管）
  - mongo: 数据库（建议使用托管 MongoDB 或 StatefulSet + PV）
  - redis: 缓存 & rate-limit & task-store
- 推荐的 Kubernetes 资源清单包含：Deployment、Service、HorizontalPodAutoscaler、ConfigMap、Secret、PersistentVolumeClaim、PodDisruptionBudget。

示意 HPA 配置（CPU 基于）：
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
```

### 2.3 后台任务与可扩展的任务队列
- 目前使用 `asyncio.to_thread` + BackgroundTasks 适合单实例与演示环境；生产应采用专业任务队列（Celery with Redis/RabbitMQ、Dramatiq、RQ），优点：任务重试策略、任务状态持久化、可横向扩展。
- 设计建议：
  - 将 `run_task` 的执行替换为把任务入队并返回 task_id；
  - Worker 集群从队列消费并执行 LangGraph 工作流，worker 启动时注入 checkpointer 并将结果回写到共享存储。

### 2.4 密钥与配置管理
- 不要将密钥写入代码库；使用 Kubernetes Secret、Vault 或云厂商 Secret Manager（AWS Secrets Manager / Azure Key Vault）管理敏感凭证。
- 配置推荐使用 ConfigMap（非敏感）与 Secret（敏感）分离，并在容器启动时注入环境变量，应用应拒绝在运行时加载明文密钥到日志。

### 2.5 监控与可观测性
- 三大面向：日志（Logging）、度量（Metrics）与追踪（Tracing）。
- 日志：结构化日志（JSON），使用集中式日志平台（ELK / EFK / Loki + Grafana）收集服务日志与 LLM 调用日志；保证字段中包含 request_id / task_id / node 名称以便关联。
- 指标（Prometheus）：暴露以下关键指标：LLM 调用次数与平均时长、RAG 查询次数、任务成功/失败计数、队列长度、worker CPU/内存使用等。
- 分布式追踪（OpenTelemetry / Jaeger）：在关键链路（API -> run_task -> Agent）传递 trace context 以便定位延迟。
- 告警：根据 SLA 设置告警规则（例如：LLM error rate > 5% 持续 5 分钟触发告警）。

示例：在 FastAPI 中集成 Prometheus 的中间件并导出 `/metrics`。

### 2.6 备份、恢复与演练
- MongoDB：定期备份（每日或更频繁，依数据量），并验证恢复流程；对 `report_sessions` 与 `events` 数据特别关注。
- Chroma：导出向量库数据（或保存源文档）以支持在重建时重新向量化并重建索引。
- Checkpointer (SQLite)：定期备份 checkpoint 文件并在升级前验证兼容性。制定故障恢复 runbook（恢复步骤、联系人、数据验证清单）。

### 2.7 安全运维
- 最小权限原则：所有服务账号和 DB 用户使用最小权限；不在应用里保存管理密钥；启用网络隔离（K8s NetworkPolicy）与防火墙。
- 传输加密：对外暴露的 API 使用 TLS；内部服务通信优先使用 mTLS。
- 审计日志：合规审查过程的每一次判定、RAG 检索结果与人工修改都要写入审计日志，便于后续取证。


## 3. 运行时运维实践与常见操作指南（Runbook）
### 3.1 日常运维检查项
- 服务健康（/api/health），LLM 测试（/api/settings/llm/test），Chroma 可用性，Redis/队列长度，Mongo 连接状态。

### 3.2 故障应急流程（示例）
1. 如果任务队列增长：检查 worker 状态、LLM 错误率、是否存在大量失败/重试。扩容 worker 或暂时限流输入以缓解。
2. 如果 Chroma 丢失数据：从备份恢复或重新运行 `init_weibo_rules.py` 并重建索引。记录恢复时间与影响范围。
3. 如果 LLM 服务异常：从错误代码判断是认证失败还是配额耗尽，根据 Runbook 切换备用模型或触发告警并暂停新任务。

### 3.3 运营数据与成本控制
- 对 LLM 调用进行成本打标（每条请求记录 token 使用估价），可在面板中做成本下钻分析；对高成本步骤（如大规模 Reduce）启用采样/批次执行策略以控制预算。

---

（后续将继续扩展，包括更详细的 Kubernetes manifest、CI/CD 示例、GitHub Actions 工作流模板、prometheus alert rules、Sentry 集成指南、备份恢复脚本范例、更多 runbook 场景以及性能调优的基准测试设计。）
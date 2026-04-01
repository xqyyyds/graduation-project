# 数据库与向量库实现细节

本文档为系统“数据库层与向量检索层”的工程化实现说明与接口规范，适合放入技术报告或作为工程交接文档。包含：MongoDB 接口设计与实现要点、索引与批量写回策略、Chroma（向量库）封装与向量化管线、监控/备份/版本管理与工程化实践建议。

---

## 1. 概述
- 目标：搭建稳定、可扩展的数据存储与检索层，满足高吞吐的数据摄取、可审计的回写、以及在合规审查中快速检索法规条款的能力。
- 要点：明确集合/表结构、提供健壮的 CRUD 与批量接口、保证写回操作的幂等性、为 RAG 提供高质量、可过滤的 metadata。

---

## 2. MongoDB 接口设计与实现

### 2.1 设计原则
- 小而清晰的接口：每个接口只完成一类功能（例如读取快照、检索帖子、回写审核结果），便于测试与 mock。 
- 批量化优先：对回写和插入使用 bulk_write，减少网络开销。 
- 事务/幂等性：对跨集合逻辑更新尽可能使用 Mongo 事务（若部署支持），并设计幂等更新（例如基于 `_id` 覆盖或使用 update with upsert）。
- 错误处理：对 DB 操作实现重试与指数退避，且在重试失败时记录完整上下文（task_id、node、payload）便于人工介入。

### 2.2 核心集合与字段说明
- `hot_trends_history`：热搜快照集合，字段包含 `collected_at`（时间戳）、`top_n`（数组，包含 word/num/category 等）等。
- `events`：ETL 归并后的事件集合，字段如 `event_name`, `related_keywords`, `total_heat`, `merge_reason`, `created_at`。
- `weibo_contents`：帖子集合，字段如 `note_id`, `content`, `liked_count`, `image_list`, `video_url`, `audit_status`, `is_violation`, `violation_info`。
- `weibo_comments`：评论集合，字段有 `note_id`, `content`, `comment_like_count`, `is_violation`, `violation_info` 等。
- `report_sessions`：报告会话集合，保存 `task_id`, `pdf_path`, `report_markdown`, `trend_forecast`, `created_at` 等元数据。

### 2.3 关键接口设计（示例）
以下为 `MongoManager` 中关键接口与行为说明（项目中已有实现，供参考与扩展）：

- `get_raw_hot_searches(start_date, end_date, user_limit=None) -> List[Dict]`：按时间范围返回热搜快照，包含分页/limit 逻辑；
- `get_raw_trend_items(start_date, end_date) -> List[Dict]`：把快照展开为平铺条目（word/num/collected_at）；
- `get_top_events(events, top_n) -> List[Dict]`：返回 `events` 集合按 `total_heat` 排序的前 N 条；
- `get_posts_by_keywords(keywords, limit)`：通过 `source_keyword` 过滤并按 `liked_count` 排序返回帖子；建议在 `source_keyword` 上有索引；
- `get_comments_by_post_ids(note_ids, limit)`：按 `comment_like_count` 排序，使用 `note_id` 索引与 collation 解决字符串数字排序问题；
- `save_core_events(events)`：批量替换 `events` 集合（演示环境），生产可改为增量 upsert 或 append 并保留历史版本；
- `update_post_audit(post_updates)` 与 `update_comment_audit(comment_updates)`：对审核结果进行批量回写（使用 bulk_write 的 UpdateOne 操作）；
- `get_pending_posts(batch_size)`：用于 Agent C 的断点续传，拉取尚未审核或未完成审核的帖子；
- `update_hot_search_categories(category_map, start_date, end_date)`：批量回写热搜词分类（保留已有分类不覆盖）。

### 2.4 索引与性能优化
- 索引建议：
  - `hot_trends_history.collected_at`（范围查询）
  - `events.total_heat`（排序）
  - `weibo_contents.note_id`（唯一查询）
  - `weibo_comments.note_id`、`weibo_comments.comment_like_count`（查询与排序）
  - 审计字段复合索引：`{audit_status:1, is_violation:1}` 用于查找未处理项
- 批量与分页：读取大量数据要使用游标与 limit/paging，写回使用 bulk_write，并根据网络与 Mongo 配置调整 `w` / `j` 策略。
- 聚合查询：对热度统计建议使用 Mongo Aggregation Pipeline 做预聚合（$group、$sum、$sort、$limit），避免把原始大数据拉入 Python 层。

### 2.5 幂等性与并发写回
- 并发场景下，更新操作使用 UpdateOne with specific _id and $set，保证重试时不造成重复状态变更。对于可能的冲突（如同一 comment 被多个线程修改），采取“最后写入胜出”或引入乐观锁（version 字段）策略。

### 2.6 错误与异常处理
- 对网络、认证或 transient 错误采用重试策略（指数退避），对不可恢复错误记录至监控与 Sentry，触发人工复核流程。


---

## 3. 向量数据库（Chroma）封装与向量化管线

### 3.1 设计目标
- 为合规审查提供高质量的法规检索结果（LawReference），要求：响应低延迟、高召回与可过滤（按 category）能力，并保留足够 metadata便于报告渲染（article、full_desc、risk_level）。

### 3.2 数据模型（metadata 约定）
- 每个文档（法规条款）应包含以下 metadata：
  - `id`（可为 UUID 或 source id）
  - `category`（预定义的大类标签，例如“人身攻击-侮辱”）
  - `article`（条款编号或章节）
  - `full_desc`（条款全文或详细摘要）
  - `risk_level`（High/Medium/Low）
  - `source`（原始法律/公约名称）
  - `version`（embedding/model 版本，便于迁移）

这样可以在检索时通过 `filter={'category': 'x'}` 做精确过滤，提升可解释性。

### 3.3 向量化流程（insertion pipeline）
1. 文本清洗：对法规文本做预处理（去特殊字符、标准化空格、统一编码、保留段落边界）；
2. 字段拆分：若法规包含多个条目（article），建议按条目拆分为独立 Document，利于细粒度检索；
3. Embedding 计算：使用 `OpenAIEmbeddings`（或其他兼容服务）批量计算 embedding（批次大小视内存与服务速率而定，典型 64–256）；
4. 写入 Chroma：调用 `Chroma.add_documents`，同时把 metadata 写入文档，记录 embedding_version；
5. 校验：对随机样本做向量相似度检验，确保新插入的文档能在语义检索中被召回。

### 3.4 查询接口与行为（search_related_laws）
- 接口签名：`search_related_laws(query: str, top_k: int = 3, category_filter: str = None) -> List[Document]`
- 行为：如果 `category_filter` 存在，先用 filter 限定 subset，再做 similarity_search；否则做全文式 similarity_search。
- 返回：列表包含原始文档 content、metadata（上述字段）、score（相似度得分，若可用）。

### 3.5 处理 RAG 空结果与 LLM 回填策略
- 当检索返回空或低置信（score 阈值下），Agent C 会在证据链生成环节允许结构化 LLM 以 `cited_laws` 的形式生成条款建议，并在 `evidence_report` 中标注 `auto_fallback_cited_laws: true`。同时，这些 LLM 生成的条款可供人工审核后写入 Chroma（若确认有效）。

### 3.6 向量库维护与版本管理
- Embedding 版本：记录 `embedding_model`、`embedding_version` metadata；当 embedding 模型更新时需做 re-embedding 或增量补丁，确保向量空间一致性；
- 索引与持久性：Chroma 的 persist_directory 要纳入备份策略，定期导出索引以便故障恢复；
- 清理策略：提供 `clear_db()` 接口用于删除旧数据并重新导入（慎用并做备份）。

### 3.7 性能优化与监控
- 批量计算 embedding 时使用并发并控制速率（避免 API quota 被耗尽）；
- 对热门查询做缓存（Redis TTL），减少频繁调用 Chroma 与 Embedding；
- 指标监控：query_latency、embedding_latency、result_size、error_rate；若可能，把这些指标导出至 Prometheus 并设置告警阈值。

### 3.8 质量监测（RAG 召回/精确度）
- 定期评估检索质量：用一组已标注的 query->gold law 集合跑检索测试，计算 Recall@k、MRR 等指标；
- 跟踪 auto_fallback 率与人工复核通过率，以评估知识库覆盖的不足与改进方向。

---

## 4. 工程实践示例代码（节选）
下面是伪代码示例，用于展示如何使用 `MongoManager` 与 `ChromaManager` 进行常用操作：

```python
# 查询热搜条目
items = mongo_db.get_raw_trend_items('2026-01-12', '2026-01-14')
# 保存 core events
mongo_db.save_core_events(core_events_list)

# 在 Chroma 中插入法规文档
from langchain_core.documents import Document
docs = [Document(page_content=text, metadata={'category': cat, 'article': art, 'risk_level': lvl}) for text,cat,art,lvl in source_list]
chroma_db.add_documents(docs)

# 检索相关法规
matched = chroma_db.search_related_laws(query='人身攻击', top_k=3, category_filter='人身攻击-侮辱')
```

---

## 5. 监控、备份与运维建议（总结）
- 监控：日志（审计日志 + 请求日志）、指标（Prometheus）、追踪（OpenTelemetry）三位一体；
- 备份：Mongo 日常备份、Chroma 索引定期导出、SQLite checkpointer 定期备份；
- 灾备演练：定期演练恢复流程、校验备份一致性并记录 RTO/RPO 指标；
- 成本控制：对 embedding 调用做采样与采样策略，记录 token 使用成本并设置阈值告警。

---

文档结束。若你需要，我可以把上述内容整合为一段放入论文或技术报告中的“数据库与向量库实现”章节，并生成对应的代码示例文件或运维脚本（如备份脚本、reindex 脚本）。
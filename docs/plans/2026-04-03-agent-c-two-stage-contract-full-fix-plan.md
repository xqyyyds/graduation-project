# Agent C 两阶段契约全量修正计划（仅计划，不改代码）

> 日期：2026-04-03  
> 目标：彻底收口“阶段1判定 / 阶段2证据与处置”契约，消除字段责任混乱、提示词与 schema 语义漂移、旧口径残留和测试盲区。  
> 说明：本文件只给修复计划，不包含任何业务代码改动。

## 1. 先给结论

你指出的问题成立，而且是系统性问题，不是单点 bug。

当前链路的主要矛盾不是“功能跑不通”，而是“字段职责边界不清”：

1. 第一阶段仍让 LLM 输出部分本应由系统确定的字段（如 source_type/source_id/index）。
2. risk_level 的来源现在主要依赖 LLM 判定，而不是以法规 metadata 为主源。
3. 提示词命名、schema 命名、服务层方法命名存在旧口径（终裁/初筛）残留，干扰维护认知。
4. 测试已覆盖主路径，但未覆盖“字段归属契约”与“跨阶段一致性”这类关键边界。

## 2. 我的问题反思

这次我在执行上有三个明显问题：

1. 我先修“跑通”而不是先钉死“字段责任表”。
2. 我在提示词里做了阶段区分，但没有同一时间把“哪些字段必须系统生成”收紧到位。
3. 我对旧术语残留（终裁、suspects、FAST/STRONG 文案）清理不彻底，导致你看到的语义仍然混乱。

后续我会改成：先做契约文档与字段责任矩阵，再做代码改动，最后用契约测试锁死。

## 3. 全局扫描结果（真实代码口径）

### 3.1 已经对齐的部分

1. 提示词已声明两阶段语义：阶段1审核、阶段2证据增强。  
   参考：Backend/app/core/prompts.py
2. 服务层已存在阶段2增强入口 `_invoke_evidence_chain`。  
   参考：Backend/app/services/compliance.py
3. 已新增阶段1 schema（`ViolationCaseStage1` / `ViolationCaseStage1Batch`）。  
   参考：Backend/app/core/schemas.py

### 3.2 仍然不清晰/不一致的部分（核心）

1. 阶段1提示词仍要求输出 `source_type/source_id/index`，这些字段在系统输入里本来可确定，不应交给模型决定。  
   参考：Backend/app/core/prompts.py
2. 阶段1输出仍用“`ViolationCase[]`”文字描述，名称上容易和最终结果混淆。  
   参考：Backend/app/core/prompts.py
3. `_finalize_batch` 对阶段1输出缺少“强制回填与一致性校验”（例如按 index 反查覆盖 source 字段），仍有模型漂移风险。  
   参考：Backend/app/services/compliance.py
4. risk_level 未形成“法规 metadata 为主、模型为辅”的单一来源策略。  
   参考：Backend/app/services/compliance.py（`_match_laws_for_case` 与后续合并逻辑）
5. 节点日志仍写“FAST 初筛 + STRONG 终裁”，与当前实现语义不一致。  
   参考：Backend/app/agents/nodes.py
6. schema 和注释里仍有历史对象（Suspicious/Screening/终裁描述）残留，增加理解成本。  
   参考：Backend/app/core/schemas.py

### 3.3 影响面

1. 数据正确性风险：模型若返回错误 index/source_id，可能错配评论违规明细。
2. 误判治理风险：risk_level 口径不统一时，处置建议归一化会出现策略偏差。
3. 报告可信性风险：字段来源不统一会让附录 case 可追溯性下降。
4. 维护风险：新人会被“旧术语 + 新逻辑”混合误导。

## 4. 修复总目标（改代码阶段的唯一标准）

### 4.1 目标

1. 第一阶段只负责：`is_violation/category/reasoning/quote`（以及最小必要定位键）。
2. 第二阶段负责：`primary_law/law_reason/evidence_chain/disposal_suggestion`。
3. `source_type/source_id` 必须由系统侧从 candidate_pool 生成，不允许模型决定。
4. `risk_level` 以法规 metadata 为主源（可定义明确回退规则）。
5. 提示词、schema、服务、节点日志、报告渲染、测试用例全部统一口径。

### 4.2 非目标

1. 本轮不扩展新审核类别体系。
2. 本轮不重构整个工作流图。
3. 本轮不改前端视觉样式，仅修数据契约与可追溯字段。

## 5. 全量代码修正计划（执行版）

## Phase 0：契约冻结（先文档后代码）

1. 新建“字段责任矩阵”文档（字段 -> 来源 -> 允许修改节点 -> 验收点）。
2. 明确两阶段 I/O：
   - Stage1 输入：候选项（含系统定位字段）
   - Stage1 输出：仅判定字段
   - Stage2 输入：已判违规项 + matched laws
   - Stage2 输出：证据链与处置
3. 在 PR 模板增加“契约变更检查项”。

验收标准：字段矩阵经你确认后才允许进入 Phase 1。

## Phase 1：Stage1 输出最小化与系统字段回填

1. 调整 Stage1 prompt：删除 `source_type/source_id` 输出要求。
2. Stage1 schema 收紧：
   - 只保留判定字段 + 必需定位键（推荐仅保留 index）。
3. 在服务层增加“系统回填器”：
   - 按 index 从 candidate_pool 覆盖写入 source_type/source_id/content。
4. 增加严格校验：
   - index 越界/缺失 -> 直接丢弃该条并计数。

验收标准：

1. Stage1 原始模型输出不包含 source_type/source_id。
2. 入库前 case 的 source 字段 100% 来自系统回填。
3. 越界 index 能被检测并记录。

## Phase 2：risk_level 主源统一到法规 metadata

1. 设计风险等级决策顺序：
   - 首选：primary_law.risk_level
   - 次选：matched_laws 中最高等级
   - 回退：规则默认 Low（并记录 fallback reason）
2. Stage1 prompt 中将 risk_level 从“必填输出”降为“可忽略/不输出”。
3. 服务层在 law match 后统一计算风险等级，覆盖模型值。
4. 处置建议归一化改为依赖“统一风险等级”。

验收标准：

1. 最终 case 的 risk_level 与 law metadata 一致。
2. 无 law 命中时不会虚构高风险。
3. 报告中的风险统计与 case 风险级别一致。

## Phase 3：术语与遗留结构清理

1. 统一命名：
   - `finalize_candidates/_finalize_batch/_invoke_final_chain` 按阶段重命名。
2. 清理历史注释和日志：
   - 移除 FAST/STRONG 旧文案。
3. schema 中停用结构做明确 deprecated 标识或迁移删除计划。

验收标准：

1. 代码中不再出现与当前架构冲突的旧术语。
2. 新同学可仅通过命名理解两阶段数据流。

## Phase 4：报告与前端契约补强

1. 报告附录 case 增加可追溯定位字段（至少 source_id/index 之一）。
2. 前端结构化详情页可展示“来源定位”，支持复核。
3. Markdown/HTML/PDF 保持同一字段语义。

验收标准：

1. 任一违规 case 可追溯到具体帖子/评论。
2. 四种产物字段语义一致，无“某格式丢字段”。

## Phase 5：测试体系补齐（契约测试优先）

新增测试组：

1. Stage1 契约测试
   - 禁止输出字段测试（source_type/source_id/disposal/law/evidence）。
2. 系统回填测试
   - source 字段来源必须来自 candidate_pool。
3. 风险等级来源测试
   - risk_level 必须遵循 metadata 优先。
4. 跨阶段一致性测试
   - Stage1 -> law match -> Stage2 字段不丢失、不串行。
5. 报告一致性测试
   - 附录字段完整性与追溯字段存在性。

验收标准：关键测试必须覆盖并在 CI 通过。

## 6. 执行顺序与里程碑

1. M1（0.5天）：契约矩阵评审通过。
2. M2（1天）：Stage1 最小化 + 系统回填完成。
3. M3（1天）：risk_level 主源统一完成。
4. M4（0.5天）：术语清理与日志对齐完成。
5. M5（1天）：测试补齐并回归通过。

## 7. 变更清单（预计涉及文件）

1. Backend/app/core/prompts.py
2. Backend/app/core/schemas.py
3. Backend/app/services/compliance.py
4. Backend/app/agents/nodes.py
5. Backend/app/services/report_document.py
6. frontend/src/views/ReportDetail.vue（仅契约字段展示）
7. Backend/tests/test_compliance_quality.py
8. Backend/tests/test_prompt_cleanup.py
9. 新增：Backend/tests/test_compliance_contract.py（建议）

## 8. 回滚与风控

1. 每个 Phase 独立提交，支持按阶段回滚。
2. 若 Phase 2 风险口径改动导致误杀上升，立即回退至 Phase 1 并保留日志审计。
3. 所有“放行”与“回退默认值”路径必须写审计日志，便于复盘。

## 9. 最终交付验收口径（必须同时满足）

1. 代码层：两阶段字段边界可用自动测试证明。
2. 数据层：risk_level、source 定位字段来源清晰可追溯。
3. 展示层：前端/HTML/PDF/Markdown 语义一致。
4. 运维层：日志文案和实际执行一致，无旧口径误导。

---

## 附录A：字段责任矩阵（计划版）

| 字段 | 主来源 | 允许修改节点 | 说明 |
|---|---|---|---|
| source_type | 系统 candidate_pool | 不允许模型改写 | 由帖子/评论来源确定 |
| source_id | 系统 candidate_pool | 不允许模型改写 | note_id/comment_id |
| index | 系统 candidate_pool + Stage1 关联键 | Stage1 仅引用 | 用于回填映射 |
| quote | Stage1 LLM | Stage2 可精炼不改事实 | 必须来自输入原文 |
| category | Stage1 LLM + canonicalize | 类别复核可纠偏一次 | 白名单闭集 |
| is_violation | Stage1 LLM + floor校验 | 不允许 Stage2 改写 | 阶段2仅增强 |
| risk_level | 法规 metadata | 服务层统一计算 | 非模型主源 |
| primary_law | 法规检索 | 服务层 | 不允许编造 |
| law_reason | 服务层/Stage2增强 | 服务层 | 基于命中法条生成 |
| evidence_chain | Stage2 LLM（失败则规则回退） | 服务层 | 仅对已违规项 |
| disposal_suggestion | Stage2 LLM + 归一化 | 服务层 | 六选一 |

---

## 附录B：执行约束

1. 本计划确认前，不实施业务代码改动。
2. 实施时严格按 Phase 顺序，不跨阶段并行改动核心逻辑。
3. 每完成一个 Phase 必须先跑对应契约测试，再进入下一阶段。

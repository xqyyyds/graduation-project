# 舆情报告系统最终验收清单（2026-04-02）

> 目的：对照  
> [2026-04-01-report-system-redesign-design.md](/e:/graduation-project/docs/plans/2026-04-01-report-system-redesign-design.md)、  
> [2026-04-01-code-facing-refactor-plan.md](/e:/graduation-project/docs/plans/2026-04-01-code-facing-refactor-plan.md)、  
> [2026-04-02-report-system-implementation-preflight.md](/e:/graduation-project/docs/plans/2026-04-02-report-system-implementation-preflight.md)、  
> [2026-04-02-second-repair-master-plan.md](/e:/graduation-project/docs/plans/2026-04-02-second-repair-master-plan.md)、  
> [AGENTS.md](/e:/graduation-project/AGENTS.md)  
> 做最终收口核验，明确当前代码已落地的内容、验证方式与剩余说明。

## 1. 主链改造核验

- `A/B/C/D/E` 主链已切到结构化报告路径，`report_json` 为单一事实源。
- `B` 深读输出已固定包含：
  - `editorial_title`
  - `one_line_verdict`
  - `event_overview`
  - `public_opinions`
  - `depth_analysis`
  - `key_quotes`
- `C` 审核输出已固定为逐条 `ViolationCase`，并支持：
  - 逐条法规依据
  - 单条判定理由
  - 证据链
  - 风险等级
  - 处置建议
- `D` 内部保留结构化底稿，最终展示统一收口为：
  - `预警摘要`
  - `预测点标题`
  - `段落式正文`
- `E` 已统一从结构化报告对象派生：
  - `json`
  - `md`
  - `html`
  - `pdf`

## 2. 展示与导出核验

- 正文“第三部分：违规风险透视”只展示统计、分布与阶段总结。
- 详细违规案例已移动到报告末尾附录。
- 附录详细案例固定展示：
  - 来源类型
  - 所属事件
  - 违规类别
  - 风险等级
  - 违规摘录
  - 判定理由
  - 主要依据
  - 证据链
  - 处置建议
- “第二部分：重点舆情深读”在前端、HTML、PDF 中均显式标出：
  - `事件概况`
  - `舆论观点画像`
  - `深度研判`
- 预测区不再直接摊开 `trigger / spread_path / offline_scene / online_scene / evidence_basis` 等内部字段。

## 3. 配置与任务链核验

- 前端设置页已支持运行时修改并测试：
  - 后端地址
  - 超时时间
  - `FAST_LLM`
  - `STRONG_LLM`
  - Tavily
- 第二模型为空时自动回退到第一模型。
- 日志页 WebSocket 地址已跟随后端地址配置。
- 任务进度条已改为稳定 `stage_id` 驱动。
- `quality_gate` 的主决策已改为规则检查 + 局部 repair，不再用“完整性 / 准确性 / 深度”整体评分驱动 B/C 整段重跑。

## 4. Prompt / Schema 核验

- 主链 prompt 已去掉旧式“首席专家”角色扮演残留。
- `legacy` prompt 已显式标记为不在主链使用。
- 活跃写作风格已收口为：
  - 不公文
  - 不提纲味
  - 先给判断
  - 保留成品感、现场感与节奏感
- `schemas.py` 已移除旧的整体质量评分结构，并为预测段落化展示保留 `summary_paragraph`。

## 5. 仓库与依赖卫生核验

- Chroma 默认路径已改为锚定 `Backend/app/scripts/chroma_db`，避免测试或运行时把向量库写到仓库根目录。
- `langchain_community.vectorstores.Chroma` 已切换为 `langchain_chroma.Chroma`，测试不再出现弃用告警。
- 测试临时产物目录已改为系统临时目录，不再继续向仓库 `output/` 下注入新的 `artifact-test-*` 目录。
- 根目录误产物 `app/` 已加入忽略规则，防止再次进入版本控制视野。

## 6. 测试与构建记录

### 6.1 后端测试

执行命令：

```powershell
Backend\.venv\Scripts\python.exe -m unittest discover Backend/tests -v
```

结果：

- `30` 项测试全部通过
- 已覆盖：
  - LLM 工厂
  - 阶段进度
  - Prompt/Schema 清理
  - 质量门控规则
  - 报告对象构建
  - 报告渲染
  - 多格式接口兜底
  - 设置接口
  - 工作流清理

### 6.2 前端测试

执行命令：

```powershell
npm test
```

结果：

- `api index tests`
- `reportPresentation tests`
- `taskProgress tests`

全部通过。

### 6.3 前端构建

执行命令：

```powershell
npm run build
```

结果：

- 构建成功
- 当前仅剩 Vite 的大 chunk 警告，不影响运行与交付

## 7. 已知说明

- 当前设置页中的 LLM/Tavily 配置为运行时生效，不会自动写回 `.env`。
- `task_store = {}` 仍是内存态任务状态，不是持久化任务系统；这已在计划文件中保留为已知限制。
- `Backend/app/scripts/chroma_db/chroma.sqlite3` 属于现有向量库文件，保持现状，不在本轮擅自重建。

## 8. 结论

按当前代码、测试、构建和文档对照结果，第二轮修复涉及的主链功能、展示语义、配置链与测试链已全部收口到可交付状态。  
后续如果继续迭代，应以本清单为基线，不再回退到：

- 多格式双真相
- 正文/附录职责混乱
- 预测字段直排
- 深读小节不显式标出
- 设置页假接线
- 整体评分驱动整段重跑

# 报告结构与内容说明

本文档说明系统自动生成的研判报告包含哪些部分、每部分的作用与典型内容示例，便于答辩展示和读者快速理解报告产出。

---

## 1. 报告总体（封面与元信息）
- 报告文件名示例：`舆情研判_社会_20260114_1100.md`。
- 元信息包括：任务 ID (`task_id`)、研判类别（category）、研判周期（start_date ~ end_date）、生成时间、作者（系统/操作员）、报告版本与所用模型/Prompt 版本（用于可复现与审计）。

作用：便于索引管理、回溯生成参数与审计。

---

## 2. 前言（Preface）
- 由 Agent E 生成，采用智库式公文风格。通常包含：报告覆盖周期、总体态势概述、热点领域分布与主导情绪提炼、违规透视与结语。
- 字数与深度约束：不少于 200 字，分段清晰（概述、特征、违规透视、结语与建议）。

解读提示：前言是决策层的快速入口，适合在答辩中先读给非技术听众。

---

## 3. 热点与榜单（Hot Topics）
- 列表式展示 Top‑N 热点事件，每条包含：事件名、核心关键词、total_heat、简短摘要（merge_reason）、时间戳。
- 可包含表格：事件名 | 关键词 | 热度 | 摘要 | 代表帖子链接。

用途：快速定位最需关注的话题与初步证据。

---

## 4. 典型事件深度分析（Event Analyses）
- 针对若干（默认 5）事件给出深度章节，每章由 Agent B 生成的 `EventAnalysisReport` 构成：
  - 事件概述（事实层）：不少于 150 字；
  - 舆论观点（public_opinions）：至少 4 项（每项含推理）；
  - 深度点评（depth_analysis）：不少于 200 字；
  - 代表评论摘录与观点簇示例（供人工核验）。

解读提示：每个观点后可附评论索引（comment index）以便追溯源数据与人工复核。

---

## 5. 合规审查与证据链（Compliance Findings）
- 汇总 Agent C 的 `audit_results`，每条违规记录包含：
  - 判定（is_violation）、违规类别、风险等级（Low/Medium/High）；
  - `violation_info`：batch_result、matched_laws（Chroma 检索结果或 LLM 回填）、evidence_report（evidence_chain、reasoning、disposal_suggestion）；
  - 涉及的原文片段与评论索引（用于法律取证）。

特色：若 RAG 无命中会保留 LLM 回填条款并标注为 `auto_fallback_cited_laws` 以便人工复核。此节是审计与合规申诉的关键依据。

---

## 6. 趋势预测（Trend Forecast）
- Agent D 输出的 `TrendForecastReport`，包含：
  - target_period（预测时间段）与 evidence_sources（历史/情报来源）；
  - topics（3–5 个 ForecastTopic），每个 topic 含：topic_name、background（最少 60 字）、points（3–5 个 ForecastPoint）；
  - 每个 ForecastPoint 包含 subtitle、content（≥80 字）、likelihood（高/中/低）、evidence_basis 列表。

解读提示：重点关注 likelihood 为“高”的风险点与对应的 evidence_basis（可检验的历史/情报依据）。

---

## 7. 总结与处置建议（Executive Recommendations）
- 从报告整体提炼 3–5 条可落地治理建议（例如：前置预警、舆论澄清机制、平台处置策略、法律上报建议等）。
- 每条建议应指明执行主体（平台/政府/媒体），优先级与预期效果。

---

## 8. 附录（Appendices）
- 原始数据引用（若许可）：代表帖子链接、评论索引；
- Prompt 版本与模型信息（用于可复现）；
- 证据链详细表格与 Chroma 命中文档元信息（article、rule、full_desc、risk_level）；
- 任务运行日志片段（关键节点时间戳）与 Checkpointer 信息（用于断点续传回溯）。

---

## 9. 文件位置与下载方式
- Markdown 报告保存在：`output/` 目录下（文件名含时间与类别）；
- PDF（若已生成）同目录并可通过前端“查看报告/下载”按钮获取或直接访问 `/api/reports/{filename}/download`。

---

## 10. 演示建议与快速读法
- 答辩演示顺序建议：封面 → 前言 → 典型事件（1–2 个深度拆解）→ 合规证据链示例 → 趋势预测要点 → 操作建议 → 附录（证明可审计）。
- 读者关注点：对非技术评委强调“可审计性与可操作性”；对技术评委强调“schema 与断点续传、RAG 回填的工程处理”。

---

如果你愿意，我可以：
- 生成一个带占位内容的示例报告（`output/sample_report.md`），并把真实的数据片段替换为匿名样例以便演示；
- 或把报告各章节生成 PPT 页（便于答辩幻灯片构建）。

要我现在生成示例报告还是直接制作 PPT？请选择其中一项。
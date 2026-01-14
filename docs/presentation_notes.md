# 演讲备注（1页） — 舆情研判系统

目标听众：技术评审 / 项目答辩（10 分钟演示）

1. 开场（30s）
   - 项目目标：自动化采集舆情 → 深度研判 → 合规审查 → 趋势预测 → 报告产出
   - 核心优势：多-agent 协同、可断点续传（SQLite checkpointer）、RAG+LLM 证据链

2. 系统架构（1m）
   - 前端：Vue3 (Task 创建/监控/报告下载)
   - 后端：FastAPI + LangGraph 工作流（Agents A-E）
   - 数据层：Mongo（内容）、Chroma（法规）、SQLite（checkpoints）

3. 关键流程演示（3-4m）
   - UI 新建任务（选择类别/时间/预测）→ 后端 run_task stream 执行 → 前端实时进度
   - 展示日志 / 节点进度 / 计时冻结（start_time / end_time）
   - 演示报告（Markdown/PDF）与合规证据（cited_laws）

4. 亮点与设计决策（1m）
   - 严格 Schema（Pydantic）保证 LLM 输出可解析
   - RAG + LLM 回退（当 RAG 无命中时使用 LLM 提供的条款并保留审计痕迹）
   - 并发/资源控制：线程池、to_thread、请求超时、重试策略

5. 已知限制与后续计划（1m）
   - 多实例持久化（task_store -> Redis）
   - 增加自动化测试覆盖 LLM 链路
   - 提供无 LLM 的演示模式（mock）

6. Q&A（剩余时间）

---

备注：我可以基于这些要点帮你生成一页 PPT（Markdown -> 简洁幻灯片）或导出为 PDF，或者把每个演示步骤写成单独的脚本（便于快速跑 demo）。
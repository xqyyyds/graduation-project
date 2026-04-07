# 舆情报告系统第二次修复总方案

> 文档定位：这是本项目进入最终交付前的“第二次修复详细文件”。  
> 作用：把现有三份计划文件、`AGENTS.md` 约束、当前代码现状、全系统审查结果和最终验收要求合并成一份唯一总修复蓝图。  
> 目标：本轮修复完成后，不再留下“已知但未收口”的链路问题，做到前后端、报告内容、导出格式、测试验收和仓库整洁度都可交付。  
> 执行状态：本轮修复完成后的逐项验收记录见 [2026-04-02-final-acceptance-checklist.md](/e:/graduation-project/docs/plans/2026-04-02-final-acceptance-checklist.md)。

## 1. 本轮修复的范围与目标

### 1.1 修复范围

本轮不是继续发散设计，而是把以下内容一次性收口：

- 两份现行计划文件中承诺但尚未完全落平的修复项
- `AGENTS.md` 中已经固化的硬约束
- 当前仓库中未被明确讨论但会影响交付的系统级风险
- 报告内容质量、展示质量、多格式一致性、测试体系和仓库交付卫生

### 1.2 本轮总目标

修复完成后，系统必须同时满足：

1. 前后端链路真实可用，不再存在“页面能配、实际不生效”的假链路
2. 报告在前端结构化页、HTML、PDF、Markdown 四种形态中内容一致、层级一致、案例位置一致
3. 报告文字达到“深刻、有判断、愿意读”的质量目标，不再残留明显的公文腔、提纲味、字段直排味
4. 违规审核做到逐条 case 级展示与附录明细闭环
5. 任务进度、设置配置、导出下载、报告详情、日志连接都稳定可用
6. 仓库具备完整的回归测试与交付前验收流程
7. 修复完成后，对照三份计划文件与 `AGENTS.md` 做一轮全量检查，确认没有遗漏项

## 2. 当前状态判断

### 2.1 已有基础

当前仓库已经完成了第一轮大改，基础骨架已具备：

- 双模型配置链基本接通
- Tavily 前端可配
- B/C/D/E 主链已重构到结构化方向
- `report_json / md / html / pdf` 四种产物链已初步成型
- 前端报告详情页已从纯 Markdown 走向结构化展示
- 质量门控、任务阶段映射、附录详细违规案例等关键方向已经明确

### 2.2 当前仍不能视为最终交付态

当前代码距离“最终可交付”还有明确差距，主要集中在四类问题：

1. **多格式一致性仍未完全收口**
   - 前端、HTML、PDF、Markdown 在个别 section 上仍存在展示差异
   - PDF 回退路径与主路径展示层级不完全一致
   - Markdown 仍有退化成提纲或字段块的风险

2. **内容层仍有残留老味道**
   - `prompts.py` 仍有多代残留与旧角色腔
   - D 预测内部结构化字段虽已转向段落式，但主链 prompt/schema/render 还没完全统一到最终标准
   - 深读、预测、审核理由的“成品感”仍有提升空间

3. **测试与验收体系远远不够**
   - 后端只有少量单测，缺少服务级、导出级、前后端一致性测试
   - 前端没有自动化测试、没有视觉层验收脚本、没有报告一致性回归
   - 真实运行链路还缺“交付前总验收清单”

4. **仓库交付卫生还不合格**
   - 工作树很脏，含烟测产物和中间目录
   - 根目录出现意外 `app/` 目录，疑似错误产物
   - 存在过时注释和历史输出文件，会误导后续维护与答辩展示

## 3. 本轮必须修完的问题清单

以下问题在本轮全部视为“必修项”，不能再留到以后。

### 3.0 P0 封板前必须先清零的问题

这些问题如果不先修，本轮不能进入“最终交付收口”：

1. [Backend/main.py](/e:/graduation-project/Backend/main.py) 中 `completed_nodes.add(node_name)` 的未定义运行时风险必须修掉
2. [Backend/app/agents/nodes.py](/e:/graduation-project/Backend/app/agents/nodes.py) 中 B 节点事件去重必须接回 `llm_factory`，不能继续走 legacy 单模型配置
3. [Backend/app/services/compliance.py](/e:/graduation-project/Backend/app/services/compliance.py) 中审核 fallback 必须补上“备用 key/备用模型一次”这一层，不能停留在“缩批后直接 blocked”
4. [Backend/app/agents/quality_gate.py](/e:/graduation-project/Backend/app/agents/quality_gate.py) 中 D 门控必须把 `summary_paragraph` 纳入最终展示检查
5. [Backend/app/services/report.py](/e:/graduation-project/Backend/app/services/report.py) 与 [Backend/app/services/report_document.py](/e:/graduation-project/Backend/app/services/report_document.py) 的双源组装必须收口为单一事实源
6. [frontend/src/views/ReportDetail.vue](/e:/graduation-project/frontend/src/views/ReportDetail.vue) 与 [Backend/app/templates/report_detail.html](/e:/graduation-project/Backend/app/templates/report_detail.html) 中预测区字段直排问题必须消失
7. [Backend/app/services/render_pdf.py](/e:/graduation-project/Backend/app/services/render_pdf.py) 的回退路径必须遵守与 HTML/PDF 主路径同样的展示语义

### 3.1 报告多格式一致性问题

必须修完：

- 前端结构化页、HTML、PDF、Markdown 必须统一以 `report_json` 为内容主源
- 同一份报告在四种格式中的：
  - 主章节顺序
  - 深读事件数
  - 违规案例位置
  - 预测主题数
  - 附录明细位置
  必须一致
- PDF 作为当前视觉基准，HTML 和前端结构化页需主动向 PDF 对齐
- Markdown 虽允许朴素，但禁止：
  - 退化成字段清单
  - 出现无序列表式风险卡片
  - 出现与 PDF 不一致的章节层级
- `report_sessions` 里的 `report_json` 与磁盘 `md/html/pdf` 不能再形成“双真相”；需要增加 `render_version` 或等效版本标记，并明确历史读取优先级

### 3.2 深读内容问题

必须修完：

- 每个深读 section 必须稳定展示：
  - `事件概况`
  - `舆论观点画像`
  - `深度研判`
- 标题必须具备可读性、记忆点和判断性，不能只是热搜词重复
- `one_line_verdict` 必须真正承担“先下判断”的作用，而不是换个位置的概述
- HTML/PDF/前端中这三小节都必须显式标题，不能只顺着输出正文

### 3.3 预测内容问题

必须修完：

- D 节点内部结构字段继续保留：
  - `trigger`
  - `spread_path`
  - `offline_scene`
  - `online_scene`
  - `evidence_basis`
- 但最终展示统一改为：
  - `预警摘要`
  - `预测点标题`
  - `段落式正文`
- 段落式正文必须由 LLM 基于结构化底稿组织生成，不能靠模板硬拼
- 前端、HTML、PDF、Markdown 都不能再把内部字段逐条摊给用户
- ReportLab 回退 PDF 也必须遵守这个规则，不能成为旧展示逻辑的漏网之鱼
- `summary_paragraph` 必须成为 D 最终展示的正式字段，并被：
  - 门控校验
  - `report_json`
  - HTML/PDF/Markdown
  - 前端结构化页
  同步使用

### 3.4 违规风险透视与附录问题

必须修完：

- 正文“第三部分：违规风险透视”只放：
  - 总量
  - 风险等级分布
  - 主要类别分布
  - 阶段总结
- 报告末尾附录必须放详细违规案例明细
- 每条案例至少展示：
  - 来源类型
  - 所属事件
  - 违规类别
  - 风险等级
  - 违规摘录
  - 判定理由
  - 主要依据
  - 证据链
  - 处置建议
- 正文不能再挤进冗长案例明细
- 附录不能再次省掉详细案例

### 3.5 Prompt / Schema 问题

必须修完：

- `prompts.py` 清理主链与 legacy 残留
- 删除或降级不再主用的旧 prompt，避免继续误导维护
- `schemas.py` 与 prompt 联动调整，明确：
  - 内部底稿字段
  - 最终展示字段
- 提升整体成品感，重点修：
  - 深读标题与判断
  - 预测段落化表达
  - 审核理由精准性
  - 前言总结力度
- 禁止继续把“字段约束、提纲结构、内部校验说明”直接暴露成最终文风
- 需要显式处理的 legacy 残留包括：
  - `AGENT_C_ANALYSIS_TEMPLATE`
  - `AGENT_C_BATCH_TEMPLATE`
  - `AGENT_C_EVIDENCE_TEMPLATE`
  - `AGENT_D_REACT_SYSTEM_PROMPT`
  - `AGENT_HISTORICAL_*`
- `schemas.py` 中仍带有“硬撑字数/句数”的字段说明要统一收口，改成“信息职责驱动”而不是“篇幅驱动”

### 3.6 设置、任务状态与真实链路问题

必须修完：

- LLM、Tavily、后端地址、超时时间前端可改且真实生效
- 日志页 WebSocket 地址与 API 地址一致
- 任务步骤条不再依赖中文步骤名
- 任务阶段、当前状态、百分比三者一致
- `quality_gate` 不能再导致主步骤回退
- 第二模型为空时自动回退到第一模型，但 UI 和接口都必须明确告知
- 任务阶段内子进度不能再停留在“节点完成即 100%”的粗粒度，要按事件/帖子/搜索生成过程回调
- `task_store = {}` 仍属内存态限制，本轮至少要在验收文档里明确列为已知限制，不能伪装成已持久化任务系统

### 3.7 全系统未显式讨论但必须补的项

这部分是本轮新增纳入范围的“隐性问题”，交付前必须修：

1. **测试体系不足**
   - 前端无自动化测试
   - 后端缺少服务级/导出级/一致性测试
   - 缺少真正的交付验收脚本

2. **仓库污染**
   - 根目录意外 `app/` 中间目录
   - [Backend/app/scripts/chroma_db/chroma.sqlite3](/e:/graduation-project/Backend/app/scripts/chroma_db/chroma.sqlite3) 的变更需要明确处理口径
   - `output/` 下烟测产物混在工作树
   - `docs/plans/`、`AGENTS.md` 仍处于新建/未收口状态

3. **过时注释与历史口径**
   - `Backend/app/services/report.py` 仍残留“不再生成 PDF”的旧注释
   - 旧 PDF 产物仍能看到 `xhtml2pdf` 时代的历史痕迹
   - 需要统一清理“实现已变、注释未变”的误导项

4. **自动化构建缺口**
   - 前端只有 `build`，没有测试脚本
   - 后端测试仍以 `unittest` 为主，缺少更完整回归分层
   - 没有专门覆盖“多格式一致性”的测试

## 4. 本轮修复的实施方式

### 4.1 采用多 AGENTS 并行施工

本轮建议采用 **多 AGENTS 并行 + 主 Agent 汇总评审**，并固定全部使用 `gpt-5.4`。

#### Agent A：后端主链修复

负责：

- A/B/C/D/E 主链残留问题
- prompt/schema 联动重构
- 质量门控、阶段进度、配置链

#### Agent B：前端展示与交互修复

负责：

- Settings / Reports / ReportDetail / Task / Logs
- 结构化报告页
- 下载体验
- 长内容阅读与移动端适配

#### Agent C：渲染导出与多格式一致性修复

负责：

- `report_document`
- `report.py`
- `render_html.py`
- `render_pdf.py`
- HTML/PDF/Markdown 一致性
- PDF 主路径与回退路径一致性

#### Agent D：测试、验收与仓库收口

负责：

- 后端测试补齐
- 前端测试/构建校验
- 烟测/验收脚本
- 仓库脏文件与交付卫生
- 计划文件与 `AGENTS.md` 对照验收

### 4.3 推荐执行顺序

本轮不能从前端样式开始倒着修，推荐顺序固定为：

1. 先修 P0 运行时与单一事实源问题
2. 再清 prompt/schema 与 D 展示字段
3. 再收口 HTML/PDF/Markdown/前端一致性
4. 再补设置链、进度链与多格式下载体验
5. 最后补测试、人工验收与仓库卫生

### 4.2 主 Agent 的责任

主 Agent 不直接并行乱改所有地方，而负责：

- 定义统一约束
- 合并子任务结果
- 解决跨层冲突
- 复查所有代码与文档
- 生成最终交付验收记录

## 5. 本轮修复任务拆分

### 任务组 A：内容生成质量修复

#### A1. Prompt 清库与主链重写

目标：

- 精简 `prompts.py`
- 将主链 prompt 与 legacy prompt 分层
- 清除旧角色腔、旧公文套话、旧反过滤垃圾前缀的过度堆叠

验收：

- 主链 prompt 数量明显收敛
- 不再出现“谁也不确定到底用哪个 prompt”的维护状态

#### A2. Schema 对齐

目标：

- 给最终展示所需字段明确 schema 落点
- 明确区分内部底稿字段和用户展示字段

验收：

- 预测段落式字段、法规说明、证据链等不再只靠代码后补

#### A3. 深读/预测/审核内容风格修复

目标：

- 深读更有判断和钩子
- 预测更像推演段落
- 审核理由更精准克制
- 前言更能定调而非空泛铺陈

验收：

- 同一份报告中不再明显出现公文腔、流水账、字段直排味

### 任务组 B：多格式报告一致性修复

#### B1. `report_json` 单一事实源彻底落平

目标：

- 所有展示层只吃结构化报告对象
- 禁止某一格式继续走独立拼装分支

验收：

- 四种产物的章节顺序、字段语义、案例位置一致

#### B2. 预测区最终展示收口

目标：

- HTML / PDF / Markdown / 前端结构化页统一展示：
  - `预警摘要`
  - `预测点标题`
  - `段落式正文`

验收：

- 看不到 `trigger / spread_path / offline_scene / online_scene / evidence_basis` 被直接摊出来

#### B3. PDF 主路径与回退路径一致化

目标：

- Playwright 主路径与 xhtml2pdf/reportlab 回退路径遵守同样的内容结构

验收：

- 回退 PDF 不再恢复成旧式字段展示

### 任务组 C：前端交付质量修复

#### C1. 结构化详情页收口

目标：

- 让前端主展示完全贴合最终结构
- 修正深读、预测、附录、风险透视的层级与阅读体验

验收：

- 与 PDF 的内容层级一致
- 长内容不乱
- 视觉不偏移

#### C2. 设置链与进度条收口

目标：

- 设置页、日志页、任务页都达到“真实可用”

验收：

- 配置真实生效
- 日志地址正确
- 阶段条不回退、不乱跳

### 任务组 D：测试与交付收口

#### D1. 后端测试补齐

必须新增或补强：

- 报告对象构建测试
- 多格式导出测试
- prompt/schema 基线测试
- 设置接口测试
- 工作流阶段/质量门控测试
- 预测段落化展示测试
- 附录详细案例明细测试
- B 深读输出结构测试
- C fallback 第二层测试
- `Backend/main.py` CLI 主链基础烟测

#### D2. 前端测试补齐

至少补：

- 报告详情结构化渲染测试
- 下载菜单测试
- 设置页保存/测试链路测试
- 进度条 stage_id 渲染测试

#### D3. 交付前全链路验收

必须补一份显式验收清单，逐项对照：

- `2026-04-01-report-system-redesign-design.md`
- `2026-04-01-code-facing-refactor-plan.md`
- `2026-04-02-report-system-implementation-preflight.md`
- `AGENTS.md`

任何一条未满足，都不能标记为“100%完工”。

## 6. 必须新增的测试与验收清单

### 6.1 当前测试缺口

当前仓库测试明显不足：

- 后端只有少量 `unittest`
- 前端没有自动化测试
- 没有多格式一致性测试
- 没有“提示词与 schema 是否真的对齐”的完整校验
- 没有“真实最终展示结构是否符合 AGENTS 约束”的回归

### 6.2 本轮必须补齐的测试类型

1. **后端单测**
   - `llm_factory`
   - `progress`
   - `report_document`
   - `prompt/schema cleanup`
   - `workflow cleanup`
   - `settings api`
   - `forecast paragraph rendering`
   - `appendix detailed cases`

2. **后端集成测试**
   - 报告 4 产物落盘
   - API 多格式下载
   - `report_sessions` 字段完整性
   - `report_json` 与导出产物关键字段一致性

3. **前端组件/页面测试**
   - 详情页 section 渲染
   - 深读三小节可见
   - 预测段落展示
   - 附录详细案例
   - 下载菜单
   - 设置链
   - 任务进度条

4. **交付前人工验收**
   - 桌面端浏览
   - 移动端浏览
   - PDF 打印观感
   - Markdown 层级检查
   - HTML 与前端对照检查
   - 设置页改地址/改模型/改 Tavily 的真实生效检查
   - 日志页地址变更后的重连检查
   - 长预测段落、长附录案例、长深读正文的滚动与换行检查

## 7. 仓库与交付卫生要求

本轮修复结束前，必须做一轮仓库收口：

- 清理不应留在根目录的 `app/` 中间产物
- 清理或归档 `output/` 下的烟测文件，避免混入正式交付
- 清理过时注释和误导性说明
- 确认 `docs/plans/`、`AGENTS.md` 处于最终版
- 明确哪些生成文件应纳入仓库，哪些只作为运行产物
- 对所有未被本轮直接修改、但与主链相邻的代码做一次快速审查，防止残留旧接口、旧字段、旧提示词继续误导后续维护

## 8. 最终验收方式

### 8.1 四层验收

最终必须做四层验收：

1. **代码层**
   - 所有核心模块可导入、可构建、测试通过

2. **功能层**
   - 设置、任务、日志、报告生成、下载、详情页均可用

3. **内容层**
   - 深读、预测、审核、前言达到“可读、深刻、有成品感”

4. **一致性层**
   - 前端、HTML、PDF、Markdown 四种产物对齐

### 8.2 对照性验收

交付前必须逐条勾验：

- `2026-04-01-report-system-redesign-design.md`
- `2026-04-01-code-facing-refactor-plan.md`
- `2026-04-02-report-system-implementation-preflight.md`
- `AGENTS.md`

要求：

- 每条硬约束都要有代码落点或测试落点
- 不能只口头说“已经做了”
- 需要形成一份最终验收记录

## 9. 本轮修复后的定义

只有满足以下条件，才允许宣布“100%完工”：

1. 三份计划文件和 `AGENTS.md` 中的硬要求全部有落实
2. 全系统未显式讨论但影响交付的问题也已修完
3. 前端、HTML、PDF、Markdown 四种产物内容对齐
4. 深读、预测、审核、附录展示都达到最终约束
5. 配置链、日志链、任务链真实可用
6. 测试、构建、人工验收全部通过
7. 仓库处于可交付状态，不再残留误导性中间产物和旧口径
8. 对照三份计划文件与 `AGENTS.md` 的逐项验收记录已经形成并通过

---

## 10. 本文件的使用方式

后续如果进入真正的“第二次修复实施”，应当以本文件为最高执行蓝图：

- 设计文件定义方向
- 第一份计划文件定义代码级方案
- 第二份前置文件定义施工阶段
- 本文件定义“把所有尾巴一次性修干净”的最终收口标准

如果按本文件执行完并通过全量验收，项目应进入“最终交付态”，而不是继续以零散修补方式推进。

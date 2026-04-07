# 舆情报告系统改造实施前置文件

**目标：** 基于既有总方案，将本项目拆成可执行的改造阶段，明确每一步修改范围、实现方式、验证方式和交付物，作为正式改代码前的唯一施工前置文档。

**架构：** 保留现有 `LangGraph + FastAPI + Vue3 + Mongo + Chroma` 主干，不推倒重来；重点重构 Node A/B/C/D/E 的输入输出、报告渲染链、前端详情页和设置链路，使系统从“字符串拼接式报告”升级为“结构化证据流 + 双 LLM 分工 + HTML/PDF 主渲染”的稳定工程系统。

**技术栈：**
- 后端：FastAPI、LangGraph、LangChain、MongoDB、Chroma
- 前端：Vue 3、Pinia、Element Plus、Vite
- 渲染：Jinja2、Playwright、Markdown 兼容导出（PDF 失败时回退 xhtml2pdf/reportlab）

---

## 0. 施工总原则

### 0.1 不推翻现有主干

保留：

- `Classify -> A -> [B || C] -> GateBC -> D -> GateD -> E`
- 现有 `FastAPI` API 骨架
- 现有 `MongoManager / ChromaManager`
- 现有前端路由、布局、列表页

不做：

- 重做爬虫
- 重做 ETL 主逻辑
- 重建法条向量库
- 启用 `agent_historical`

### 0.2 只改影响结果质量与交付一致性的关键链路

本轮重点修以下关键链路：

1. 前端设置与连接配置链
2. Node A 证据装配链
3. B 深读链
4. C 审核链
5. D 预测链
6. Prompt 与 Schema 联动层
7. E 报告对象、导出与模板渲染链
8. 前端结构化报告展示链
9. 任务管理进度链

### 0.3 质量目标

目标是“高质量、强可测、可交付”，不是口头承诺“绝对零 bug”。

因此后续实现必须满足：

- 每个阶段都能单独验证
- 每条关键链路都有回归检查
- 每个新增结构都有向后兼容策略或降级路径
- 交付时提供：
  - 可运行系统
  - 可验证接口
  - 可下载报告产物
  - 测试记录与已知限制

---

## 1. 最终交付形态

改造完成后，系统应交付以下能力：

### 1.1 后端

- 双 LLM 配置可用
- API 地址、日志、LLM 配置链路真实可用
- Node A 能稳定输出结构化 `post_packet`
- B 能输出更像成品的深读结果
- C 能输出逐条 `ViolationCase`
- D 能输出结构化预警主题和预测点
- E 能输出：
  - `report_json`
  - `report_md`
  - `report_html`
  - `report_pdf`

### 1.2 前端

- 设置页能真正保存连接配置并测试
- 日志页能跟随后端地址连接
- 报告列表页支持多格式下载
- 报告详情页切换为结构化展示
- 违规案例以卡片/抽屉形式优雅展示

### 1.3 报告产物

- 固定章节结构
- 优化后的固定引导语
- 热点总览表保留当前 4 列
- 违规风险透视正文只展示统计信息与阶段总结
- 附录必须展示统计表 + 详细违规案例明细
- HTML/PDF 排版稳定、美观、可下载
- 前端结构化页、HTML、PDF、Markdown 四种产物内容主线一致
- 当前布局与视觉质量对齐优先以 PDF 成品为参考

### 1.4 多格式一致性要求

多格式输出必须遵守“单一事实源”原则：

- `report_json` 是唯一内容主源
- HTML、PDF、Markdown、前端结构化页都从 `report_json` 派生
- 不允许某个格式单独拼章节、单独改案例位置、单独漏字段

一致性最低要求：

- 四种产物的章节顺序一致
- 深读三小节标题一致
- 违规案例所在章节一致
- 预测主题数量和每个主题的正文层级一致
- Markdown 虽可朴素，但不能把 HTML/PDF/前端中的正文段落退化成字段清单或无序列表

---

## 2. 固定配额与边界

这些值在第一阶段固定写死，不做动态漂移。

### 2.1 事件与帖子

- 事件候选池：`Top 20`
- 深读事件数：`5`
- 审核事件数：`8`
- 深读每事件帖子数：`12`
- 审核每事件帖子数：`15`

### 2.2 评论

- 深读评论：每帖 `高赞前 20`
- 审核评论池：每帖 `高赞 60 + 最新 40`，去重后最多 `100`
- `FAST_LLM` 初筛批次：每批最多 `20`
- `STRONG_LLM` 终裁批次：每批 `3~5`

### 2.3 历史与预测

- `agent_historical` 保持停用
- 历史上下文仅来自联网摘要
- D 只能吃摘要输入，不能吃原始帖子/评论长文本

### 2.4 前端展示字段

违规案例主展示字段固定为：

- 来源类型
- 违规类别
- 风险等级
- 违规摘录
- 判定理由
- 主要依据
- 处置建议

不展示：

- `confidence`
- 内部 id
- provider 拦截信息
- `blocked_count`

---

## 3. 实施阶段总览

整个施工按 10 个阶段推进，不跳步，不并行乱改。

### 阶段列表

1. 设置与配置打通
2. LLM 工厂与双模型接入
3. Node A 结构化证据装配
4. C 审核链重构
5. B 深读链重构
6. D 趋势预测重构
7. Prompt 与 Schema 联动重构
8. E 报告总编、导出与模板渲染
9. 前端结构化报告页与下载体验
10. 任务管理进度条与状态映射修复

---

## 4. 分阶段施工清单

### 阶段 1：设置与配置打通

**目标：** 先把“配置页看起来可配，实际没生效”的问题彻底修正。

**主要修改文件：**

- [frontend/src/views/Settings.vue](/e:/graduation-project/frontend/src/views/Settings.vue)
- [frontend/src/api/index.js](/e:/graduation-project/frontend/src/api/index.js)
- [frontend/src/stores/app.js](/e:/graduation-project/frontend/src/stores/app.js)
- [frontend/src/views/Logs.vue](/e:/graduation-project/frontend/src/views/Logs.vue)
- [Backend/app/api/main.py](/e:/graduation-project/Backend/app/api/main.py)

**要做什么：**

1. 将 `backendForm` 与 `store.settings` 真正绑定
2. 让 API `baseURL` 和 `timeout` 动态读取 `appSettings`
3. 将“测试连接”改成真实调用 `/api/health`
4. WebSocket 地址根据当前 API 地址推导，不再写死
5. 设置页默认值以后端接口返回为准，不再写死误导值
6. 明确 LLM 保存是“运行时保存”还是“落盘持久化”
7. 后端 CORS 支持配置化 origin

**怎么做：**

- 前端 Settings 页面拆成：
  - 加载现有设置
  - 编辑
  - 保存
  - 测试连接
- API 层增加派生函数：
  - `getBaseUrl()`
  - `getTimeout()`
  - `getWsUrl()`
- 后端补稳定 `health` 探针使用说明

**验证方式：**

- 前端改 API 地址后刷新页面，接口请求仍然命中新地址
- 改超时时间后 axios 实际超时值变化
- Logs 页连接地址跟随后端地址变化
- 远程/非本地 origin 下 CORS 不再固定卡死

**阶段产物：**

- 真实可用的设置页
- 动态 API / WebSocket 连接链
- 与后端一致的 LLM 配置显示

**验收标准：**

- 页面上改的地址、超时和 LLM 配置，不再是“假保存”

---

### 阶段 2：LLM 工厂与双模型接入

**目标：** 建立 `FAST_LLM` / `STRONG_LLM` 统一工厂，后面所有节点改造都基于它。

**主要修改文件：**

- [Backend/app/core/config.py](/e:/graduation-project/Backend/app/core/config.py)
- [Backend/app/api/main.py](/e:/graduation-project/Backend/app/api/main.py)
- 新增 [Backend/app/core/llm_factory.py](/e:/graduation-project/Backend/app/core/llm_factory.py)

**要做什么：**

1. 新增双模型配置项
2. 提供统一工厂函数：
   - `get_fast_llm()`
   - `get_strong_llm()`
3. 保留向下兼容：
   - 只配一套时自动回退
4. 前端现有单组 LLM 配置先视为第一模型（`FAST_LLM`）

**怎么做：**

- 配置层读：
  - `FAST_LLM_*`
  - `STRONG_LLM_*`
- 后端设置接口增加两套配置的读写支持
- 统一超时、重试次数和 temperature
- 前端设置页当前已有那组：
  - 模型名
  - Base URL
  - API Key
  先直接映射为 `FAST_LLM`
- 再新增第二组配置作为 `STRONG_LLM`
- 若第二组为空，则前端和后端都明确采用：
  - `STRONG_LLM -> 回退到 FAST_LLM`
- 同一页面补充 Tavily 联网搜索配置：
  - `TAVILY_API_KEY`
  - 保存后运行时生效
  - 可单独测试连通性

**验证方式：**

- 单套配置时系统仍能运行
- 双套配置时 B/C/D/E 调用的模型角色正确
- 配置测试接口能分别验证两套模型
- Tavily 配置修改后，联网搜索链路立即可用

**阶段产物：**

- 双模型工厂
- 新版 LLM settings API

**验收标准：**

- 后续节点改造不再直接硬编码 `ChatOpenAI(...)`

---

### 阶段 3：Node A 结构化证据装配

**目标：** 给 B/C/D 输入稳定、最小且够用的 `post_packet`。

**主要修改文件：**

- [Backend/app/db/mongo_manager.py](/e:/graduation-project/Backend/app/db/mongo_manager.py)
- [Backend/app/agents/nodes.py](/e:/graduation-project/Backend/app/agents/nodes.py)

**要做什么：**

1. 扩充帖子查询返回字段
2. 扩充评论查询返回字段
3. 在 `agent_a_node` 中组装结构化 `post_packet`
4. 深读评论固定按高赞前 20 条抽样

**怎么做：**

- 帖子保留字段：
  - `note_id`
  - `db_id`
  - `content`
  - `source_keyword`
  - `create_date_time`
  - `liked_count`
  - `comments_count`
  - `media_context`
- 评论保留字段：
  - `db_id`
  - `comment_id`
  - `content`
  - `create_date_time`
  - `comment_like_count`

**验证方式：**

- Node A 运行后 state 中每个事件都能拿到结构化 `post_packet`
- B/C 不需要再手工从字符串里拆内容
- 深读样本评论数稳定在 20 以内

**阶段产物：**

- 稳定的 `post_packet`
- 后续节点统一输入基础

**验收标准：**

- B/C/D 不再依赖“帖子正文 + 评论纯文本大拼接”

---

### 阶段 4：C 审核链重构

**目标：** 从“整帖总体判断”切成“逐条 case 终裁 + 单条法条挂接”。

**主要修改文件：**

- [Backend/app/services/compliance.py](/e:/graduation-project/Backend/app/services/compliance.py)
- [Backend/app/db/chroma_manager.py](/e:/graduation-project/Backend/app/db/chroma_manager.py)
- [Backend/app/core/prompts.py](/e:/graduation-project/Backend/app/core/prompts.py)
- [Backend/app/core/schemas.py](/e:/graduation-project/Backend/app/core/schemas.py)
- [Backend/app/agents/nodes.py](/e:/graduation-project/Backend/app/agents/nodes.py)

**要做什么：**

1. 审核事件数固定为 8
2. 每事件固定取 15 个帖子
3. 每帖子构造 100 条评论池
4. `FAST_LLM` 分批初筛
5. `STRONG_LLM` 逐条终裁
6. 每条 `ViolationCase` 单独做法条匹配
7. 审核结果按新结构落库

**怎么做：**

- 评论池：`高赞60 + 最新40`
- `FAST_LLM`：每批 20 条，仅做 suspect filter
- `STRONG_LLM`：每批 3~5 条，逐条输出：
  - `quote`
  - `category`
  - `reasoning`
  - `risk_level`
  - `disposal_suggestion`
- law query：`category + quote + reasoning`
- category filter 优先

**fallback：**

- `FAST_LLM`: `20 -> 5 -> 备用 key`
- `STRONG_LLM`: `3~5 -> 单条 -> 备用 key`
- 仍失败：只记内部 `blocked_count`，不进入前端违规展示

**验证方式：**

- 单条评论能一一对应：
  - 违规摘录
  - 判定理由
  - 主要依据
  - 处置建议
- 不再出现“总体理由覆盖一堆评论”
- provider 拦截时不会整链失败

**阶段产物：**

- 新 `ViolationCase`
- 新 `violation_info`
- 新的单条法条挂接结果

**验收标准：**

- 前端/报告端看到的是逐条 case，不再是一锅炖

---

### 阶段 5：B 深读链重构

**目标：** 让重点舆情深读有好标题、有判断、有层次，而不是公文化平铺。

**主要修改文件：**

- [Backend/app/services/opinions.py](/e:/graduation-project/Backend/app/services/opinions.py)
- [Backend/app/core/prompts.py](/e:/graduation-project/Backend/app/core/prompts.py)
- [Backend/app/core/schemas.py](/e:/graduation-project/Backend/app/core/schemas.py)
- [Backend/app/agents/nodes.py](/e:/graduation-project/Backend/app/agents/nodes.py)

**要做什么：**

1. 保持深读事件数 5
2. 每事件最多 12 帖
3. 每帖由 `FAST_LLM` 做切片
4. `STRONG_LLM` 做事件级 reduce
5. 固定三类搜索补背景

**怎么做：**

- per-post map 输出：
  - `fact_slice`
  - `opinion_buckets`
  - `conflict_points`
  - `emotion_labels`
  - `representative_quotes`
  - `risk_signals`
- event reduce 输出：
  - `editorial_title`
  - `one_line_verdict`
  - `event_overview`
  - `public_opinions`
  - `depth_analysis`
  - `key_quotes`

**验证方式：**

- 每个深读事件都有标题和一句话判断
- 标题不再是热搜词复读
- 深读内容明显比当前更具体、更有判断

**阶段产物：**

- 新 `EventAnalysisReport`
- 更强深读输入供 E 和 D 使用

**验收标准：**

- 重点深读不再像模板公文，而像可阅读成品

---

### 阶段 6：D 趋势预测重构

**目标：** 让预测真正基于主线矛盾、风险信号和未来节点，而不是泛泛续写。

**主要修改文件：**

- [Backend/app/agents/nodes.py](/e:/graduation-project/Backend/app/agents/nodes.py)
- [Backend/app/core/prompts.py](/e:/graduation-project/Backend/app/core/prompts.py)
- [Backend/app/core/schemas.py](/e:/graduation-project/Backend/app/core/schemas.py)

**要做什么：**

1. 去掉对 `agent_historical` 的依赖
2. D 只吃压缩摘要，不吃原始长文本
3. 固定三类在线搜索
4. `FAST_LLM` 先压历史与未来信号
5. `STRONG_LLM` 成文
6. 每个 topic 至少 2 个预测点
7. 不同 `forecast_range` 对应不同搜索策略，而不是只换时间文案

**怎么做：**

- 输入控制为：
  - 5 个深读事件摘要
  - 5 个审核风险摘要
  - 3 条历史摘要
  - 5 条未来信号摘要
- 输出结构：
  - `topic_name`
  - `background`
  - `audience`
  - `scene_opening`
  - `points[2..4]`

#### 周期化查询规则

不同预测周期必须驱动不同的搜索重点：

- `1w`
  - 优先搜索未来 7 天内的确定性节点
  - 重点看：发布日、查分日、会议日、赛事日、纪念日、公告日
  - 适合短期引爆点预测

- `2w`
  - 优先搜索半月内连续触发事件
  - 重点看：考试窗口、活动周期、政策生效前后、舆情持续升温点

- `1m`
  - 优先搜索月度节奏与阶段性议题
  - 重点看：政策节奏、月度事件、社会情绪累积与节点共振

- `2m`
  - 优先搜索跨月周期性风险
  - 重点看：学期变化、招录周期、节庆、季节性民生议题、长期议题演化

实现要求：

- D 节点不能只是把 `forecast_range` 改写成不同文案塞给模型
- 联网搜索 query 模板、摘要重点、topic 生成角度都必须随周期变化
- 最终报告中的 `target_period`、topic 背景和 evidence_basis 要与所选周期一致

**验证方式：**

- 单个 topic 不再只有 1 个点
- 每个预测点都具备：
  - 触发点
  - 传播路径
  - 线上/线下场景
  - 依据说明
- 上下文长度稳定，不爆模型窗口

**展示约束：**

- 上述字段只作为 D 节点内部结构化底稿和质量校验依据
- 最终报告、前端结构化页、HTML、PDF 不直接逐条展示：
  - `触发点`
  - `传播路径`
  - `线上/线下场景`
  - `依据`
- 最终展示形态改为：
  - `预警摘要`
  - `预测点标题`
  - `段落式正文`

实现方式为：

- `STRONG_LLM` 基于结构化底稿，再组织一层面向读者的 `summary_paragraph`
- 模板层只负责渲染这个段落化结果，不再把底稿字段原样摊给用户

**阶段产物：**

- 新 forecast JSON 结构

**验收标准：**

- 预测从“空泛总结”提升为“像预警推演”

---

### 阶段 7：Prompt 与 Schema 联动重构

**目标：** 清理历史残留提示词，重写主链 prompt，并同步调整 schema 说明与展示字段，让系统输出从“结构正确”升级为“结构正确且有成品感”。

**主要修改文件：**

- [Backend/app/core/prompts.py](/e:/graduation-project/Backend/app/core/prompts.py)
- [Backend/app/core/schemas.py](/e:/graduation-project/Backend/app/core/schemas.py)

**要做什么：**

1. 清理已脱离主工作流的 legacy prompt
2. 重写 B/C/D/E 主链 prompt
3. 同步调整 schema 注释、字段说明和展示字段
4. 减少公文腔、模板味、提纲味
5. 增强标题感、判断力、现场感和段落化表达

**怎么做：**

- `prompts.py` 先按“主链 / legacy”分区
- 主链 prompt 只保留当前真正生效的模板
- B prompt 从“长度驱动”改成“矛盾驱动、判断驱动”
- C prompt 从“重反过滤前缀”改成“强证据、强边界、逐条理由”
- D prompt 明确区分：
  - 内部结构化底稿
  - 面向读者的段落式正文
- E prompt 去掉过度模板化和空泛结语
- `schemas.py` 同步补足最终展示需要的字段，如：
  - 证据链
  - 法规说明
  - 段落化预测正文

**风格要求：**

- 文字必须让观众愿意读
- 可以活泼，但不能轻浮
- 要有观点、新意和锋利度
- 不得满足于安全但乏味的公文写法

**验证方式：**

- 主链 prompt 数量明显收敛，legacy 提示词不再混入主链
- 深读标题不再只是热搜复述
- 预测正文不再是字段直排
- 审核理由不再空泛或一锅炖
- schema 与最终展示字段不再错位

**阶段产物：**

- 清理后的 `prompts.py`
- 对齐后的 `schemas.py`
- 更有成品感的主链提示词体系

**验收标准：**

- 生成内容在保持结构稳定的同时，明显摆脱公文腔、模板味和提纲味

---

### 阶段 8：E 报告总编、模板与导出

**目标：** 先组装结构化 `ReportDocument`，再导出多种格式。

**主要修改文件：**

- [Backend/app/services/report.py](/e:/graduation-project/Backend/app/services/report.py)
- [Backend/app/core/schemas.py](/e:/graduation-project/Backend/app/core/schemas.py)
- [Backend/app/api/main.py](/e:/graduation-project/Backend/app/api/main.py)
- 新增：
  - `Backend/app/services/render_html.py`
  - `Backend/app/services/render_pdf.py`
  - `Backend/app/templates/report_base.html`
  - `Backend/app/templates/report_detail.html`

**要做什么：**

1. 引入主对象 `ReportDocument`
2. 固定报告骨架与固定文案迁入模板
3. 从 `ReportDocument` 渲染：
   - `json`
   - `md`
   - `html`
   - `pdf`
4. 新增多格式下载接口
5. 更新 `report_sessions` 存储结构

**怎么做：**

- HTML 模板负责：
  - 固定章节
  - 固定引导语
  - CSS 主排版
- PDF 由 HTML 输出
- Markdown 降级为兼容导出，不再承载复杂样式
- 正文的“第三部分：违规风险透视”只渲染：
  - 确认违规总量
  - 风险等级分布
  - 主要违规类别
  - 阶段性总结文字
- 报告末尾附录必须新增“违规案例明细”区，逐条展示：
  - 来源类型
  - 所属事件
  - 违规类别
  - 风险等级
  - 违规摘录
  - 判定理由
  - 主要依据
  - 证据链
  - 处置建议

**验证方式：**

- 每份报告都能同时落盘 4 种产物
- PDF 样式与 HTML 保持一致
- 热点总览保持 4 列
- 正文只展示违规统计和总结，不混入详细案例
- 附录同时具备违规统计表和详细案例明细

**阶段产物：**

- `ReportDocument`
- `json/md/html/pdf` 四种产物
- 多格式下载 API

**验收标准：**

- 报告不再只有 Markdown 字符串这一个最终形态

---

### 阶段 9：前端结构化报告页与下载体验

**目标：** 保留现有框架，重做报告详情内容层。

**主要修改文件：**

- [frontend/src/views/Reports.vue](/e:/graduation-project/frontend/src/views/Reports.vue)
- [frontend/src/views/ReportDetail.vue](/e:/graduation-project/frontend/src/views/ReportDetail.vue)
- 新增：
  - `frontend/src/views/ReportDetailStructured.vue`
  - `frontend/src/components/DeepReadCard.vue`
  - `frontend/src/components/ForecastCard.vue`
  - `frontend/src/components/ViolationClusterList.vue`
  - `frontend/src/components/ViolationCaseDrawer.vue`
  - `frontend/src/components/ReportArtifactBar.vue`
- [frontend/src/api/index.js](/e:/graduation-project/frontend/src/api/index.js)

**要做什么：**

1. 保留现有列表页和路由壳子
2. 报告详情主入口改成结构化视图
3. 原 `ReportDetail.vue` 降级为 markdown 预览
4. 下载改成多格式菜单
5. 违规案例改成卡片 + 抽屉

**怎么做：**

- Section 1：热点总览表
- Section 2：深读卡片组
- Section 3：违规风险概览 + 总结
- Section 4：趋势预警卡片组
- Section 5：附录统计 + 违规案例明细

其中 Section 2 有一个硬要求：

- 每张深读卡片都必须显式展示以下三个小标题，而不能只顺着输出正文：
  - `事件概况`
  - `舆论观点画像`
  - `深度研判`

这个要求同时适用于：

- 前端结构化详情页
- HTML 导出模板
- PDF 成品

**验证方式：**

- 详情页不再只渲染 markdown
- 审核案例不再依赖超长表格
- 附录案例明细能逐条查看帖子/评论、理由、法规、证据链、风险等级、处置建议
- 下载栏可选 md/html/pdf
- 页面在移动端和桌面端都能正常展示

**阶段产物：**

- 新版结构化详情页
- 多格式下载体验

**验收标准：**

- 前端报告展示优雅、可读、可查、可下载

---

### 阶段 10：任务管理进度条与状态映射修复

**目标：** 让任务管理页的步骤条、当前阶段和后端真实执行阶段一致，不再出现步骤错位、重复门控回退和阶段误导。

**主要修改文件：**

- [frontend/src/views/Task.vue](/e:/graduation-project/frontend/src/views/Task.vue)
- [frontend/src/stores/app.js](/e:/graduation-project/frontend/src/stores/app.js)
- [Backend/main.py](/e:/graduation-project/Backend/main.py)
- [Backend/app/api/main.py](/e:/graduation-project/Backend/app/api/main.py)

**当前问题：**

- 前端步骤条依赖固定中文步骤名匹配
- 后端进度映射同样依赖硬编码中文步骤名
- `quality_gate_bc` 和 `quality_gate_d` 共用“质量评估”步骤名，会导致前端步骤回退/错位
- `分类`、`门控`、`repair`、`fallback` 混在主步骤条里，用户理解成本高
- 进入并行、repair、fallback 场景后，当前百分比与步骤条越来越失真

**要做什么：**

1. 用稳定的 `stage_id` 替代中文步骤名做前后端映射
2. 前端步骤条只保留真正面向用户的主阶段
3. 门控、repair、fallback 改成次级状态文案和日志，不再占主步骤
4. 避免第二次质量门控把前端步骤打回前一个阶段

**怎么做：**

- 后端统一输出稳定阶段标识，例如：
  - `prepare`
  - `deep_read`
  - `compliance`
  - `forecast`
  - `report`
  - `done`
- 前端步骤条收敛为：
  1. 数据准备
  2. 深读分析
  3. 违规审核
  4. 趋势预测
  5. 报告组装
  6. 导出完成
- `分类`、`质量门控`、`局部 repair`、`fallback` 仅作为：
  - 当前状态说明
  - 日志输出
  - 不再作为主步骤节点

**验证方式：**

- D 的质量门控不再把步骤条打回“质量评估”
- 并行/repair/fallback 场景下，步骤条仍然只向前推进
- 当前阶段、百分比、日志三者不再互相冲突

**阶段产物：**

- 新版任务阶段映射
- 更稳定的任务进度条与监控文案

**验收标准：**

- 任务管理页不再出现明显的步骤错位和回退 bug

---

## 5. 测试与验收方案

## 5.1 后端测试

每一阶段都必须补对应验证，不等到最后一起试。

### 配置链

- API 地址切换
- timeout 生效
- WebSocket 派生地址正确
- LLM settings 读写与测试接口可用

### Node A

- 结构字段完整性
- 空评论去除
- 高赞评论截断逻辑正确

### C 审核链

- 评论池构造正确
- `FAST_LLM` -> `STRONG_LLM` 链路正确
- 单条 case 法条挂接正确
- fallback 触发后整链不崩

### B 深读链

- 每事件深读字段完整
- 标题、判断、引用齐全

### D 预测链

- 输入摘要不过长
- topic 数和 point 数符合约束

### E 导出链

- 4 种产物都存在
- API 返回正确
- 文件名与 session 记录一致

## 5.2 前端测试

- Settings 页保存/测试真实生效
- Logs 页跟随连接地址变化
- Reports 列表页下载菜单可用
- Structured 详情页数据渲染正常
- Drawer 展示字段正确
- 多格式下载有效
- 任务管理页步骤条在正常、repair、fallback 场景下不倒退、不乱跳

## 5.3 端到端回归

至少跑通 4 类场景：

1. 正常类别任务
2. 审核高风险较多的任务
3. 搜索/模型部分失败触发 fallback 的任务
4. 存在门控修补但主步骤不应回退的任务

## 5.4 交付前手工验收

交付前必须人工检查：

- 一份新生成报告的：
  - 热点总览
  - 深读
  - 违规案例
  - 趋势预测
  - html/pdf 下载
- 设置页真实生效
- 日志页真实可连
- 无明显报错、字段错位、下载缺失

---

## 6. 交付清单

改造完成后，交付给用户的必须包括：

### 6.1 代码产物

- 更新后的前后端代码
- 新增的模板、渲染器、结构化组件

### 6.2 运行产物

- 至少 1 份新生成的：
  - `json`
  - `md`
  - `html`
  - `pdf`

### 6.3 说明产物

- 更新后的计划文件
- 本实施前置文件
- 测试结果摘要
- 已知限制列表

---

## 7. 实际施工顺序

真正开始改代码时，严格按这个顺序：

1. 设置与连接配置
2. 双模型工厂
3. Node A 证据装配
4. C 审核链
5. B 深读链
6. D 预测链
7. E 报告对象与导出
8. 前端结构化报告页
9. 任务管理进度条与状态映射
10. 最后一轮全链路回归

不能先改前端报告页，再改后端结构；也不能先改 PDF，再改 `ReportDocument`。

---

## 8. 本文件的作用

这份文档不是再次发散设计，而是把既有总方案收敛成：

- 先做什么
- 后做什么
- 每步改哪里
- 每步怎么验证
- 最后交付什么

如果你批准，后续真正实施时应以这份文档和总方案文档作为双基线：

- 总方案文档：定义“系统要变成什么样”
- 本前置文件：定义“施工时每一步怎么干”

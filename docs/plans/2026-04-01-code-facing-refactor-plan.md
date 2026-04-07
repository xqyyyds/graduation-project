# 舆情报告系统代码级改造前置方案

> 文档定位：这是“准备改代码前的最终方案”，不是泛泛设计说明。  
> 适用约束：  
> 1. 只能使用 LLM API，不能部署本地模型。  
> 2. 最多同时维护两套 LLM 配置/两把 API Key。  
> 3. 必须贴合当前 Mongo 爬虫数据结构与现有 `Backend/frontend` 代码组织。  
> 4. 下一步目标是按本方案直接落代码。

## 1. 现有代码与数据现实

我先明确当前系统的真实基础，不再按理想化系统假设。

### 1.1 当前 Mongo 数据结构

后端现在实际依赖三类核心集合：

- `hot_trends_history`
  - 来源：微博热搜快照
  - 后端读取位置：[mongo_manager.py](/e:/graduation-project/Backend/app/db/mongo_manager.py#L92)
  - 核心字段：
    - `source = "weibo_social"`
    - `collected_at`
    - `top_n[]`
      - `word`
      - `num`
      - `category`

- `weibo_contents`
  - 后端读取位置：[mongo_manager.py](/e:/graduation-project/Backend/app/db/mongo_manager.py#L269)
  - 当前后端实际使用字段：
    - `note_id`
    - `content`
    - `full_content`（如果有）
    - `image_list`
    - `video_url`
    - `source_keyword`
    - `liked_count`
    - `audit_status`
    - `is_violation`
    - `violation_info`
  - 爬虫模型中对应字段可参考 [models.py](/e:/graduation-project/MediaCrawler/database/models.py#L225)

- `weibo_comments`
  - 后端读取位置：[mongo_manager.py](/e:/graduation-project/Backend/app/db/mongo_manager.py#L299)
  - 当前后端实际使用字段：
    - `note_id`
    - `content`
    - `comment_like_count`
  - 爬虫模型中对应字段可参考 [models.py](/e:/graduation-project/MediaCrawler/database/models.py#L253)

### 1.1.1 必须分清三层数据

这点后续实现必须始终注意：

- **爬虫原始层**
  - `hot_trends_history`
  - `weibo_contents`
  - `weibo_comments`
  - 含义：原始抓取结果与其审核回写字段

- **系统中间层**
  - `events`
  - 含义：ETL 每次运行后重新生成的核心事件集合
  - 代码位置：[save_core_events](/e:/graduation-project/Backend/app/db/mongo_manager.py#L247)

- **系统结果层**
  - `report_sessions`
  - 含义：每次生成报告后写入的长期结果集合
  - 代码位置：[save_report_session](/e:/graduation-project/Backend/app/db/mongo_manager.py#L401)

这个分层的重要性在于：

- `events` 和 `report_sessions` 都是系统生成层，可以大胆改结构
- `weibo_contents` 和 `weibo_comments` 是原始数据层，只应增量回写审核字段，不要做重迁移
- 本次改造真正要做兼容的是 `violation_info` 的新旧结构，而不是爬虫原始 schema

### 1.2 当前取数和工作流现实

现在的主干工作流不需要推倒重来，保留最划算：

- `Classify -> A -> [B || C] -> GateBC -> D -> GateD -> E`
  - 工作流定义在 [workflow.py](/e:/graduation-project/Backend/app/agents/workflow.py#L45)

当前问题主要不在“有没有工作流”，而在：

- Node A 只把事件抓成“帖子文本 + 评论列表 + 简单媒体链接”
- B/C/D/E 的输入都太粗
- C 按帖子整体做审查
- E 把结构化结果重新拍扁成大 Markdown 字符串

### 1.3 当前最应该保留的东西

这几块可以保留，不建议重来：

- `FastAPI` API 骨架
- `LangGraph` 节点工作流
- Mongo 读写入口 `MongoManager`
- Chroma 规则库的基础设施
- 前端页面整体路由与 Pinia 状态

### 1.4 当前最应该重做的东西

以下模块必须重做，否则你要的效果出不来：

- ETL 事件归并逻辑
- Node A 的证据装配逻辑
- B 的深读输入组织和输出结构
- C 的审核数据模型与逐条判定链
- D 的预测输入、联网策略和输出结构
- E 的报告对象模型与渲染机制
- 报告详情页与违规展示页
- LLM 配置体系（改成双模型配置）

## 2. 最终采用的唯一方案

不做多方案比较，直接给出我认为在你当前代码库和约束下最优、最可落地的路线：

### 2.1 核心路线

**保留现有 LangGraph 主干节点不变，重构每个节点的内部产物，让系统从“字符串拼接流”升级为“结构化证据流 + 双 LLM 分工 + HTML 主渲染”的舆情系统。**

### 2.2 两个 API Key 的固定分工

后端改成固定双模型角色，不做动态选择：

#### `FAST_LLM`

用途：

- 评论候选初筛
- 帖子切片摘要
- 评论簇归纳
- 标题润色
- 审核 reviewer
- 预测资料整理

特点：

- 速度快
- 成本低
- 允许较多并发
- 上下文较短

#### `STRONG_LLM`

用途：

- 重点深读 reduce
- 逐条违规终裁
- 趋势预测正式写作
- 前言与报告总编
- 高质量 reviewer

特点：

- 推理更强
- 调用次数更少
- 每次只处理高价值输入

### 2.3 为什么这个分工是当前最优

因为你当前最大的瓶颈不是“模型不够强”，而是：

- 一个模型做了太多不同性质的任务
- 高毒内容和长上下文都直接打给同一个模型
- 造成过滤、成本和质量三输

双模型分工后：

- `FAST_LLM` 做“预处理、压缩、归纳”
- `STRONG_LLM` 做“定稿、终裁、成文”

这样最贴合你当前“只有两个 key”的实际条件。

## 3. 代码改造总原则

### 3.1 不新增新节点，先改节点内部

第一轮不改 LangGraph 拓扑，只改节点内部逻辑。

原因：

- 工作流主干已经能跑
- 直接改节点内部风险最低
- 更容易一步步验证

所以第一轮还是：

- `agent_a_node`
- `agent_b_analyze_node`
- `agent_c_node`
- `agent_d_node`
- `agent_e_node`

但每个节点的输入输出都升级。

### 3.2 不再以 Markdown 为主产物

最终主产物改成：

- `report_json`
- `report_html`
- `report_md`
- `report_pdf`

其中：

- 前端展示主用 `report_json`
- 下载主用 `report_html / report_pdf / report_md`
- Markdown 不再承担复杂 UI 展示职责
- `report_json` 是所有格式的唯一内容主源，前端结构化页、HTML、PDF、Markdown 必须从同一份结构化报告对象派生，避免多套内容拼接逻辑长期漂移
- 当前排版与视觉质量的主对齐参考采用 PDF 成品；HTML、前端结构化页的章节层级、标题顺序、案例位置与字段含义必须与 PDF 对齐，Markdown 可在视觉上简化，但内容顺序和语义不得偏移

### 3.3 审核必须逐条裁决

这是硬要求：

- 帖子一条一条判
- 评论一条一条判
- 每条结果都有：
  - `quote`
  - `reasoning`
  - `matched_law`
  - `risk_level`
  - `disposal_suggestion`
  - `confidence`

### 3.3.1 Prompt 与 Schema 必须联动重构

本次改造不能只改链路，不改语言层。`prompts.py` 与 `schemas.py` 必须视为同一层面的联动对象：

- 清理 `prompts.py` 中已经脱离主工作流的 legacy prompt，避免多代提示词长期混杂
- 当前主链正在使用的 prompt，必须同步检查对应 schema 的字段说明、数量约束和风格说明
- 凡是 prompt 中已经不再需要承担的职责，例如最终展示样式、固定章节标题、过重的数量约束，应下放到 schema、代码或模板层
- 凡是最终前端/HTML/PDF 要展示的新字段，如段落化预测正文、证据链、法规说明，必须在 schema 中有清晰位置，不能只靠代码后补

#### 提示词重构目标

这轮提示词与 schema 重构，不是单纯“更稳定输出 JSON”，而是要同时实现：

- 深读更有标题感和判断力
- 预测更像推演文字，而不是字段卡片
- 审核更精准克制，不把负面情绪泛化成违规
- 前言、深读、预测、审核整体摆脱公文腔、流水账和模板味

#### 风格硬要求

系统最终生成的报告文字必须满足：

- 有趣但不轻浮
- 有观点但不虚张声势
- 有现场感和画面感
- 有判断和新意
- 不写成公文汇报、政策套话或提纲堆砌

换句话说，重构后的 prompt 目标不是“更像机器产出的规范文本”，而是“更像一份真的有人愿意看的舆情研判成品”。

### 3.4 固定处理配额（写死，不走动态漂移）

这部分直接作为第一版代码里的固定常量，不做复杂自适应。

#### 事件层

- 事件候选池：Top 20
- 深读事件数：5
- 审核事件数：8

说明：

- `Top 20` 只用于建立事件候选池和全局态势判断，不代表 20 个事件都走重分析。
- `深读 5 个` 与你当前报告结构一致，正文重点深读仍然只保留 5 个事件。

### 3.5 多格式一致性交付要求

本次改造不接受“前端一套、HTML 一套、PDF 一套、Markdown 一套”的分裂式实现。最终交付必须满足：

- 同一份报告在前端结构化页、HTML、PDF、Markdown 中的主章节顺序一致
- 同一份报告在不同格式中的深读事件数量、违规案例数量、预测主题数量一致
- “第三部分：违规风险透视”在所有格式中都只放统计与阶段总结
- “附录：违规数据监测”在所有格式中都必须保留详细违规案例明细
- “第二部分：重点舆情深读”在所有格式中都显式展示：
  - `事件概况`
  - `舆论观点画像`
  - `深度研判`
- “第四部分：未来趋势与战略预警”在所有格式中都以：
  - `预警摘要`
  - `预测点标题`
  - `段落式正文`
  的方式展示，不再把内部底稿字段直排给用户

验收时默认以 PDF 成品作为当前视觉基准，再反向检查 HTML、前端结构化页和 Markdown 是否对齐。
- `审核 8 个` 的范围略大于深读，用来补足报告里的风险扫描覆盖面。

审核事件的选法固定为：

1. 先从 ETL + 热度统计结果里拿到 `Top 20` 事件候选池
2. 其中按热度和去重后的结果，前 `5` 个直接进入深读事件
3. 审核事件先无条件包含这 `5` 个深读事件
4. 再从剩余事件里，继续按 `total_heat` 降序补足后续 `3` 个事件

也就是说：

- 深读事件 = `热度最高且去重后的前 5 个`
- 审核事件 = `热度去重后的前 8 个`

#### 帖子层

- 深读事件：每个事件最多取 12 个帖子
- 审核事件：每个事件最多取 15 个帖子

说明：

- 深读要的是代表性和可写性，`12` 个帖子足够做观点分层，不需要把 15 个都喂给写作链。
- 审核要的是覆盖面，所以保留 `15` 个帖子的上限，与当前代码的帖子量级保持接近。

帖子选法固定为：

- 从 [mongo_manager.py](/e:/graduation-project/Backend/app/db/mongo_manager.py#L269) 取与事件 `related_keywords` 命中的帖子
- 按 `liked_count` 降序排序
- 按 `note_id` 去重
- 深读取前 `12` 个
- 审核取前 `15` 个
- 不足则全取

#### 评论层

- 深读链：
  - 每个帖子评论样本上限：20
  - 取法固定为：按点赞数降序取前 20 条
- 审核链：
  - 每个帖子原始抓取评论上限：100
  - 进入 `FAST_LLM` 候选分流的评论/帖子片段：每批最多 20 条
  - 进入 `STRONG_LLM` 终裁的条目：每批 3~5 条

说明：

- 深读链第一版不做复杂抽样，直接使用高赞评论，最省实现成本，也最符合工程化思路。
- 审核链不能像现在那样直接塞 `200` 条评论进一个 prompt，所以改成“`100` 条原始评论分批送 `FAST_LLM` 初筛，再分层送审”。

审核评论的选法固定为：

- 每个审核帖子先取评论候选池 `100` 条
- 取法为：`高赞前 60 条 + 最新 40 条`
- 按 `comment_id` 或内容去重
- 去空评论、去纯表情评论
- 不足 `100` 条则按实际返回

之后不是 100 条全送模型，而是：

1. 这 `100` 条按每批 `20` 条送 `FAST_LLM` 做初筛
2. `FAST_LLM` 认为需要终裁的，再按每批 `3~5` 条送 `STRONG_LLM`

#### 评论取样规则

第一版固定为：

- 深读链评论样本 = `高赞前 20 条`
- 审核链原始评论池 = `高赞 60 + 最新 40` 去重后截断为 100

这样做的原因是：

- 深读链目标是快速抓住主流传播面和代表性观点，直接看高赞最简单也最稳定。
- 审核链目标是尽量别漏，所以仍然保留“高赞 + 最新”的更宽覆盖方式。

#### 这部分与现有代码的关系

不是完全沿用，也不是推倒重来，而是：

- **保留现在的量级感**：
  - 事件候选池仍然是 `20`
  - 深读仍然是 `5`
  - 帖子量级仍然接近 `15`
- **重做最有问题的地方**：
  - 不再默认 `200` 条评论全量送 LLM
  - 不再让深读和审核共用同一份粗糙输入
  - 不再让强模型直接面对整池长上下文

## 4. 具体代码改造方案

## 4.1 配置体系改造

### 要改的文件

- [config.py](/e:/graduation-project/Backend/app/core/config.py)
- [main.py](/e:/graduation-project/Backend/app/api/main.py#L550)
- [Settings.vue](/e:/graduation-project/frontend/src/views/Settings.vue#L89)

### 当前问题

当前只支持一套：

- `LLM_MODEL`
- `LLM_BASE_URL`
- `ZHIPU_API_KEY`

这无法支撑“快模型做压缩/筛选，强模型做终裁/定稿”。

### 必改方案

在 [config.py](/e:/graduation-project/Backend/app/core/config.py#L8) 中新增：

```text
FAST_LLM_MODEL
FAST_LLM_BASE_URL
FAST_LLM_API_KEY

STRONG_LLM_MODEL
STRONG_LLM_BASE_URL
STRONG_LLM_API_KEY
```

兼容策略：

- 若只配了一套，则 `FAST` 和 `STRONG` 都回退到当前 `LLM_*`
- 但前端设置页改成显示两组配置

### 必新增文件

- `Backend/app/core/llm_factory.py`

职责：

- 暴露 `get_fast_llm()` 和 `get_strong_llm()`
- 统一构造 `ChatOpenAI`
- 统一设置 timeout、temperature、重试次数

这样后续 B/C/D/E 不再直接手写模型初始化。

## 4.2 ETL 与事件归并改造

### 要改的文件

- 本阶段不改主逻辑
- 维持 [event_manager.py](/e:/graduation-project/Backend/app/etl/event_manager.py)
- 维持 [stats.py](/e:/graduation-project/Backend/app/services/stats.py)
- 维持 [nodes.py](/e:/graduation-project/Backend/app/agents/nodes.py#L256) 里的现有去重选题方式

### 当前问题

当前 [event_manager.py](/e:/graduation-project/Backend/app/etl/event_manager.py#L61) 只做“完全相同词条热度累加”。  
这会导致：

- 同一事件的不同热搜别名拆开
- `related_keywords` 基本只有 1 个词
- 后面 `source_keyword` 匹配帖子时召回不全

### 本阶段结论

这块第一阶段不改。

原因：

- 你的当前目标不是做全量高精度事件图谱，而是先把报告质量、审核链和渲染链做起来。
- 现有 [nodes.py](/e:/graduation-project/Backend/app/agents/nodes.py#L256) 已经会在选题阶段做“按热度往下选 + LLM 判断是否与前面重复事件”的去重。
- 对报告正文来说，最重要的是“最后入选深读的前 5 个事件不要重复”，这件事当前逻辑已经基本能完成。
- 如果现在强行重做 ETL 归并，会显著增加复杂度，但对第一阶段报告质量的收益不一定最大。

### 保留方式

- 热度统计仍按当前方式生成事件候选池
- 深读事件仍按当前方式确定：
  - 先按热度排序
  - 再由 LLM 判断和已选事件是否重复
  - 若重复则跳过，继续补下一个
- 审核事件仍然直接取热度去重后的前 8 个事件，不新增事件归并层

### 这一块后面只保留一个轻量观察项

后续如果真的发现帖子召回明显不全，再单独补一个很轻的增强：

- 不改 ETL 主逻辑
- 只在 Node A 抓帖子时，对 `related_keywords` 做极轻的补词处理
- 但这不作为第一阶段必做项

## 4.3 Node A 证据装配改造

### 要改的文件

- [nodes.py](/e:/graduation-project/Backend/app/agents/nodes.py#L149)
- [mongo_manager.py](/e:/graduation-project/Backend/app/db/mongo_manager.py#L269)

### 当前问题

Node A 现在只装配：

- 帖子正文
- 评论纯文本列表
- 简单媒体链接

这导致后续：

- B 无法做真正的舆论画像
- C 无法逐条判定
- D 无法基于生活场景预测

### 必改方案

#### `MongoManager.get_posts_by_keywords`

除了现有字段，还要保留：

- `create_date_time`
- `liked_count`
- `comments_count`
- `source_keyword`
- `full_content`

#### `MongoManager.get_comments_by_post_ids`

除了现有字段，还要保留：

- `comment_id`
- `create_date_time`
- `comment_like_count`

#### `agent_a_node` 新输出

每个 `post_packet` 改成：

```text
{
  note_id,
  db_id,
  content,
  source_keyword,
  create_date_time,
  liked_count,
  comments_count,
  media_context,
  comment_items: [
    {
      db_id,
      comment_id,
      content,
      create_date_time,
      comment_like_count
    }
  ]
}
```

### 第一阶段不新增中间构建层

- 不新增 `Backend/app/services/evidence_builder.py`
- 直接在 `agent_a_node` 里整理简化后的 `post_packet`
- 等后续确实出现复用压力，再考虑抽成独立构建层

### 代表性评论抽样规则

第一版不做复杂分桶，直接固定为：

- 按 `comment_like_count` 降序取前 20 条
- 去空、去纯表情、去完全重复内容
- 不足 20 条则按实际条数返回

这样最贴合当前 `weibo_comments` 数据结构，也最容易直接落到 [mongo_manager.py](/e:/graduation-project/Backend/app/db/mongo_manager.py) 和 [nodes.py](/e:/graduation-project/Backend/app/agents/nodes.py#L167)。

## 4.4 B 节点：重点舆情深读改造

### 要改的文件

- [opinions.py](/e:/graduation-project/Backend/app/services/opinions.py)
- [prompts.py](/e:/graduation-project/Backend/app/core/prompts.py)
- [schemas.py](/e:/graduation-project/Backend/app/core/schemas.py)
- [nodes.py](/e:/graduation-project/Backend/app/agents/nodes.py#L328)

### 当前问题

- 搜索词太弱，只搜“事件详情 官方通报”
- Reduce 输出风格过度智库化
- 没有编辑标题
- 没有一句话结论

### 必改方案

#### `opinions.py` 改成双阶段

##### Stage 1：`FAST_LLM` 做 per-post map

输入：

- 单帖正文
- 抽样评论
- 帖子元信息
- 联网搜索补充事实

输出：

- `fact_slice`
- `opinion_buckets`
- `conflict_points`
- `emotion_labels`
- `representative_quotes`
- `risk_signals`

##### Stage 2：`STRONG_LLM` 做 event-level reduce

输入：

- event 级所有 post map slices
- 统计量
- 代表性引用
- 搜索背景

输出结构改为：

```text
EventAnalysisReport
  editorial_title
  one_line_verdict
  event_overview
  public_opinions
  depth_analysis
  key_quotes[]
```

### 深读标题策略

`editorial_title` 必须满足：

- 不是原始热搜词照抄
- 不低俗，但要有钩子
- 与结论方向一致

### 一句话判断

新增 `one_line_verdict`，强制第一句先给判断，不许先铺陈背景。

### 联网搜索策略

`opinions.py` 不能再只搜一种 query。  
固定改成三类搜索：

1. `事件名 + 官方通报`
2. `事件名 + 最新进展`
3. `事件名 + 争议点/网友质疑`

每类取少量结果即可，由 `FAST_LLM` 先压缩，再喂给 `STRONG_LLM`。

## 4.5 C 节点：违规审核链彻底重构

### 要改的文件

- [compliance.py](/e:/graduation-project/Backend/app/services/compliance.py)
- [prompts.py](/e:/graduation-project/Backend/app/core/prompts.py)
- [schemas.py](/e:/graduation-project/Backend/app/core/schemas.py)
- [nodes.py](/e:/graduation-project/Backend/app/agents/nodes.py#L402)
- [chroma_manager.py](/e:/graduation-project/Backend/app/db/chroma_manager.py)

### 当前问题

1. 一次把主贴 + 大量评论送进一个 prompt。
2. 一旦触发过滤，就强脱敏、截断、默认安全。
3. 最终输出是按帖子聚合，而不是逐条判定。
4. RAG 是按整组违规项检索，不是按单条检索。

### 必改方案

#### 第一步：拆成两层审核

##### Layer A：`FAST_LLM` 做全量候选池初筛

新增 prompt：

- `AGENT_C_CANDIDATE_FILTER_TEMPLATE`

输入：

- 20 条以内的评论/帖子片段
- 每条只给短文本 + index + 最小上下文

输出：

- `suspect_indices`
- `candidate_category`
- `needs_strong_judge`

这一步不写长理由，只做分流。

##### Layer B：`STRONG_LLM` 做逐条终裁

新增 schema：

```text
ViolationCase
  source_type
  source_index
  source_id
  raw_text
  quote
  target
  category
  reasoning
  confidence
  is_violation
```

调用方式：

- 一次最多审 3~5 条
- 每条单独裁决
- 不再按帖子整体裁决

### 为什么这样能减少 API 过滤

因为现在不是把“整池高毒评论”丢给一个模型，而是：

- 快模型分批扫评论池
- 强模型只看少量候选项

这比当前 [compliance.py](/e:/graduation-project/Backend/app/services/compliance.py#L230) 的全量 batch 审法更稳。

### 关键判定边界

必须直接写进 prompt 和 schema 注释：

- 单纯负面情绪，不算违规
- 粗口但没有攻击对象，不默认违规
- 对事件的强烈批评，不默认违规
- 只有明确触碰平台规则或法规边界，才判违规
- 证据不够或 provider 拦截时，不计入前端违规展示，只做后端内部日志标记

### 过滤 fallback 机制

这部分只做轻量两层 fallback，不做复杂回退树。

#### `FAST_LLM` 初筛 fallback

固定策略：

1. 正常按每批 `20` 条做初筛
2. 若 provider 拦截，则直接拆成每批 `5` 条重试一次
3. 若仍拦截，则切到备用 key / 备用模型再试一次
4. 若仍失败，则丢弃该批，不进入前端展示，不计违规，只记 `blocked_count`

#### `STRONG_LLM` 终裁 fallback

固定策略：

1. 正常按每批 `3~5` 条做终裁
2. 若 provider 拦截，则改单条终裁
3. 若仍拦截，则切到备用 key / 备用模型再试一次
4. 若仍失败，则丢弃该条，不进入前端展示，不计违规，只记 `blocked_count`

#### fallback 的产品口径

- 前端报告只展示 `确认违规` 的 case
- 不展示“待复核”
- 不展示“被 provider 拦截”
- 被拦截的内容只保留后端内部日志、计数和质量门控信号
- 违规统计只统计 `is_violation = true` 的 case

### 审核结果存储结构

`violation_info` 改成：

```text
{
  post_case: {...} | null,
  comment_cases: [...],
  overall_risk_level,
  matched_laws_by_case: {...},
  audit_version,
  blocked_count
}
```

不再使用：

- 单个 `reasoning`
- 单个 `disposal_suggestion`
- 单包 `matched_laws` 覆盖整行

## 4.6 法条 RAG 改造

### 当前问题

[chroma_manager.py](/e:/graduation-project/Backend/app/db/chroma_manager.py#L95) 现在的问题是：

- 只做 dense search
- 过度依赖 HyDE
- query 来自“整组违规项”

### 必改方案

#### 向量库内容本身第一阶段不动

保持现有 [init_weibo_rules.py](/e:/graduation-project/Backend/app/scripts/init_weibo_rules.py) 不变：

- 不改规则数据
- 不改 metadata 结构
- 不重建“原始条文库”

当前规则库字段设计在第一阶段视为合理，先把提升点放在“怎么检索、怎么挂接到单条 case”上。

#### `chroma_manager.py` 检索改法

按单条 `ViolationCase` 检索，不再按帖子检索。

检索顺序固定为：

1. `category_filter` 先过滤
2. 直接 query 检索
3. 若结果弱，再启用 HyDE
4. 返回带 score 的 top 3

HyDE 不再默认开启，而是只在“直接检索弱匹配”时调用。

原因：

- 省一次 API
- 降低过滤概率
- 更贴合两把 key 的约束

#### `compliance.py` 改法

为每条 `ViolationCase` 单独做 law match：

```text
law_query = category + quote + reasoning
```

输出：

- `primary_law`
- `alternative_laws`
- `law_match_score`
- `law_reason`

## 4.7 D 节点：趋势预测改造

### 要改的文件

- [nodes.py](/e:/graduation-project/Backend/app/agents/nodes.py#L667)
- [prompts.py](/e:/graduation-project/Backend/app/core/prompts.py#L327)
- [schemas.py](/e:/graduation-project/Backend/app/core/schemas.py#L227)

### 当前问题

- 输入只有 `event_overview` 和 `overall_risk_level`
- 没有把真实生活场景塞进去
- 最终每个 topic 经常只有一个点

### 必改方案

#### 输入升级

Node D 的输入改为：

- B 产出的 `one_line_verdict`
- B 的 `public_opinions`
- B 的 `key_quotes`
- C 的高风险 case categories
- C 的事件级风险簇
- 联网搜索得到的历史同期摘要
- Tavily 搜索的未来节点摘要

历史上下文注入固定为：

- 不依赖 `historical_events`
- 不启用 `agent_historical`
- 直接通过联网搜索获取“往年同期 + 类别 + 舆情”结果
- 由 `FAST_LLM` 先压缩成最多 `3` 条历史摘要后再注入 D

未来上下文注入固定为：

- 通过固定三类搜索获取未来节点信息
- 由 `FAST_LLM` 先压缩成最多 `5` 条未来信号摘要后再注入 D

第一阶段 D 的上下文只允许注入摘要，不允许直接注入：

- 原始帖子正文
- 原始评论列表
- B 的完整深读正文
- C 的全量 case 列表
- Tavily 原始长文本

#### 预测结构改造

每个 `ForecastTopic` 改成：

```text
topic_name
background
audience
scene_opening
points[2..4]
```

每个 `ForecastPoint` 改成：

```text
subtitle
trigger
spread_path
offline_scene
online_scene
evidence_basis
likelihood
content
```

这里要明确区分两层：

- **内部结构化底稿**
  - `trigger`
  - `spread_path`
  - `offline_scene`
  - `online_scene`
  - `evidence_basis`
- **面向用户的最终展示**
  - `subtitle`
  - `summary_paragraph`（由 LLM 基于上述底稿组织成段落）

也就是说：

- D 节点内部继续保留这些字段，用于约束预测质量和防止空话
- 但 E 节点、前端结构化页、HTML 和 PDF 的最终展示，不再把这些字段逐条罗列成清单
- 预测区主展示改为：
  - `预警摘要`
  - `预测点标题`
  - `段落式正文`

目标是让观众读到的是自然、有张力、可阅读的段落，而不是字段化的风险卡片或提纲。

### 输出要求

每个 topic 必须至少 2 个点。  
质量门控直接检查点数，不够就重试。

### 联网搜索改法

当前 ReAct 太散，建议改成固定三类搜索：

1. `目标周期 + 类别 + 日程/政策/考试`
2. `往年同期 + 类别 + 舆情`
3. `当前事件主线 + 下月 + 风险`

由 `FAST_LLM` 先做搜索摘要，再交给 `STRONG_LLM` 写预测。

## 4.8 E 节点：报告总编与渲染改造

### 要改的文件

- [report.py](/e:/graduation-project/Backend/app/services/report.py)
- [schemas.py](/e:/graduation-project/Backend/app/core/schemas.py)
- [main.py](/e:/graduation-project/Backend/app/api/main.py#L424)
- 新增渲染文件

### 当前问题

- 前言输入太粗
- 最终报告对象不存在
- Markdown 内嵌 CSS
- 前端只能渲染大字符串

### 必改方案

#### 第一步：引入 `ReportDocument`

在 `schemas.py` 中新增主报告结构：

```text
ReportDocument
  meta
  preface
  overview_table
  deep_reads[]
  forecasts[]
  compliance_summary
  compliance_clusters[]
  compliance_cases[]
  appendix
```

报告骨架固定为：

- 第一部分：本期热点舆情总览
- 第二部分：重点舆情深读
- 第三部分：违规风险透视
- 第四部分：未来趋势与战略预警
- 附录：违规数据监测

这些章节标题、章节顺序、章节引导语由模板固定控制，不交给模型临时决定。

#### 第二步：`report.py` 不再直接拼长 Markdown

拆成三层：

- `compose_report_document(state) -> ReportDocument`
- `render_markdown(report_doc) -> md`
- `render_html(report_doc) -> html`
- `render_pdf(html) -> pdf`

其中：

- HTML/PDF 是正式成品渲染主路径
- Markdown 只作为兼容导出与文本归档格式
- 现有 CSS 的固定章节样式、表格样式、留白和层级感，应迁移到 HTML 模板中承接

#### 固定语句与模板文案

以下内容应从“模型生成”改为“模板固定文案，可统一优化后写死”：

- 章节标题
- 章节开头引导语
- 统计表说明语
- 违规案例区说明语
- 趋势预测过渡语
- 附录导语

原则：

- 可以优化现有固定语句
- 但优化结果应写入 HTML 模板或渲染层
- 不应交给模型每次自由生成

#### 热点总览表固定字段

“本期热点舆情总览”固定为 4 列：

- 序号
- 时间
- 事件名称
- 热度值

不在该表中展示 `related_keywords` 等内部召回字段。

### 前言改法

前言输入不能再只吃：

- Top15 标题
- 违规总数
- 预测标题

而要改成：

- 本期主线事件簇
- B 的一线判断
- C 的风险类型分布
- D 的未来风险耦合点

前言结构改成：

- `thesis`
- `overview`
- `characteristics[2..4]`
- `compliance_perspective`
- `trend_connection`
- `conclusion`

不再强制“其一其二其三”的模板渲染。

### 深读渲染改法

每个深读 section 显示：

- `editorial_title`
- `one_line_verdict`
- `事件概况`
- `舆论观点画像`
- `深度研判`
- `关键引用`

这里有一个固定渲染约束：

- 后端结构里必须保留 `event_overview / public_opinions / depth_analysis`
- 前端详情页、HTML 模板和 PDF 导出里也必须把它们显式渲染成三个可见小标题：
  - `事件概况`
  - `舆论观点画像`
  - `深度研判`

禁止只把三段内容顺着输出而不标标题，否则 PDF 和导出页会出现“内容已经生成，但结构看不出来”的问题。

### 审核渲染改法

附录不再以“一个超长 6 列大表”作为唯一呈现方式。  
报告正文改成：

- 风险概览
- 事件级风险簇摘要
- 本期违规态势总结

这不代表取消违规详情展示，而是调整分工：

- 正文只负责统计信息、类型分布、风险概览和阶段性总结
- 报告末尾附录必须保留完整的“违规案例明细”
- 不再让正文中的统计区承担案例逐条阅读功能

附录中的“违规案例明细”固定字段为：

- 来源类型
- 所属事件
- 违规类别
- 风险等级
- 违规摘录
- 判定理由
- 主要依据
- 证据链
- 处置建议

展示口径固定为：

- 评论 case：展示评论原文摘录
- 帖子 case：展示帖子违规摘录，不展示整帖全文
- 不展示 `confidence`
- 不展示内部 id / provider 拦截信息 / blocked_count

附录结构建议固定为：

- 附录 A：违规统计表
- 附录 B：违规案例明细

其中“违规案例明细”可以是分组表格或分组卡片，但必须做到：

- 每条帖子/评论独立一行或一张卡
- 理由、法规、证据链、风险等级、处置建议逐条对应
- 可以按事件分组，但不能只给总体理由和总体法条

## 4.9 报告下载与导出改造

### 要改的文件

- [report.py](/e:/graduation-project/Backend/app/services/report.py#L997)
- [main.py](/e:/graduation-project/Backend/app/api/main.py#L424)
- 新增 HTML/PDF 渲染器

### 当前问题

[report.py](/e:/graduation-project/Backend/app/services/report.py#L1000) 已经明确承认：

- `xhtml2pdf` 中文支持差
- 现在实际只存 md

### 必改方案

#### 新增文件

- `Backend/app/services/render_html.py`
- `Backend/app/services/render_pdf.py`
- `Backend/app/templates/report_base.html`
- `Backend/app/templates/report_detail.html`

#### 工具选型固定

- HTML 模板：`Jinja2`
- PDF 主渲染：`Playwright`
- PDF 回退：`xhtml2pdf / reportlab`

#### 导出产物

每次报告生成后落盘：

- `*.json`
- `*.md`
- `*.html`
- `*.pdf`

API 增加：

- `GET /api/reports/{id}/json`
- `GET /api/reports/{id}/html`
- `GET /api/reports/{id}/pdf`

兼容旧接口：

- 旧 `/download` 默认下 md
- 前端改成格式选择下载

## 4.10 前端展示改造

### 要改的文件

- [ReportDetail.vue](/e:/graduation-project/frontend/src/views/ReportDetail.vue)
- [Reports.vue](/e:/graduation-project/frontend/src/views/Reports.vue)
- [api/index.js](/e:/graduation-project/frontend/src/api/index.js)
- 新增组件若干

### 当前问题

[ReportDetail.vue](/e:/graduation-project/frontend/src/views/ReportDetail.vue#L45) 现在只是：

- 拉 Markdown
- `marked` 渲染
- 表格超长就弹窗

这不可能优雅展示逐条审核案例。

### 必改方案

#### 报告详情页拆两层

##### 主页面：结构化报告视图

新增：

- `frontend/src/views/ReportDetailStructured.vue`

展示：

- 前言卡
- 热点总览表
- 深读卡片组
- 趋势预警卡片组
- 违规风险总览
- 事件级风险簇

##### 次页面：原始 Markdown 视图

保留旧 `ReportDetail.vue` 作为“原始导出预览”，不再作为主入口。

#### 新增组件

- `ViolationClusterList.vue`
- `ViolationCaseDrawer.vue`
- `DeepReadCard.vue`
- `ForecastCard.vue`
- `ReportArtifactBar.vue`

### 审核展示固定方案

主页面不再全量平铺所有 case。

默认展示：

1. 风险统计卡
2. 类别分布
3. 事件分组
4. 每个事件下展示若干风险簇
5. 点击风险簇，打开 `ViolationCaseDrawer`

`Drawer` 内展示逐条 case：

- 来源类型
- 违规类别
- 风险等级
- 违规摘录
- 判定理由
- 主要依据
- 处置建议

展示口径固定为：

- 评论 case：展示评论原文摘录
- 帖子 case：只展示帖子违规摘录，不展示整帖全文
- 不展示 `confidence`
- 不展示内部 id / provider 拦截信息 / blocked_count
- 若需要更多上下文，后续可在抽屉内补“所属帖子摘要”，但第一阶段不是必做项

### 下载按钮

新增：

- 下载 Markdown
- 下载 PDF
- 下载 HTML

## 4.11 前端设置与连接配置修复

### 要改的文件

- [Settings.vue](/e:/graduation-project/frontend/src/views/Settings.vue)
- [api/index.js](/e:/graduation-project/frontend/src/api/index.js)
- [app.js](/e:/graduation-project/frontend/src/stores/app.js)
- [Logs.vue](/e:/graduation-project/frontend/src/views/Logs.vue)
- [main.py](/e:/graduation-project/Backend/app/api/main.py)
- [config.py](/e:/graduation-project/Backend/app/core/config.py)

### 当前问题

当前“设置页看起来可配，但很多并未真正生效”，主要问题如下：

- 后端连接测试是假实现，`testConnection()` 只做前端延时提示，没有真实请求
- `backendForm.url` / `backendForm.timeout` 没有写回 `store.settings`，所以设置页改地址不会影响真实 API 请求
- `axios` 的 `timeout` 固定写死为 `60000`，设置页的超时时间输入框目前无效
- `Logs.vue` 的 WebSocket 地址写死为 `ws://localhost:8000/ws/logs`，没有跟随后端地址配置变化
- 前端 LLM 默认值与后端真实默认值不一致，设置加载失败时会误导用户
- `Settings.vue` 里写了伪真实 API Key 占位字符串，不适合继续保留在源码中
- 后端 `/api/settings/llm` 目前只更新运行时内存和进程环境变量，服务重启后配置可能丢失
- 前端允许修改后端 API 地址，但后端 CORS 仍只放行本地 `5173`，远程部署时会脱节
- Tavily 联网搜索配置目前只能写后端环境变量，前端无法直接调整和测试

### 必改方案

#### 后端连接设置真正接线

`Settings.vue` 的“后端连接配置”改成真实设置链路：

- 页面加载时，从 `store.settings` 回填 `backendForm`
- 点击“保存/测试”时，调用 `store.updateSettings()` 写入：
  - `apiUrl`
  - `timeout`
- API 层统一从 `store/localStorage appSettings` 读取当前地址与超时

#### 后端连接测试改成真实探测

前端“测试连接”不再是假提示，改为真实请求：

- 优先调用 `GET /api/health`
- 成功后显示真实连通结果与延迟
- 失败时展示可读错误信息

#### API 超时跟随设置

[api/index.js](/e:/graduation-project/frontend/src/api/index.js) 改成动态读取：

- `baseURL` 来自 `appSettings.apiUrl`
- `timeout` 来自 `appSettings.timeout`

不能再固定为 `60000`。

#### WebSocket 地址统一派生

[Logs.vue](/e:/graduation-project/frontend/src/views/Logs.vue) 不能继续写死 `localhost:8000`，应由当前 API 地址推导：

- `http://...` -> `ws://.../ws/logs`
- `https://...` -> `wss://.../ws/logs`

这样日志页才会跟随连接设置生效。

#### LLM 设置页与后端真实默认值对齐

前端不再写死误导性默认值：

- 模型名默认值应留空或以接口返回为准
- Base URL 默认值应以后端返回为准
- API Key 输入框只显示空值或掩码返回值
- 删除源码中的伪真实 key 示例值

#### LLM 配置持久化策略明确化

第一阶段至少明确两件事：

- 前端提示“当前保存仅对运行中服务生效，重启后需重新加载或另做持久化”
- 若后端允许，再补一层真正的持久化落盘（例如写回 `.env` 或单独配置文件）

在未实现真正持久化前，不能让 UI 误导用户为“永久保存”。

#### CORS 与可配置地址对齐

如果继续支持前端可配置后端地址，则后端 CORS 也要同步改造：

- 不再只写死 `localhost:5173`
- 至少支持从环境变量读取允许的前端 Origin 列表

否则“前端可改地址”在非本地环境下仍然会被浏览器拦截。

## 4.12 质量门控改造

### 要改的文件

- [quality_gate.py](/e:/graduation-project/Backend/app/agents/quality_gate.py)

### 当前问题

现在门控的问题是：

- 过度依赖“完整性 / 准确性 / 深度”这类整体主观评分
- 一旦低分，容易触发整节点重试
- B/C/D 的坏项没有被拆开定位
- 评分结果很难直接对应到“该修哪个字段、该补哪个 case”

### 必改方案

#### 总体改法

- 去掉“完整性 / 准确性 / 深度”作为主门控决策条件
- 主门控改成代码级检查项
- 只对坏项做 repair，不对整节点做默认重跑
- LLM reviewer 若保留，只能作为内部参考，不参与主路由

#### B 门控改法

- 是否生成 `editorial_title`
- 是否生成 `one_line_verdict`
- 是否引用了至少 2 条关键 quotes
- 是否存在重复事件
- 是否缺少 5 个有效深读事件

处理策略：

- 不整段重跑 B
- 缺标题 / 缺一句话判断 / quotes 不足：只对对应事件做 reduce repair
- 少事件 / 事件重复：只补缺失事件，不重跑已通过事件

#### C 门控改法

- 是否逐条 case 一一对应
- 是否存在 `reasoning` 为空
- 是否存在 `primary_law` 为空
- 是否仍然输出“总体理由 + 总体法条”

处理策略：

- 不整段重跑 C
- 缺理由 / 缺法条：只修对应 case
- 个别帖子结构坏掉：只重跑该帖子
- 不允许因为少量坏 case 触发 8 个事件全量重审

#### D 门控改法

- 每个 topic 是否至少 2 个点
- 是否包含生活场景
- 是否只是当前热点复述
- 每个 point 是否有 `trigger / spread_path / offline_scene / online_scene / evidence_basis`

处理策略：

- D 允许整段重跑一次
- 因为 D 输入已经是压缩摘要，整段重跑成本可接受
- 超过一次后直接降级放行，不再继续放大耗时

#### E 门控新增

- 是否生成 `ReportDocument`
- 是否前言有 `thesis`
- 是否 HTML/MD/PDF 产物完整

#### 重试策略

- 不再把“整体低分”作为整节点重试依据
- B/C 默认不整段重跑，只做局部 repair
- D 最多整段重跑一次
- 若保留重试反馈，必须是结构化坏项列表，而不是模糊 `improvement_hint`

目标：

- 避免 B/C/D 因整体评分不佳而重复执行两遍
- 将质量门控的额外耗时控制在小幅增量范围
- 正常情况下只增加代码检查开销，而不是增加整链 LLM 开销

## 5. 实施顺序（必须按这个顺序）

这是我建议你后面让我真正动代码时的落地顺序，不能乱。

### 第一阶段：配置与工厂

先改：

- `config.py`
- `main.py` LLM settings API
- `Settings.vue`
- 新增 `llm_factory.py`

目标：

- 系统先支持双模型配置

### 第二阶段：Node A + 数据装配

先改：

- `mongo_manager.py`
- `event_manager.py`
- `nodes.py` Node A

目标：

- 给 B/C/D 真正可用的证据结构

### 第三阶段：C 审核链

先改：

- `compliance.py`
- `chroma_manager.py`
- `schemas.py`
- `prompts.py`

目标：

- 先把“误判 + 过滤 + 一锅炖展示”这条最影响可信度的链修掉

### 第四阶段：B 深读链

先改：

- `opinions.py`
- `schemas.py`
- `prompts.py`

目标：

- 让标题、判断、深读质量起来

### 第五阶段：D 预测链

先改：

- `nodes.py`
- `prompts.py`
- `schemas.py`

目标：

- 让预测真正有未来风险点和生活场景

### 第六阶段：E 报告对象与导出

先改：

- `report.py`
- `main.py`
- 新增 render/template 文件

目标：

- 产出 `json/html/pdf/md`

### 第七阶段：前端结构化展示

最后改：

- `ReportDetail.vue`
- 新增结构化组件

目标：

- 用新报告 JSON 把体验真正拉起来

## 6. 这份方案为什么现在可以直接进代码

因为它已经把以下关键问题全部贴到了现有代码：

- 用的就是你现在的 `hot_trends_history / weibo_contents / weibo_comments`
- 保留你现在的 LangGraph 主干，不做大拆
- 明确了两个 API key 的固定职责
- 指定了每一步该改哪些现有文件
- 指定了必须新增哪些文件
- 明确了先后顺序
- 明确了哪些现有逻辑必须删除或替换

所以这不是“未来愿景”，而是一份可以直接拿来批准后开改的代码前置方案。

## 7. 最终批准标准

如果你批准这份方案，下一步我建议直接进入“实施计划”或“第一阶段代码改造”。

我后续改代码时会严格按这份文档执行，不再重新发散方案。

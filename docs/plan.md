# 舆情分析系统重构方案 v2.0

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 增强现有 LangGraph 工作流的质量控制与自主决策能力

**Architecture:** 保留扁平线性图 + 条件分支，通过增强 quality_gate 和 ReAct Agent 实现智能化

**Tech Stack:** LangGraph, LangChain, Tavily Search, MongoDB, ChromaDB

---

## 1. 项目背景与目标

### 当前架构
Backend/ 项目基于 LangGraph 的线性工作流：
```
START → Classify → A(ETL) → [B∥C] → QualityGate → D → QualityGate → E → END
```

### 存在问题

| Agent | 问题 | 严重程度 |
|-------|------|----------|
| Agent D | `nodes.py` 700-780行硬编码搜索词，缺乏自主性 | 高 |
| Agent E | 前言生成缺乏数据约束，容易产生数字幻觉 | 中 |
| Agent B/C | quality_gate 重试次数过少 (MAX_RETRIES=1)，评估逻辑过于宽松 | 中 |
| All Agents | `prompts.py` 中的 Prompt 冗长、结构不统一，缺乏最佳实践 | 中 |

### 重构目标
在**保留现有架构**的基础上，实现：
1. **Prompt 优化**：精简所有 Agent 的 Prompt，统一结构，移除冗余 Few-Shot
2. **Agent D ReAct 化**：自主构造查询词，但 Prompt 约束时间与领域格式
3. **增强 quality_gate**：任意维度 < 8 分即重试，反馈注入原 Prompt
4. **Agent E 数字校验**：代码级正则校验，消除幻觉

---

## 2. 核心原则

### 执行前必读文件
- `app/agents/workflow.py` - 主工作流
- `app/agents/nodes.py` - 各 Agent 节点逻辑
- `app/agents/quality_gate.py` - 质量门控
- `app/services/*.py` - 业务逻辑（**只复用，不重写**）
- `app/core/prompts.py` - Prompt 模板

### 架构决策

| Agent | 模式 | 说明 |
|-------|------|------|
| Agent A | Node (保持不变) | 确定性 ETL 逻辑 |
| Agent B | Node + 增强 quality_gate | 复用现有反思机制 |
| Agent C | Node + 增强 quality_gate | 复用现有反思机制 |
| Agent D | **ReAct Agent** | 自主构造查询词（Prompt 约束格式） |
| Agent E | Node + 代码级校验 | 正则提取 + 数字比对 |

### 不采用 SubGraph 的原因
1. 现有 `workflow.py` 已实现并行执行（B∥C）
2. `quality_gate.py` 已有 LLM 评估 + 重试路由
3. SubGraph 增加维护复杂度，调试困难

---

## 3. 分阶段实施计划

### Phase 0: Prompt 全局优化 (低风险，前置任务)

**目标:** 扫描项目所有 Prompt，精简冗余内容，统一结构，提升 LLM 理解效率

**涉及文件:**
- `app/core/prompts.py` — 主 Prompt 模板文件
- `app/agents/quality_gate.py` — 评估 Prompt

**优化原则:**
1. **统一结构**: 所有 Prompt 遵循 `ROLE → GOAL → INPUT → THINKING → OUTPUT → SELF-CHECK` 结构
2. **精简约束**: 合并重复约束（如 `_WRITING_STYLE_GUIDE` 被多处引用，保留一份即可）
3. **增强反馈插槽**: 确保需要重试的 Prompt 都有 `{improvement_hint}` 占位符
4. **消除冗余**: 移除重复的 `SELF-CHECK` 条目，避免指令膨胀

---

#### Prompt 清单与优化点

| # | Prompt 名称 | 位置 | 有 improvement_hint | 需优化点 |
|---|------------|------|:-------------------:|----------|
| 1 | `AGENT_B_MAP_TEMPLATE` | prompts.py:32 | ❌ | 无反馈插槽，需添加 |
| 2 | `AGENT_B_REDUCE_TEMPLATE` | prompts.py:85 | ✅ (line 188) | SELF-CHECK 重复(QUALITY CHECKLIST + SELF-VERIFICATION)，合并 |
| 3 | `AGENT_C_ANALYSIS_TEMPLATE` | prompts.py:198 | ❌ | Legacy 兜底，较少使用，暂不改动 |
| 4 | `AGENT_C_BATCH_TEMPLATE` | prompts.py:221 | ❌ | 核心批量审查，需添加反馈插槽 |
| 5 | `AGENT_C_EVIDENCE_TEMPLATE` | prompts.py:290 | ❌ | 证据链生成，暂不改动 |
| 6 | `AGENT_D_FORECAST_TEMPLATE` | prompts.py:339 | ✅ (line 428) | `_WRITING_STYLE_GUIDE` 重复引用，精简；SELF-CHECK 与 CORE RULES 有重叠 |
| 7 | `AGENT_E_PREFACE_TEMPLATE` | prompts.py:444 | ❌ | 需添加 `{improvement_hint}` 和 `{stats}` 插槽 |
| 8 | `AGENT_HISTORICAL_DAILY_EXTRACT_TEMPLATE` | prompts.py:588 | ❌ | 独立功能，暂不改动 |
| 9 | `AGENT_HISTORICAL_SUMMARY_TEMPLATE` | prompts.py:610 | ❌ | 独立功能，暂不改动 |
| 10 | `EVENT_DUPLICATE_CHECK_PROMPT` | prompts.py:641 | ❌ | 独立功能，暂不改动 |
| 11 | `_EVAL_PROMPT` | quality_gate.py:60 | ❌ | 评估 Prompt，Phase 1 优化 |

---

#### Step 0.1: 优化 Agent B Prompt

**文件:** `app/core/prompts.py`

**AGENT_B_MAP_TEMPLATE (line 32-83)**
- [ ] 添加 `{improvement_hint}` 插槽在末尾
- [ ] SELF-CHECK 保持，用于单贴分析自检

**AGENT_B_REDUCE_TEMPLATE (line 85-196)**
- [ ] QUALITY CHECKLIST (line 152-159) 与 SELF-VERIFICATION (line 161-186) 内容重复，合并为一个 `SELF-CHECK` 块
- [ ] `{improvement_hint}` 已存在 (line 188)，保持

**代码示例:**
```python
# 合并前（冗余）
### QUALITY CHECKLIST
- [ ] 事件概述是否包含关键时间节点和冲突焦点？
- [ ] 舆论观点是否分层梳理（至少4项）？
...

### SELF-VERIFICATION（生成后自检）
**请生成完整报告后，逐项检查**：
1. 事件概述部分：
   - [ ] 不少于8句话？
...

# 合并后（精简）
### SELF-CHECK（生成后自检）
**事件概述**: 不少于8句话？包含时间节点+冲突焦点？未编造日期？
**舆论观点**: 至少4项？每项至少2句？体现四层梳理？
**深度分析**: 至少3段？每段至少3句？有独立观点？未复述概述？
```

---

#### Step 0.2: 优化 Agent C Prompt

**文件:** `app/core/prompts.py`

**AGENT_C_BATCH_TEMPLATE (line 221-288)**
- [ ] 添加 `{improvement_hint}` 插槽在末尾（用于重试时注入反馈）
- [ ] EDGE CASES 与 AUDIT PRINCIPLES 有重叠描述，精简

**代码示例:**
```python
# 在 SELF-CHECK 后添加
### IMPROVEMENT FEEDBACK
{improvement_hint}
```

---

#### Step 0.3: 优化 Agent D Prompt

**文件:** `app/core/prompts.py`

**AGENT_D_FORECAST_TEMPLATE (line 339-442)**
- [ ] `{improvement_hint}` 已存在 (line 428)，保持
- [ ] CORE RULES 的 Rule 1-5 与 SELF-CHECK 高度重叠，移除 SELF-CHECK 中的重复项
- [ ] `_WRITING_STYLE_GUIDE` 全局引用了 2 次（Agent B Reduce 和 Agent D），考虑保留

**精简示例:**
```python
# 修改前 SELF-CHECK (冗余)
- [ ] 是否引用了【历史同期规律】或【未来情报前瞻】？  # 与 Rule 1 重复
- [ ] 每个 topic 是否包含触发场景/演化路径/落地建议，且不少于 200 字？  # 与 Rule 4 重复
- [ ] 是否禁止使用模糊词（可能/或将）并给出具体时间点？  # 与 Rule 3 重复

# 修改后 SELF-CHECK (精简)
- [ ] 每个 topic 的 evidence_basis 是否引用了历史/未来数据（而非仅当前情绪）？
- [ ] 议题之间是否正交（互斥），无重复角度？
```

---

#### Step 0.4: 优化 Agent E Prompt

**文件:** `app/core/prompts.py`

**AGENT_E_PREFACE_TEMPLATE (line 444-586)**
- [ ] 添加 `{improvement_hint}` 插槽在末尾
- [ ] 添加 `{stats}` 插槽用于数据锚定（Phase 3 Agent E 校验时使用）
- [ ] QUALITY CHECKLIST 与 SELF-VERIFICATION 内容重复，合并

**代码示例:**
```python
# 添加数据锚定插槽
### DATA ANCHOR (硬性数据约束)
{stats}

# 添加反馈插槽
### IMPROVEMENT FEEDBACK
{improvement_hint}
```

---

#### Step 0.5: 统一 `_WRITING_STYLE_GUIDE` 引用

**文件:** `app/core/prompts.py`

当前 `_WRITING_STYLE_GUIDE` 被引用于：
- `AGENT_B_REDUCE_TEMPLATE`
- `AGENT_D_FORECAST_TEMPLATE`
- `AGENT_E_PREFACE_TEMPLATE`

**检查点:**
- [ ] 确认三处引用一致
- [ ] 确认没有其他地方重复定义写作风格

---

### Phase 1: 增强 quality_gate (低风险)

**目标:** 改进评估逻辑，任意维度 < 8 分即触发重试，反馈直接注入原 Prompt

**文件:** `app/agents/quality_gate.py`

**Step 1.1: 修改 MAX_RETRIES**
```python
# 修改前
MAX_RETRIES = 1

# 修改后
MAX_RETRIES = 2
```

**Step 1.2: 修改通过判定逻辑**
```python
# 修改前 (quality_gate.py 中的 _EvalResult)
class _EvalResult(BaseModel):
    ...
    passed: bool = Field(description="是否通过(overall>=7)")

# 修改后
class _EvalResult(BaseModel):
    ...
    passed: bool = Field(description="是否通过(completeness>=8 AND accuracy>=8 AND depth>=8)")
```

```python
# 修改 evaluate 函数中的判定逻辑
def evaluate(agent_name: str, content_summary: str) -> QualityScore:
    ...
    # 修改后的通过判定：任意维度 < 8 即不通过
    is_passed = (
        result.completeness >= 8 and 
        result.accuracy >= 8 and 
        result.depth >= 8
    )
    return QualityScore(
        ...,
        passed=is_passed,
        ...
    )
```

**Step 1.3: 细化评估标准 `_CRITERIA`（含反馈模板）**
```python
_CRITERIA = {
    "agent_b_analyze": """评估舆情分析(Agent B)，每项必须 >= 8 分才通过：
- 完整性(0-10): 是否分析了5个不同事件？每个事件有 event_overview, public_opinions, depth_analysis？
- 准确性(0-10): 观点是否基于实际评论？representative_comments 是否真实存在？有无捏造？
- 深度(0-10): 是否区分了「主流声浪/次生质疑/深层情绪/对立博弈」四层？

【反馈模板】若任一项 < 8，feedback 必须按以下格式输出：
「[维度名] 不足：[具体问题]。建议：[改进方向]」
示例：「深度不足：仅有主流声浪，缺少次生质疑和深层情绪分析。建议：补充对事件处置过程的延伸批判和隐藏群体心理。」""",

    "agent_c": """评估合规审查(Agent C)，每项必须 >= 8 分才通过：
- 完整性(0-10): 是否审查了所有提交内容？
- 准确性(0-10): 违规判定有明确 quote 原文？违规率>50% 是否过严（扩大化）？
- 深度(0-10): 每个违规项有 matched_laws 法规依据？

【反馈模板】若任一项 < 8，feedback 必须按以下格式输出：
「[维度名] 不足：[具体问题]。建议：[改进方向]」
示例：「准确性不足：帖子 note_123 的 quote 为空。建议：重新提取违规原文。」""",

    "agent_d": """评估趋势预测(Agent D)，每项必须 >= 8 分才通过：
- 完整性(0-10): 是否有3-5个预测主题？
- 准确性(0-10): 每个预测的 evidence_basis 是否引用了历史同期或未来情报（而非仅当前情绪）？
- 深度(0-10): 每个预测有「触发时间+具体事件+目标群体+应对建议」四要素？content >= 200字？

【反馈模板】若任一项 < 8，feedback 必须按以下格式输出：
「[维度名] 不足：[具体问题]。建议：[改进方向]」
示例：「准确性不足：主题2的 evidence_basis 仅引用当前情绪，未引用历史同期。建议：补充历年同月的舆情规律。」""",
}
```

---

### Phase 2: Agent D ReAct 化 (中风险)

**目标:** 让 Agent D 自主构造搜索词，但通过 Prompt 严格约束时间与领域格式

#### Step 1: 新建 Agent 工厂

**文件:** `app/agents/factory.py` (新建)

```python
from typing import List, Callable
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage

def create_react_agent(
    model: ChatOpenAI,
    tools: List[Callable],
    system_prompt: str,
) -> StateGraph:
    """
    创建 ReAct Agent (工具调用循环)
    参考 LangGraph 官方示例，不使用 create_react_agent prebuilt
    """
    from typing import Annotated, TypedDict
    from langgraph.graph.message import add_messages

    class AgentState(TypedDict):
        messages: Annotated[list, add_messages]

    # 绑定工具到模型
    model_with_tools = model.bind_tools(tools)

    def call_model(state: AgentState):
        messages = state["messages"]
        # 注入 system prompt
        if messages and not any(m.type == "system" for m in messages):
            from langchain_core.messages import SystemMessage
            messages = [SystemMessage(content=system_prompt)] + messages
        response = model_with_tools.invoke(messages)
        return {"messages": [response]}

    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    # 构建图
    graph = StateGraph(AgentState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", ToolNode(tools))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()
```

#### Step 2: 新建 Agent D ReAct Prompt

**文件:** `app/core/prompts.py` (追加)

```python
AGENT_D_REACT_SYSTEM_PROMPT = """
### ROLE
你是一名国家级智库的**首席战略预警专家**，擅长预测未来舆情风险。

### TOOLS
你可以使用 `tavily_search` 工具搜索网络信息。

### MANDATORY SEARCH PROTOCOL (必须严格遵守)

**Step 1: 历史同期搜索**
- 必须先搜索"历史同期规律"
- 查询词构造规则（**必须按此格式**）：
  - 格式: `历年{当前月}月{当前日}日~{目标月}月{目标日}日 中国{领域}领域 重点舆情 高发事件 复盘`
  - 示例: `历年2月8日~3月8日 中国高校领域 重点舆情 高发事件 复盘`
  - 若领域为"综合"，则省略领域限定词
- 若搜索结果为空，换关键词重试（如：去掉"高发"，改用"典型案例"）

**Step 2: 未来情报搜索**
- 必须再搜索"未来日程/政策"
- 查询词构造规则（**必须按此格式**）：
  - 格式: `{目标年}年{目标月}月 中国{领域}领域 重点新闻日历 大事预告 政策施行`
  - 示例: `2026年3月 中国高校领域 重点新闻日历 大事预告 政策施行`
  - 若领域为"综合"，则省略领域限定词
- 若搜索结果为空，换关键词重试（如：改用"会议安排"、"考试日程"、"法规生效"）

**Step 3: 风险推演**
- 基于搜索结果，使用公式推演：
  **[未来必然发生的节点] + [当前压抑的社会情绪] = [新的爆发点]**
- 输出 3-5 个风险预测主题
- 每个主题必须包含：触发时间、具体事件、目标群体、应对建议

### TIME CONSTRAINT
- 目标时间段: {target_period}
- 领域: {category}
- 当前日期: {current_date}

### OUTPUT FORMAT
最终输出必须是 JSON，符合 TrendForecastReport Schema：
```json
{{
  "target_period": "...",
  "topics": [
    {{
      "title": "（一）...",
      "content": "...(至少200字，包含触发场景/演化路径/应对建议)",
      "trigger_timing": "具体时间点",
      "risk_level": "High/Medium/Low",
      "evidence_basis": "基于历史同期规律：...；叠加未来情报：..."
    }}
  ]
}}
```
"""
```

#### Step 3: 改造 nodes.py 中的 agent_d_node

**文件:** `app/agents/nodes.py`

**修改要点:**
1. 删除 700-780 行的硬编码查询词构造逻辑
2. 改为调用 ReAct Agent
3. 保留时间计算逻辑用于生成 `target_period` 描述

```python
def agent_d_node(state: GraphState) -> Dict[str, Any]:
    """
    Agent D: 趋势预测 (ReAct Agent 模式)
    """
    from app.agents.factory import create_react_agent
    from app.services.utils import tavily_search  # Tool 版本
    from app.core.prompts import AGENT_D_REACT_SYSTEM_PROMPT
    from datetime import datetime
    from dateutil.relativedelta import relativedelta

    feedback = (state.get("supervisor_feedback") or "").strip()
    retry_count = (state.get("retry_count") or {}).get("agent_d", 0)
    is_retry = retry_count > 0

    logger.info(
        f"\n [Node D] 启动：趋势研判 (ReAct Mode)"
        f"{f' [第{retry_count}次重试, 反馈: {feedback}]' if is_retry else ''}..."
    )

    category = state.get("category") or "综合"
    forecast_range = state.get("forecast_range") or "1m"
    
    # 计算目标时间段描述
    now = datetime.now()
    range_map = {
        "1w": ("未来一周", 7, "days"),
        "2w": ("未来两周", 14, "days"),
        "1m": ("未来一个月", 1, "months"),
        "2m": ("未来两个月", 2, "months"),
    }
    range_desc, delta_val, delta_unit = range_map.get(forecast_range, ("未来一个月", 1, "months"))
    
    if delta_unit == "days":
        target_date = now + timedelta(days=delta_val)
    else:
        target_date = now + relativedelta(months=delta_val)
    
    target_period = f"{now.strftime('%Y年%m月%d日')}至{target_date.strftime('%Y年%m月%d日')}（{range_desc}）"

    # 准备当前舆情摘要
    analyzed_events = state.get("analyzed_events", [])
    audit_results = state.get("audit_results", [])
    
    b_texts = []
    for evt in analyzed_events:
        r = evt.get("opinion_report", {})
        if isinstance(r, dict):
            b_texts.append(f"【事件】{evt.get('event_name')}\n【概况】{r.get('event_overview')}")
    opinion_str = "\n---\n".join(b_texts) if b_texts else "无数据"

    c_texts = []
    for r in audit_results:
        v = r.get("violation_info", {})
        c_texts.append(f"事件<{r.get('event_name','未知')}>: 风险[{v.get('overall_risk_level')}]")
    audit_str = "\n".join(c_texts) if c_texts else "无高风险"

    # 创建 ReAct Agent
    from langchain_openai import ChatOpenAI
    from app.core.config import settings
    
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        openai_api_key=settings.ZHIPU_API_KEY,
        openai_api_base=settings.LLM_BASE_URL,
        temperature=0.6,
        request_timeout=180,
        max_retries=3,
    )

    system_prompt = AGENT_D_REACT_SYSTEM_PROMPT.format(
        target_period=target_period,
        category=category,
        current_date=now.strftime("%Y年%m月%d日"),
    )

    agent = create_react_agent(
        model=llm,
        tools=[tavily_search],
        system_prompt=system_prompt,
    )

    # 执行 Agent
    from langchain_core.messages import HumanMessage
    
    user_message = f"""
请为【{category}领域】的【{target_period}】进行舆情风险预测。

当前舆论情绪摘要：
{opinion_str}

已核实违规风险：
{audit_str}

{'改进建议：' + feedback if is_retry else ''}
"""

    result = agent.invoke({"messages": [HumanMessage(content=user_message)]})
    
    # 从最后一条消息提取 JSON
    last_message = result["messages"][-1]
    forecast = _extract_json_from_message(last_message.content)
    
    # 确保 target_period 有值
    if not forecast.get("target_period"):
        forecast["target_period"] = target_period

    return {"trend_forecast": forecast, "current_step": "D_Done"}


def _extract_json_from_message(content: str) -> dict:
    """从 Agent 输出中提取 JSON"""
    import re
    import json
    
    # 尝试匹配 JSON 块
    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except:
            pass
    
    # 尝试直接解析
    try:
        return json.loads(content)
    except:
        pass
    
    # 兜底返回空结构
    return {"target_period": "", "topics": []}
```

#### Step 4: 封装 Tavily Search Tool

**文件:** `app/services/utils.py` (追加)

```python
from langchain_core.tools import tool

@tool
def tavily_search(query: str) -> str:
    """
    搜索网络信息。用于查询历史同期舆情规律或未来政策日历。
    
    Args:
        query: 搜索查询词，必须包含具体时间和领域
    
    Returns:
        搜索结果摘要文本
    """
    return get_web_context(query, max_results=5, search_depth="advanced")
```

---

### Phase 3: Agent E 数字校验 (低风险)

**目标:** 用代码级校验替代 LLM Review，确保前言中的数字准确

**文件:** `app/services/report.py`

**Step 1: 新增统计计算函数**
```python
def _compute_stats(self, core_events, audit_results, analyzed_events) -> dict:
    """计算报告统计数据，作为 Source of Truth"""
    violation_list = [r for r in audit_results if r.get("is_violation")]
    high_risk_list = [r for r in audit_results 
        if (r.get("violation_info") or {}).get("overall_risk_level") == "High"]
    
    return {
        "total_events": len(core_events),
        "analyzed_count": len(analyzed_events),
        "violation_count": len(violation_list),
        "high_risk_count": len(high_risk_list),
    }
```

**Step 2: 修改 Prompt 注入统计数据**

在 `_generate_preface` 方法中：
```python
# 计算统计数据
stats = self._compute_stats(core_events, audit_results, analyzed_events)
stats_str = f"""
### DATA ANCHOR (报告必须使用的准确数据)
- 热点事件总数: {stats['total_events']}
- 深度分析事件数: {stats['analyzed_count']}
- 违规内容数: {stats['violation_count']}
- 高风险数: {stats['high_risk_count']}

**重要约束**: 文中出现的数据必须与上述数据完全一致，严禁杜撰其他数字。
"""

# 注入 Prompt
prompt_text = AGENT_E_PREFACE_TEMPLATE.format(
    ...,
    stats=stats_str,
)
```

**Step 3: 新增代码级校验**
```python
def _validate_preface_numbers(self, preface_text: str, stats: dict) -> tuple[bool, str]:
    """
    校验前言中的数字是否与统计数据一致
    返回: (是否通过, 错误信息)
    """
    import re
    
    # 提取前言中的所有数字
    numbers_in_text = [int(n) for n in re.findall(r'\d+', preface_text)]
    expected_numbers = set(stats.values())
    
    errors = []
    for num in numbers_in_text:
        # 如果前言中出现了不在预期范围内的大数字（>100），可能是幻觉
        if num > 100 and num not in expected_numbers:
            errors.append(f"检测到可疑数字: {num}")
    
    if errors:
        return False, "; ".join(errors)
    return True, ""
```

---

## 4. 编排层 (workflow.py)

**保持不变**，确保：
1. quality_gate 使用新的 `MAX_RETRIES=2`
2. Agent D 调用改造后的 `agent_d_node`

---

## 5. 执行顺序与检查点

| Phase | Step | 任务 | 涉及文件 | 预计时间 |
|-------|------|------|----------|----------|
| 0 | 0.1 | 检查 Agent B Prompt | core/prompts.py | 10min |
| 0 | 0.2 | 检查 Agent C Prompt | core/prompts.py | 10min |
| 0 | 0.3 | 检查 Agent D Prompt | core/prompts.py | 10min |
| 0 | 0.4 | 检查 Agent E Prompt，增加 {stats} 插槽 | core/prompts.py | 15min |
| 1 | 1.1 | 修改 MAX_RETRIES | quality_gate.py | 5min |
| 1 | 1.2 | 修改通过判定逻辑（任意 < 8 即重试） | quality_gate.py | 15min |
| 1 | 1.3 | 细化 _CRITERIA（含反馈模板） | quality_gate.py | 20min |
| 2 | 2.1 | 新建 factory.py | agents/factory.py | 20min |
| 2 | 2.2 | 新建 Agent D ReAct Prompt | core/prompts.py | 15min |
| 2 | 2.3 | 改造 agent_d_node | agents/nodes.py | 30min |
| 2 | 2.4 | 封装 tavily_search tool | services/utils.py | 10min |
| 3 | 3.1 | 增加 _compute_stats | services/report.py | 10min |
| 3 | 3.2 | 修改 Prompt 注入统计 | services/report.py | 10min |
| 3 | 3.3 | 增加 _validate_preface | services/report.py | 15min |

---

## 6. 测试验证

每个 Phase 完成后执行:
```bash
cd Backend
python -m pytest tests/ -v
python main.py --category 高校 --range 1w --dry-run
```

---

## 7. 回滚计划

如果 Agent D ReAct 化后搜索质量下降:
1. 在 Prompt 中增加更详细的查询词示例
2. 增加查询词格式的 few-shot examples
3. 最坏情况：回退到原有硬编码模式（保留在 git 历史中）

---

## 8. 致执行者的提示

1. **不要一次性生成所有文件**。请按 Phase 0 → 1 → 2 → 3 的顺序逐步实施。
2. **保留业务逻辑**：`app/services/` 下的业务代码应复用，不要重写核心算法。
3. **路由兜底**：确保 quality_gate 的 MAX_RETRIES 逻辑正确，重试耗尽则放行。
4. **测试驱动**：每完成一个 Step，运行测试验证。
5. **反馈注入**：重试时，将 quality_gate 的 feedback 注入到原 Prompt 的 `{improvement_hint}` 插槽，**不需要完整重新生成**，只需在原输出基础上修正。

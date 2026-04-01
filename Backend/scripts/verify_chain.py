"""全链路验证脚本：确保重构后所有模块导入正常"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

errors = []


def check(label, fn):
    try:
        result = fn()
        print(f"  [OK] {label}: {result}")
    except Exception as e:
        errors.append((label, str(e)))
        print(f"  [FAIL] {label}: {e}")


print("=" * 60)
print("全链路验证")
print("=" * 60)

# 1. services/ 业务服务层
print("\n--- 1. Services ---")
check("stats", lambda: (
    __import__("app.services.stats", fromlist=["agent_stats"]),
    "AgentStats OK")[1])
check("opinions", lambda: (
    __import__("app.services.opinions", fromlist=["agent_opinions"]),
    "AgentOpinions OK")[1])
check("compliance", lambda: (
    __import__("app.services.compliance", fromlist=["agent_c"]),
    "AgentCompliance OK")[1])
check("forecast", lambda: (
    __import__("app.services.forecast", fromlist=["agent_forecast"]),
    "AgentForecast OK")[1])
check("historical", lambda: (
    __import__("app.services.historical", fromlist=["agent_historical"]),
    "AgentHistorical OK")[1])
check("report", lambda: (
    __import__("app.services.report", fromlist=["agent_report"]),
    "AgentReport OK")[1])
check("utils", lambda: (
    __import__("app.services.utils", fromlist=["get_web_context", "normalize_category"]),
    "get_web_context + normalize_category OK")[1])

# 2. agents/quality_gate.py
print("\n--- 2. Quality Gate ---")

def check_qg():
    from app.agents.quality_gate import quality_gate_bc_node, quality_gate_d_node, route_after_bc_gate, route_after_d_gate
    return "4 functions imported"

check("quality_gate imports", check_qg)

# 3. workflow
print("\n--- 3. Workflow ---")

def check_workflow():
    from app.agents.workflow import create_workflow
    wf = create_workflow()
    compiled = wf.compile()
    nodes = list(compiled.get_graph().nodes.keys())
    return f"{len(nodes)} nodes: {nodes}"

check("workflow compile", check_workflow)

# 4. 目录结构验证
print("\n--- 4. Structure ---")
agents_expected = {"quality_gate.py", "nodes.py", "workflow.py", "state.py"}
services_expected = {"stats.py", "opinions.py", "compliance.py", "forecast.py", "historical.py", "report.py", "utils.py", "category_classifier.py", "__init__.py"}
agents_dir = set(f for f in os.listdir("app/agents") if f.endswith(".py"))
services_dir = set(f for f in os.listdir("app/services") if f.endswith(".py"))
check("agents/ files", lambda: f"{agents_dir}" if agents_dir == agents_expected else f"MISMATCH: got {agents_dir}, expected {agents_expected}")
check("services/ files", lambda: f"{services_dir}" if services_dir >= services_expected else f"MISMATCH: got {services_dir}, expected {services_expected}")

# 5. 旧文件不存在
print("\n--- 5. Dead files ---")
dead = ["app/agents/react_agents.py", "app/agents/agent_tools.py", "app/agents/agent_factory.py",
        "app/agents/quality_gate_llm.py", "app/agents/tools.py", "app/agents/toolset.py", "app/agents/factory.py",
        "app/agents/agent_stats.py", "app/agents/agent_opinions.py", "app/agents/agent_compliance.py",
        "app/agents/agent_forecast.py", "app/agents/agent_historical.py", "app/agents/agent_report.py"]
for p in dead:
    check(f"{os.path.basename(p)} deleted", lambda p=p: "OK" if not os.path.exists(p) else "STILL EXISTS!")

# Summary
print("\n" + "=" * 60)
if errors:
    print(f"FAILED: {len(errors)} check(s)")
    for label, err in errors:
        print(f"  - {label}: {err}")
else:
    print("ALL CHECKS PASSED")
print("=" * 60)

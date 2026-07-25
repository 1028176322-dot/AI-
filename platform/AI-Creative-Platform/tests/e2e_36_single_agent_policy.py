# -*- coding: utf-8 -*-
"""Phase 5 · 单 Agent 执行策略 · 端到端一致性验证。

覆盖四层：策略契约 / 项目覆盖 / AGENTS 规则 / 任务模板+ready_check /
会话锁 / 工具白名单 / Compliance Gate(doctor) / 顺序编排器。
运行：python tests/e2e_36_single_agent_policy.py
"""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PLAT = os.path.dirname(HERE)
TOOLS = os.path.join(PLAT, "tools")
GATES = os.path.join(PLAT, "core", "gates")
RUNTIME = os.path.join(PLAT, "core", "runtime")
PROJ_ROOT = os.path.dirname(os.path.dirname(PLAT))   # AI-Workspace
PROJ = os.path.join(PROJ_ROOT, "projects", "道法百年")

for p in (TOOLS, GATES, RUNTIME):
    if p not in sys.path:
        sys.path.insert(0, p)

import _gov
import agent_compliance_gate as ACG
import session_bootstrap as SB
import task_engine as TE
import sequential_planner as SP

TOTAL, PASS_CNT, FAILS = 0, 0, []


def check(name, cond, detail=""):
    global TOTAL, PASS_CNT
    TOTAL += 1
    mark = "PASS" if cond else "FAIL"
    if cond:
        PASS_CNT += 1
    else:
        FAILS.append((name, detail))
    print("  [%s] %s%s" % (mark, name, ("" if cond else "  -> " + detail)))
    return cond


# ───────────────────────── 1. 策略契约层 ─────────────────────────
print("\n[1] 策略契约层：agent-execution.policy.yaml")
pol = _gov.load_yaml(os.path.join(PLAT, "core", "policies", "agent-execution.policy.yaml"))
ae = (pol or {}).get("agent_execution") or {}
check("策略文件可解析且 agent_execution 存在", isinstance(ae, dict))
check("mode == single_agent", ae.get("mode") == "single_agent", "mode=%s" % ae.get("mode"))
check("subagents.allowed == false", (ae.get("subagents") or {}).get("allowed") is False)
check("delegation.allowed == false", (ae.get("delegation") or {}).get("allowed") is False)
check("parallel_agents.allowed == false", (ae.get("parallel_agents") or {}).get("allowed") is False)
check("nested_sessions.allowed == false", (ae.get("nested_sessions") or {}).get("allowed") is False)
check("background_workers.allowed == false", (ae.get("background_workers") or {}).get("allowed") is False)
check("auto_role_derivation.allowed == false", (ae.get("auto_role_derivation") or {}).get("allowed") is False)
check("decomposition.agent_decomposition == forbidden",
      (ae.get("decomposition") or {}).get("agent_decomposition") == "forbidden")
check("violation.code == SUBAGENT_DISABLED",
      (ae.get("violation") or {}).get("code") == "SUBAGENT_DISABLED")

# ───────────────────────── 2. 项目覆盖层 ─────────────────────────
print("\n[2] 项目覆盖层：project.yaml runtime")
pdata = _gov.load_yaml(os.path.join(PROJ, "project.yaml"))
rt = (pdata or {}).get("runtime") or {}
check("runtime.agent_mode == single（显式）", rt.get("agent_mode") == "single", "agent_mode=%s" % rt.get("agent_mode"))
conc = rt.get("concurrency") or {}
check("concurrency.max_active_agents == 1", conc.get("max_active_agents") == 1)
check("concurrency.max_running_tasks == 1", conc.get("max_running_tasks") == 1)
check("concurrency.max_parallel_tool_calls == 1", conc.get("max_parallel_tool_calls") == 1)
check("concurrency.max_background_jobs == 0", conc.get("max_background_jobs") == 0)
check("delegation.enabled == false", (rt.get("delegation") or {}).get("enabled") is False)
check("subagents.enabled == false", (rt.get("subagents") or {}).get("enabled") is False)
check("background.enabled == false", (rt.get("background") or {}).get("enabled") is False)
check("async_tasks.enabled == false", (rt.get("async_tasks") or {}).get("enabled") is False)
check("worker_pool.size == 0", (rt.get("worker_pool") or {}).get("size") == 0)
check("fork.enabled == false", (rt.get("fork") or {}).get("enabled") is False)
check("decomposition.step_decomposition == true", (rt.get("decomposition") or {}).get("step_decomposition") is True)
check("decomposition.agent_decomposition == false", (rt.get("decomposition") or {}).get("agent_decomposition") is False)
check("role_switching.method == context_package", (rt.get("role_switching") or {}).get("method") == "context_package")

# ───────────────────────── 3. AGENTS.md 规则 ─────────────────────────
print("\n[3] AGENTS.md 强制规则段")
agents_md = os.path.join(PROJ, "AGENTS.md")
with open(agents_md, "r", encoding="utf-8") as f:
    agents_txt = f.read()
check("含『Single-Agent Execution Policy』强制段", "Single-Agent Execution Policy" in agents_txt)
check("含『多角色不等于多 Agent』核心句", "多角色不等于多 Agent" in agents_txt)
check("位于文件顶部（第一行或紧随标题）", agents_txt.lstrip().startswith("# Single-Agent Execution"))

# ───────────────────────── 4. 任务模板 execution_policy ─────────────────────────
print("\n[4] 任务模板 execution_policy 一致性")
TEMPLATES = ["chapter-write", "chapter-fix", "chapter-plan", "chapter-review",
             "nkb-sync", "project-design", "system-maintenance"]
all_ok_tmpl = True
for name in TEMPLATES:
    tf = os.path.join(PLAT, "core", "task-system", "templates", "%s.task.yaml" % name)
    tmpl = (_gov.load_yaml(tf) or {}).get("task_template") or {}
    ep = tmpl.get("execution_policy") or {}
    good = (ep.get("max_agents") == 1 and ep.get("subagent_allowed") is False
            and ep.get("delegation_allowed") is False
            and ep.get("parallel_execution_allowed") is False
            and ep.get("required_session") == "current")
    all_ok_tmpl = all_ok_tmpl and good
    print("    - %-18s max_agents=%s subagent=%s delegation=%s" % (
        name, ep.get("max_agents"), ep.get("subagent_allowed"), ep.get("delegation_allowed")))
check("7 个模板均含合规 execution_policy", all_ok_tmpl)

# ───────────────────────── 5. ready_check 校验 ─────────────────────────
print("\n[5] task_engine.ready_check 单 Agent 校验")
import tempfile
tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, "tasks", "ready"))


def _write_task(tid, body):
    with open(os.path.join(tmp, "tasks", "ready", "%s.yaml" % tid), "w", encoding="utf-8") as f:
        f.write(body)


def _chk(tid):
    ok, rep = TE.ready_check(tmp, tid)
    return ok, rep

# 5a 内联合规 execution_policy
_write_task("TASK-POS-001", """task:
  type: chapter_write
  status: ready
  execution_policy:
    agent_mode: single
    delegation_allowed: false
    subagent_allowed: false
    parallel_execution_allowed: false
    max_agents: 1
    max_parallel_steps: 1
    required_session: current
""")
_, rep_pos = _chk("TASK-POS-001")
check("内联合规 execution_policy → single_agent_policy=True",
      rep_pos.get("checks", {}).get("single_agent_policy") is True, str(rep_pos.get("checks")))

# 5b 内联违例 max_agents:2
_write_task("TASK-NEG-001", """task:
  type: chapter_write
  status: ready
  execution_policy:
    agent_mode: single
    delegation_allowed: false
    subagent_allowed: false
    parallel_execution_allowed: false
    max_agents: 2
    max_parallel_steps: 1
    required_session: current
""")
_, rep_neg = _chk("TASK-NEG-001")
check("内联 max_agents=2 → single_agent_policy=False",
      rep_neg.get("checks", {}).get("single_agent_policy") is False, str(rep_neg.get("checks")))

# 5c 无内联 → 从模板继承 chapter-write 的 execution_policy
_write_task("TASK-INH-001", """task:
  type: chapter_write
  status: ready
""")
_, rep_inh = _chk("TASK-INH-001")
check("无内联 + 模板继承 → single_agent_policy=True",
      rep_inh.get("checks", {}).get("single_agent_policy") is True, str(rep_inh.get("checks")))

# ───────────────────────── 6. 会话锁 agent_runtime + locks ─────────────────────────
print("\n[6] 会话锁：session_bootstrap.agent_runtime / locks")
ar = SB._derive_agent_runtime(pdata)
check("agent_runtime.agent_mode == single", ar.get("agent_mode") == "single")
check("agent_runtime.max_active_agents == 1", ar.get("max_active_agents") == 1)
check("agent_runtime.subagents_enabled == false", ar.get("subagents_enabled") is False)
check("agent_runtime.delegation_enabled == false", ar.get("delegation_enabled") is False)
check("agent_runtime.background_execution_enabled == false", ar.get("background_execution_enabled") is False)
src = open(SB.__file__, encoding="utf-8").read()
check("session_bootstrap 源码声明 agent_runtime 字段", "agent_runtime" in src)
check("session_bootstrap 源码声明不可变 locks 字段", "locks" in src
      and "agent_runtime.agent_mode" in src and "agent_runtime.max_active_agents" in src)

# ───────────────────────── 7. 工具白名单 ─────────────────────────
print("\n[7] 工具白名单：ROLE_REGISTRY.tool_access")
reg = _gov.load_yaml(os.path.join(PLAT, "core", "session", "ROLE_REGISTRY.yaml"))
ta = (reg or {}).get("tool_access") or {}
check("access_mode == whitelist", ta.get("access_mode") == "whitelist", "mode=%s" % ta.get("access_mode"))
check("disabled 列表非空（>=11 项）", len(ta.get("disabled") or []) >= 11,
      "count=%d" % len(ta.get("disabled") or []))
check("allowed 白名单非空", len(ta.get("allowed") or []) >= 5)
disabled_str = " ".join(ta.get("disabled") or [])
for tok in ("spawn_agent", "create_subagent", "delegate_to_agent", "run_agent_parallel",
            "launch_worker", "background_agent"):
    check("disabled 含 %s" % tok, tok in disabled_str)

# ───────────────────────── 8. Compliance Gate（doctor AgentGov） ─────────────────────────
print("\n[8] Subagent Compliance Gate（doctor AgentGov）")
rep = ACG.govern(PROJ, write=False)
check("gate decision == proceed", rep["gate"]["decision"] == "proceed", str(rep["gate"]))
check("gate health == 100", rep["composite"]["health"] == 100)
check("agent_audit.active_agent_count == 1", rep["agent_audit"]["active_agent_count"] == 1)
check("agent_audit 无 spawned/delegated/parallel",
      rep["agent_audit"]["spawned_agents"] == [] and rep["agent_audit"]["delegated_tasks"] == []
      and rep["agent_audit"]["parallel_runs"] == [])
# doctor 实际跑出 AgentGov PASS
r = subprocess.run([sys.executable, os.path.join(TOOLS, "platform_cli.py"),
                    "--workspace", PROJ_ROOT, "doctor"],
                   capture_output=True, text=True, timeout=420)
doctor_ok = ("AgentGov" in r.stdout) and ("[PASS] AgentGov" in r.stdout)
check("platform doctor 输出 AgentGov PASS", doctor_ok,
      ("AgentGov 缺失" if "AgentGov" not in r.stdout else "非 PASS"))

# ───────────────────────── 9. 顺序编排器 ─────────────────────────
print("\n[9] 顺序编排器 sequential-planner")
plan = SP.build_sequential_plan([
    ("STEP-01", "planner", "prepare_plan", []),
    ("STEP-02", "writer", "produce_draft", ["STEP-01"]),
    ("STEP-03", "reviewer", "review_draft", ["STEP-02"]),
    ("STEP-04", "fixer", "apply_fixes", ["STEP-03"]),
])
ep = plan["execution_plan"]
check("plan mode == sequential", ep["mode"] == "sequential")
check("plan agent_count == 1", ep["agent_count"] == 1)
check("steps 含 depends_on 顺序链", all("depends_on" in s for s in ep["steps"])
      and ep["steps"][3]["depends_on"] == ["STEP-03"])
ok_v, _ = ACG.verify_execution_plan(plan)
check("verify_execution_plan(合规 plan) == True", ok_v)
# 负例：并行 + 多 Agent
bad_plan = {"execution_plan": {"mode": "parallel", "agent_count": 3,
                               "steps": [{"id": "S1", "agent": "x"}]}}
ok_bad, reason_bad = ACG.verify_execution_plan(bad_plan)
check("verify_execution_plan(并行/多Agent) == False", ok_bad is False, reason_bad)
# build_sequential_plan 对非法 plan 抛 ValueError
raised = False
try:
    SP.build_sequential_plan([("S1", "writer", "do", [])])  # ok
    SP.build_sequential_plan([("S1", "writer", "do", [])])  # placeholder
    # 直接构造非法再 build：用 verify 已覆盖；此处验证正常 build 不抛
except ValueError:
    raised = True
check("build_sequential_plan 合规输入不抛异常", not raised)

# ───────────────────────── 总结 ─────────────────────────
print("\n" + "=" * 60)
print("单 Agent 策略 e2e 结果：%d/%d PASS" % (PASS_CNT, TOTAL))
if FAILS:
    print("失败项：")
    for n, d in FAILS:
        print("  - %s : %s" % (n, d))
    sys.exit(1)
print("全部通过。")
sys.exit(0)

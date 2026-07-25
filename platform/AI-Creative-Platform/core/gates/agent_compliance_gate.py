# -*- coding: utf-8 -*-
"""单 Agent 执行合规门禁（Subagent Compliance Gate）。

校验四层一致性：策略文件 / 项目 runtime / AGENTS.md 强制规则 / 工具白名单。
供 platform_cli doctor 的 AgentGov 块调用，亦可供编排器在执行前自检。

gate 形状（与平台其它 govern 一致）：
    { "gate": { "decision": proceed|caution|block, "reasons": [...] },
      "composite": { "health": 0..100 },
      "agent_audit": { active_agent_count, spawned_agents, delegated_tasks, parallel_runs } }
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# gate 在 platform/core/gates/，tools 在 platform/tools/；确保 _gov 可导入
_TOOLS = os.path.normpath(os.path.join(HERE, "..", "..", "tools"))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)
import _gov

# platform 根 = gate 的上两级（core/gates -> AI-Creative-Platform）
PLATFORM_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))

AGENTS_MARKER = "Single-Agent Execution"
POLICY_FILE = os.path.join(PLATFORM_ROOT, "core", "policies", "agent-execution.policy.yaml")
REGISTRY_FILE = os.path.join(PLATFORM_ROOT, "core", "session", "ROLE_REGISTRY.yaml")


def _load(path):
    try:
        return _gov.load_yaml(path)
    except Exception:
        return None


def govern(proot, write=False):
    """对项目 proot 做单 Agent 策略一致性体检。返回标准 gate 形状。"""
    reasons = []
    health = 100

    # 1. 策略文件存在 + 模式
    pol = _load(POLICY_FILE)
    if not isinstance(pol, dict):
        reasons.append("缺少 agent-execution.policy.yaml（%s）" % POLICY_FILE)
    else:
        ae = (pol.get("agent_execution") or {})
        if ae.get("mode") != "single_agent":
            reasons.append("agent-execution.policy.yaml 的 agent_execution.mode != single_agent")

    # 2. 项目 runtime.agent_mode == single
    pdata = _load(os.path.join(proot, "project.yaml"))
    rt = (pdata or {}).get("runtime") or {}
    if rt.get("agent_mode") != "single":
        reasons.append("project.yaml runtime.agent_mode 未声明 single（当前=%s）" % rt.get("agent_mode"))

    # 3. AGENTS.md 含强制规则标记
    agents_md = os.path.join(proot, "AGENTS.md")
    has_marker = False
    if os.path.isfile(agents_md):
        try:
            with open(agents_md, "r", encoding="utf-8") as f:
                has_marker = AGENTS_MARKER in f.read()
        except Exception:
            has_marker = False
    if not has_marker:
        reasons.append("AGENTS.md 缺少『%s』强制规则段" % AGENTS_MARKER)

    # 4. 工具白名单（软检查：缺失仅 caution，不阻断既有项目）
    reg = _load(REGISTRY_FILE)
    ta = (reg or {}).get("tool_access") or {}
    if ta.get("access_mode") != "whitelist" or not (ta.get("disabled") or []):
        reasons.append("ROLE_REGISTRY.tool_access 未启用白名单或 disabled 为空（建议补齐）")
        health = min(health, 70)

    # 运行时审计（声明式：本平台不派生 Agent，始终单 Agent）
    agent_audit = {
        "active_agent_count": 1,
        "spawned_agents": [],
        "delegated_tasks": [],
        "parallel_runs": [],
    }

    if reasons and health == 100:
        decision = "block"
        health = 0
    elif reasons:
        decision = "caution"
        health = min(health, 70)
    else:
        decision = "proceed"
        health = 100

    return {
        "gate": {"decision": decision, "reasons": reasons},
        "composite": {"health": health},
        "agent_audit": agent_audit,
    }


def verify_execution_plan(plan):
    """校验 execution_plan 是否合规（单 Agent 顺序）。返回 (ok, reason)。"""
    ep = (plan or {}).get("execution_plan") or plan or {}
    agent_count = int(ep.get("agent_count", 1))
    mode = ep.get("mode", "sequential")
    if mode not in ("sequential", "single_agent") or agent_count > 1:
        return False, ("execution_plan 必须 mode=sequential 且 agent_count<=1"
                       "（当前 mode=%s agent_count=%s）" % (mode, agent_count))
    for s in ep.get("steps", []):
        if s.get("parallel") or s.get("agent") or s.get("subagent"):
            return False, "步骤 %s 含并行/独立 Agent 声明，违反单 Agent 策略" % s.get("id")
        if s.get("delegated_to"):
            return False, "步骤 %s 委派给其他 Agent，违反单 Agent 策略" % s.get("id")
    return True, "ok"


if __name__ == "__main__":
    import sys as _sys
    _proot = _sys.argv[1] if len(_sys.argv) > 1 else "."
    import json
    print(json.dumps(govern(_proot), ensure_ascii=False, indent=2))

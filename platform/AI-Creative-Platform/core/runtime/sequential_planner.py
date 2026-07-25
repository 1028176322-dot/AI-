# -*- coding: utf-8 -*-
"""顺序编排器（Sequential Planner）：把复杂任务表达为单 Agent 顺序步骤。

角色（role）只是当前主 Agent 的工作模式，不代表新 Agent 实例。
提供：build_sequential_plan / role_transition，并复用 agent-compliance-gate
的 verify_execution_plan 做一致性校验。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_GATES = os.path.normpath(os.path.join(HERE, "..", "gates"))
if _GATES not in sys.path:
    sys.path.insert(0, _GATES)
import agent_compliance_gate as _acg


def build_sequential_plan(roles_actions):
    """roles_actions: [(step_id, role, action, depends_on)] -> execution_plan dict。

    role 仅表示当前主 Agent 的阶段工作模式（planner/writer/reviewer/fixer...）。
    """
    steps = []
    for sid, role, action, deps in roles_actions:
        steps.append({
            "id": sid,
            "role": role,
            "action": action,
            "depends_on": deps or [],
        })
    plan = {
        "execution_plan": {
            "mode": "sequential",
            "agent_count": 1,
            "steps": steps,
        }
    }
    ok, reason = _acg.verify_execution_plan(plan)
    if not ok:
        raise ValueError("非法 execution_plan：%s" % reason)
    return plan


def role_transition(from_role, to_role, new_context_package):
    """记录阶段角色切换（同 Agent 内，通过新 Context Package 模拟职责隔离）。"""
    return {
        "role_transition": {
            "from": from_role,
            "to": to_role,
            "new_context_package": new_context_package,
            "previous_role_output_read_only": True,
        }
    }


if __name__ == "__main__":
    import json
    demo = build_sequential_plan([
        ("STEP-01", "planner", "prepare_plan", []),
        ("STEP-02", "writer", "produce_draft", ["STEP-01"]),
        ("STEP-03", "reviewer", "review_draft", ["STEP-02"]),
        ("STEP-04", "fixer", "apply_fixes", ["STEP-03"]),
    ])
    print(json.dumps(demo, ensure_ascii=False, indent=2))

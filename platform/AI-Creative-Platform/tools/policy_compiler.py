# -*- coding: utf-8 -*-
"""policy_compiler.py — 按任务编译最小规则包（Phase A4）

不要每次把整个平台规范塞给 AI。本模块从 AGENTS.md（单 Agent 策略段）
+ 任务契约 + 角色规则 编译出当前任务所需的最小规则集：

  platform policy compile --task <TID> --project-root <R>

产物：runtime/policies/<role>-<type>.compiled.yaml
  must:      [当前任务必须做的]
  must_not:  [当前任务禁止做的，含单 Agent 禁令 + 模板 forbidden 路径]
  source:    规则来源（可追溯）

单 Agent 禁令为平台硬约束，所有任务编译结果均包含。
"""
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _gov
import task_engine as TE

TEMPLATES_DIR = os.path.join(os.path.dirname(HERE), "core", "task-system", "templates")

# 单 Agent 执行策略硬禁令（来自 core/policies/agent-execution.policy.yaml + AGENTS.md）
_SINGLE_AGENT_MUST_NOT = [
    "创建或调用子 Agent",
    "委派任务给其他 Agent",
    "启动并行 Agent",
    "创建嵌套 Agent 会话",
    "使用后台 Agent / 后台工作单元执行任务",
    "以并行方式执行多个任务",
]

# 任务系统硬禁令（来自 AGENTS.md 规则 12）
_TASK_SYSTEM_MUST_NOT = [
    "绕过任务系统用通用 Write/Edit 直接改项目内容产物",
    "AI 自行标记任务 COMPLETED（执行者不可验收自己任务）",
]


def _load_template(name):
    p = os.path.join(TEMPLATES_DIR, name + ".task.yaml")
    if not os.path.isfile(p):
        return {}
    d = _gov.load_yaml(p) or {}
    return d.get("task_template") or d.get("template") or {}


def _must_for(role, ttype, outputs):
    must = ["在单 Agent 顺序模式下执行本任务（多角色≠多 Agent）",
            "仅通过受控写工具写 permissions.write 内路径",
            "产出须满足 output-contract 的 allowed_outputs"]
    if role == "writer" or ttype == "chapter_write" or ttype == "chapter_fix":
        must += ["保留人物核心与已批准设定", "不破坏已建立的时间线/因果",
                 "输出候选事实（candidate_events）供 NKB 回填"]
    if role == "reviewer" or ttype == "chapter_review":
        must += ["先脚本预检事实，再 AI 深度审查（因果/人物/连续性/节奏）",
                 "输出带证据(evidence)+推理(reasoning)的问题清单"]
    if role == "knowledge-manager" or ttype == "nkb_update":
        must += ["仅持 approved_event 时更新 NKB", "每次变更附 Operation Manifest"]
    if "candidate_facts" in outputs or "candidate_events" in outputs:
        must.append("候选事实须标注 src 与 confidence")
    return must


def compile_policy(root, tid):
    st, data = TE.load_task(root, tid)
    if st is None:
        raise RuntimeError("任务不存在: %s" % tid)
    task = data.get("task", data)
    ttype = task.get("type", "unknown")
    role = (task.get("agent") or {}).get("required_role", "unknown")
    tmpl = _load_template(ttype)
    outputs = tmpl.get("allowed_outputs") or task.get("expected_outputs") or []
    forbidden = tmpl.get("permissions", {}).get("forbidden") or []

    must_not = list(_SINGLE_AGENT_MUST_NOT)
    must_not += _TASK_SYSTEM_MUST_NOT
    for f in forbidden:
        must_not.append("写 forbidden 路径：%s" % f)
    if role != "knowledge-manager":
        must_not.append("修改 NKB（仅 knowledge-manager 且持 approved_event 可）")
    must_not.append("修改 outline / 已批准章节")

    must = _must_for(role, ttype, outputs)

    policy = {
        "task_id": tid,
        "role": role,
        "task_type": ttype,
        "mode": "single_agent_sequential",
        "must": must,
        "must_not": must_not,
        "source": [
            "AGENTS.md#Single-Agent Execution Policy",
            "core/policies/agent-execution.policy.yaml",
            "core/task-system/templates/%s.task.yaml" % ttype,
        ],
    }
    out_dir = os.path.join(root, "runtime", "policies")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "%s-%s.compiled.yaml" % (role, ttype))
    _gov.dump_yaml(out_path, policy)
    return out_path, policy


def main():
    ap = argparse.ArgumentParser(prog="policy", description="编译最小规则包")
    ap.add_argument("action", nargs="?", default="compile", choices=["compile"])
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--task", required=True)
    args = ap.parse_args()
    try:
        p, pol = compile_policy(args.project_root, args.task)
        print("✓ Policy 已编译：%s" % p)
        print("  must: %d 条 | must_not: %d 条" % (len(pol["must"]), len(pol["must_not"])))
    except RuntimeError as e:
        print("ERROR: %s" % e)
        sys.exit(2)


if __name__ == "__main__":
    main()

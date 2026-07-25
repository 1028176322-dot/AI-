# -*- coding: utf-8 -*-
"""task_packet.py — 为单个任务生成 Task Packet（Phase A2）

AI 每次执行任务只读这一个包，而不是扫描整个项目：

  runtime/task-packets/<TASK>/
    task.yaml            任务本体（来自 task_engine.load_task）
    input-index.yaml     必需输入 → 解析路径（resolved / pending）
    context.md           最小上下文（优先引用 context build 产物）
    constraints.md       权限边界 + 单 Agent 执行约束
    output-contract.yaml 允许产出 + 验收标准 + 后继任务
    execution-manifest.yaml 执行元数据（角色/模式/预算/生成时间）

用法：platform task packet --task <TID> --project-root <R>
"""
import os
import sys
import json
import datetime
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _gov
import task_engine as TE

TEMPLATES_DIR = os.path.join(os.path.dirname(HERE), "core", "task-system", "templates")


def _load_template(name):
    p = os.path.join(TEMPLATES_DIR, name + ".task.yaml")
    if not os.path.isfile(p):
        return {}
    d = _gov.load_yaml(p) or {}
    return d.get("task_template") or d.get("template") or {}


def _resolve_input(root, name, task):
    """把概念性必需输入映射到项目内路径（最佳努力）。"""
    chapter_ref = task.get("chapter_ref")
    if name == "nkb_snapshot":
        p = os.path.join(root, "NKB")
        return (p, os.path.isdir(p))
    if name == "final_context":
        p = os.path.join(root, "runtime", "context")
        return (p, os.path.isdir(p))
    if name == "previous_chapter_handoff":
        p = os.path.join(root, "handoffs")
        return (p, os.path.isdir(p))
    if name == "chapter_plan":
        if chapter_ref:
            base = os.path.splitext(chapter_ref)[0]
            for cand in (base + "_plan.md", base + ".plan.md",
                         os.path.join("sources", "outline", os.path.basename(base) + ".md")):
                fp = os.path.join(root, cand)
                if os.path.isfile(fp):
                    return (fp, True)
            return (chapter_ref, os.path.isfile(os.path.join(root, chapter_ref)))
        return (None, False)
    # 未知输入：按文件名片段猜测
    return (None, False)


def build_packet(root, tid):
    st, data = TE.load_task(root, tid)
    if st is None:
        raise RuntimeError("任务不存在: %s" % tid)
    task = data.get("task", data)
    ttype = task.get("type", "unknown")
    tmpl = _load_template(ttype)

    out_dir = os.path.join(root, "runtime", "task-packets", tid)
    os.makedirs(out_dir, exist_ok=True)

    # 1) task.yaml
    _gov.dump_yaml(os.path.join(out_dir, "task.yaml"), data)

    # 2) input-index.yaml
    required = (tmpl.get("required_inputs") or task.get("inputs", {}).get("required") or [])
    if isinstance(required, str):
        required = [required]
    inputs = []
    for name in required:
        path, ok = _resolve_input(root, name, task)
        inputs.append({"name": name, "path": path, "resolved": bool(ok)})
    _gov.dump_yaml(os.path.join(out_dir, "input-index.yaml"), {
        "task_id": tid, "required_inputs": inputs,
        "all_resolved": all(i["resolved"] for i in inputs) if inputs else True,
    })

    # 3) context.md（优先引用 context build 产物；否则占位）
    ctx_path = os.path.join(root, "runtime", "context", "CTX-%s-001.md" % tid)
    ctx_lines = ["# Context Package（%s）" % tid, ""]
    if os.path.isfile(ctx_path):
        ctx_lines.append("完整最小上下文已生成：runtime/context/CTX-%s-001.md" % tid)
        ctx_lines.append("（由 `platform context build --task %s` 产出）" % tid)
    else:
        ctx_lines.append("尚未生成最小上下文。请运行：")
        ctx_lines.append("  platform context build --task %s --budget 12000" % tid)
        if task.get("chapter_ref"):
            ctx_lines.append("")
            ctx_lines.append("章节目标：%s" % task["chapter_ref"])
    with open(os.path.join(out_dir, "context.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(ctx_lines) + "\n")

    # 4) constraints.md（权限 + 单 Agent 约束）
    perm = tmpl.get("permissions") or task.get("permissions") or {}
    ep = tmpl.get("execution_policy") or task.get("execution_policy") or {}
    clines = ["# 约束（Constraints）", ""]
    clines.append("## 权限边界")
    clines.append("read   : %s" % perm.get("read", []))
    clines.append("write  : %s" % perm.get("write", []))
    clines.append("forbidden: %s" % perm.get("forbidden", []))
    clines.append("")
    clines.append("## 单 Agent 执行策略")
    clines.append("agent_mode: %s" % ep.get("agent_mode", "single"))
    clines.append("delegation_allowed: %s" % ep.get("delegation_allowed", False))
    clines.append("subagent_allowed: %s" % ep.get("subagent_allowed", False))
    clines.append("parallel_execution_allowed: %s" % ep.get("parallel_execution_allowed", False))
    clines.append("max_agents: %s" % ep.get("max_agents", 1))
    clines.append("required_session: %s" % ep.get("required_session", "current"))
    clines.append("")
    clines.append("禁止：创建子 Agent / 委派 / 并行 Agent / 后台工作单元。")
    clines.append("角色切换通过 Context Package 实现（同会话内），非多 Agent。")
    with open(os.path.join(out_dir, "constraints.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(clines) + "\n")

    # 5) output-contract.yaml
    _gov.dump_yaml(os.path.join(out_dir, "output-contract.yaml"), {
        "task_id": tid,
        "allowed_outputs": tmpl.get("allowed_outputs") or task.get("expected_outputs", []),
        "acceptance": task.get("acceptance", {}),
        "next_tasks": tmpl.get("next_tasks", {}),
    })

    # 6) execution-manifest.yaml
    _gov.dump_yaml(os.path.join(out_dir, "execution-manifest.yaml"), {
        "task_id": tid,
        "role": (task.get("agent") or {}).get("required_role"),
        "mode": ep.get("agent_mode", "single"),
        "budget_tokens": 12000,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "packet_version": "1.0.0",
    })

    return out_dir


def main():
    ap = argparse.ArgumentParser(prog="task-packet", description="生成 Task Packet")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--task", required=True)
    args = ap.parse_args()
    try:
        d = build_packet(args.project_root, args.task)
        print("✓ Task Packet 已生成：%s" % d)
        for fn in sorted(os.listdir(d)):
            print("  - %s" % fn)
    except RuntimeError as e:
        print("ERROR: %s" % e)
        sys.exit(2)


if __name__ == "__main__":
    main()

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
import re

HERE = os.path.dirname(os.path.abspath(__file__))
# [Phase2] 把 scripts 各分组目录加入 sys.path，保持跨组裸名 import 可用
_SCRIPTS = os.path.dirname(HERE)
if os.path.isdir(_SCRIPTS):
    for _d in os.listdir(_SCRIPTS):
        _p = os.path.join(_SCRIPTS, _d)
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _gov
import task_engine as TE
import task_templates as TT

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(HERE)), "core", "task-system", "templates")


def _load_template(name):
    return TT.load(name)


STYLE_FILE_INPUTS = {
    "protected_manifest": ("protected-manifest.yaml",),
    "diagnosis_report": (
        "diagnosis-report.yaml", "diagnosis.yaml", "diagnosis.json"),
    "revision_candidate": ("revision-candidate.md",),
    "revision_result": (
        "revision-result.yaml", "revision-result.json"),
    "fidelity_report": (
        "fidelity-report.yaml", "fidelity-report.json"),
    "quality_report": (
        "quality-report.yaml", "style-quality-report.yaml",
        "quality-report.json"),
    "pre_apply_backup": ("draft-pre-apply.md", "pre-apply.md"),
    "regression_result": (
        "final-regression-result.yaml", "regression-result.yaml",
        "final-regression-result.json", "regression-result.json"),
    "apply_result": ("chapter-apply-result.yaml", "apply-result.yaml"),
    "rollback_result": (
        "chapter-rollback-result.yaml", "rollback-result.yaml"),
    "nkb_sync_proof": ("nkb-sync-proof.yaml",),
}


def _lineage_tasks(root, task, limit=64):
    """Yield current task and dependency ancestors without scanning task pools."""
    queue = [task]
    seen = set()
    while queue and len(seen) < limit:
        current = queue.pop(0)
        task_id = current.get("id")
        if task_id in seen:
            continue
        if task_id:
            seen.add(task_id)
        yield current
        for dep in current.get("dependencies") or []:
            _, data = TE.load_task(root, dep)
            parent = (data or {}).get("task") or {}
            if parent:
                queue.append(parent)


def _existing_value(root, value):
    if isinstance(value, dict):
        return ("inline:structured-value", True)
    if isinstance(value, list):
        return ("inline:list-value", True)
    if not isinstance(value, str) or not value:
        return (None, False)
    if value.startswith(("inline:", "not-applicable:")):
        return (value, True)
    path = value if os.path.isabs(value) else os.path.join(root, value)
    return (path, os.path.exists(path))


def _resolve_from_lineage(root, name, task):
    for source in _lineage_tasks(root, task):
        for values in (
                ((source.get("inputs") or {}).get("values") or {}),
                (source.get("outputs") or {})):
            if not isinstance(values, dict):
                continue
            if values.get(name) not in (None, "", False):
                path, ok = _existing_value(root, values[name])
                if ok:
                    return path, True
        if name in ("chapter_review_report", "review_report"):
            outputs = source.get("outputs") or {}
            value = outputs.get("review_report") or (
                source.get("artifact")
                if source.get("type") == "chapter_review" else None)
            path, ok = _existing_value(root, value)
            if ok:
                return path, True
        for value in (source.get("outputs") or {}).values():
            if not isinstance(value, str):
                continue
            path, ok = _existing_value(root, value)
            if ok and os.path.basename(path) in STYLE_FILE_INPUTS.get(
                    name, ()):
                return path, True
    return None, False


def _latest_style_artifact(root, names):
    style_root = os.path.join(root, "analysis", "style")
    if not os.path.isdir(style_root):
        return None, False
    matches = []
    wanted = set(names)
    for current, dirs, files in os.walk(style_root):
        dirs.sort()
        for filename in files:
            if (
                    filename in wanted
                    or any(filename.endswith("." + name) for name in wanted)):
                matches.append(os.path.join(current, filename))
    if not matches:
        return None, False
    matches.sort(key=os.path.getmtime, reverse=True)
    return matches[0], True


def _resolve_input(root, name, task):
    """把概念性必需输入映射到项目内路径（最佳努力）。"""
    chapter_ref = task.get("chapter_ref")
    if chapter_ref is not None:
        chapter_ref = str(chapter_ref)
    values = (task.get("inputs") or {}).get("values") or {}
    if values.get(name) not in (None, False, ""):
        path, ok = _existing_value(root, values[name])
        if ok:
            return (path, True)
        # Non-path scalar values (hashes, modes, revisions) are valid inline
        # bindings. File-like style inputs must exist.
        if name not in STYLE_FILE_INPUTS and name not in (
                "style_guidance", "quality_policy",
                "publish_authorization"):
            return ("inline:inputs.values.%s" % name, True)
    # 优先解析依赖任务的已提交制品/命名输出。
    lineage_path, lineage_ok = _resolve_from_lineage(root, name, task)
    if lineage_ok:
        return lineage_path, True
    if name in STYLE_FILE_INPUTS:
        path, ok = _latest_style_artifact(
            root, STYLE_FILE_INPUTS[name])
        if ok:
            return path, True
        return None, False
    if name == "style_guidance":
        try:
            import project_layout
            if not project_layout.is_style_strict(root):
                return ("not-applicable:legacy-project", True)
        except Exception:
            pass
        task_path = os.path.join(
            root, "runtime", "learning", "style-guidance",
            "%s.yaml" % task.get("id"))
        path = (
            task_path if os.path.isfile(task_path)
            else os.path.join(
                root, "runtime", "learning", "style-guidance.yaml"))
        return path, os.path.isfile(path)
    if name == "applied_style_rules":
        path = os.path.join(
            root, "runtime", "learning", "style-guidance.yaml")
        return path, os.path.isfile(path)
    if name == "quality_policy":
        platform_root = _gov.find_platform_root()
        path = os.path.join(
            platform_root, "core", "learning", "quality-policies",
            "default.v1.yaml")
        return path, os.path.isfile(path)
    if name in ("apply_readiness", "rollback_readiness"):
        # Readiness is an inline event decision produced by the orchestrator.
        return None, False
    if name == "publish_authorization":
        path = os.path.join(
            root, "operations", "grants",
            "%s.yaml" % task.get("id"))
        return path, os.path.isfile(path)
    if name == "chapter_review_report":
        return _resolve_from_lineage(root, "review_report", task)
    if name == "nkb_snapshot":
        p = os.path.join(root, "NKB")
        return (p, os.path.isdir(p))
    if name == "final_context":
        p = os.path.join(root, "runtime", "context")
        if os.path.isdir(p):
            prefix = "CTX-%s-" % task.get("id", "")
            matches = [os.path.join(p, f) for f in os.listdir(p)
                       if f.startswith(prefix) and f.endswith(".md")]
            if matches:
                return (sorted(matches, key=os.path.getmtime)[-1], True)
        return (None, False)
    if name in ("previous_chapter_handoff", "chapter_handoff"):
        p = os.path.join(root, "handoffs")
        if os.path.isdir(p):
            files = [os.path.join(p, f) for f in os.listdir(p)
                     if os.path.isfile(os.path.join(p, f))]
            if files:
                return (sorted(files, key=os.path.getmtime)[-1], True)
        return (None, False)
    if name == "planning_policy":
        path = os.path.join(
            root, "sources", "outline", "_intake",
            "planning-policy.yaml")
        return (path, os.path.isfile(path))
    if name == "writing_strategy":
        # 旧项目没有 PROJECT_LAYOUT.yaml，也没有启用新式全章规划治理。
        # 对其标记为不适用而非缺失；新建 strict-v2 项目仍必须提供真实编排文件。
        if not os.path.isfile(os.path.join(root, "PROJECT_LAYOUT.yaml")):
            return ("not-applicable:legacy-project", True)
        chapter_match = re.search(
            r"(\d+)", str(chapter_ref or task.get("chapter_ref") or ""))
        if chapter_match:
            path = os.path.join(
                root, "runtime", "writing-strategies",
                "STRATEGY-CH-%03d.yaml" % int(chapter_match.group(1)))
            return (path, os.path.isfile(path))
        return (None, False)
    if name == "chapter_plan":
        if chapter_ref:
            base = os.path.splitext(chapter_ref)[0]
            chapter_match = re.search(r"(\d+)", os.path.basename(base))
            number = int(chapter_match.group(1)) if chapter_match else None
            governed = []
            if number is not None:
                governed = [
                    os.path.join(
                        "sources", "outline", "chapters",
                        "PLAN-%03d.yaml" % number),
                    os.path.join(
                        "sources", "outline", "chapters",
                        "CH-%03d.yaml" % number),
                ]
            for cand in tuple(governed) + (
                    base + "_plan.md", base + ".plan.md",
                    os.path.join(
                        "sources", "outline",
                        os.path.basename(base) + ".md")):
                fp = os.path.join(root, cand)
                if os.path.isfile(fp):
                    return (fp, True)
            return (None, False)
        return (None, False)
    if name == "outline":
        project_file = os.path.join(root, "project.yaml")
        pdata = _gov.load_yaml(project_file) if os.path.isfile(project_file) else {}
        rel = ((pdata.get("paths") or {}).get("outline") or (
            "sources/outline" if os.path.isfile(os.path.join(
                root, "PROJECT_LAYOUT.yaml")) else "")).lstrip("./")
        path = os.path.join(root, rel)
        if os.path.isfile(path):
            return (path, True)
        if os.path.isdir(path):
            has_outline = any(
                filename.lower().endswith((".md", ".yaml", ".yml"))
                for filename in os.listdir(path)
                if os.path.isfile(os.path.join(path, filename))
            )
            return (path, has_outline)
        return (path, False)
    if name == "project_status":
        for rel in ("project/status.derived.yaml", "project/status.yaml",
                    "lifecycle/status.yaml"):
            path = os.path.join(root, rel)
            if os.path.isfile(path):
                return (path, True)
        return (None, False)
    if name in ("chapter_draft", "review_report", "patch",
                "validation_report", "nkb_change", "operation_manifest"):
        return (None, False)
    if name == "review_spec":
        platform_root = _gov.find_platform_root()
        path = os.path.join(platform_root, "core", "review", "review-plan.yaml")
        return (path, os.path.isfile(path))
    if name == "design_review_spec":
        platform_root = _gov.find_platform_root()
        path = os.path.join(
            platform_root, "core", "contracts",
            "design-review.schema.yaml")
        return (path, os.path.isfile(path))
    # 未知输入：按文件名片段猜测
    return (None, False)


def _style_scope_from_plan(root, task):
    """Derive scene and character selectors from the governed chapter plan."""
    values = ((task.get("inputs") or {}).get("values") or {})
    scenes = set(values.get("scene_types") or [])
    if values.get("scene_type"):
        scenes.add(str(values["scene_type"]))
    characters = set(values.get("character_ids") or [])
    plan_path, plan_ok = _resolve_input(root, "chapter_plan", task)
    if plan_ok and isinstance(plan_path, str) and os.path.isfile(plan_path):
        body = _gov.load_yaml(plan_path) or {}
        candidates = body.get("scenes") or (
            (body.get("plan") or {}).get("scenes")) or []
        for scene in candidates:
            if not isinstance(scene, dict):
                continue
            if scene.get("type"):
                scenes.add(str(scene["type"]))
            for participant in scene.get("participants") or []:
                if isinstance(participant, dict):
                    participant = (
                        participant.get("id")
                        or participant.get("character_id")
                        or participant.get("name"))
                if participant:
                    characters.add(str(participant))
    return sorted(scenes or {"daily"}), sorted(characters)


def build_packet(root, tid):
    st, data = TE.load_task(root, tid)
    if st is None:
        raise RuntimeError("任务不存在: %s" % tid)
    task = data.get("task", data)
    ttype = task.get("type", "unknown")
    tmpl = _load_template(ttype)

    # Strict-v2 writing/fix tasks receive a deterministic, task-scoped
    # L0-L4 composition before Ready Check. Candidates are never promoted by
    # this step; only approved/active cards can become effective.
    if ttype in ("chapter_write", "chapter_fix", "continuity_fix"):
        try:
            import project_layout
            if project_layout.is_style_strict(root):
                import style_guidance
                chapter_match = re.search(
                    r"(\d+)", str(task.get("chapter_ref") or tid))
                chapter_id = (
                    "CH-%03d" % int(chapter_match.group(1))
                    if chapter_match else str(task.get("chapter_ref") or tid))
                strategy_path, strategy_ok = _resolve_input(
                    root, "writing_strategy", task)
                scene_types, character_ids = _style_scope_from_plan(
                    root, task)
                output = os.path.join(
                    root, "runtime", "learning", "style-guidance",
                    "%s.yaml" % tid)
                style_guidance.build(
                    root, chapter_id,
                    str(task.get("revision_cycle_id") or tid),
                    scene_types=scene_types,
                    character_ids=character_ids,
                    task_id=tid,
                    writing_strategy_path=(
                        strategy_path if strategy_ok
                        and isinstance(strategy_path, str)
                        and os.path.isfile(strategy_path) else None),
                    output=output)
        except Exception as exc:
            raise RuntimeError(
                "style guidance composition failed for %s: %s"
                % (tid, exc))

    out_dir = os.path.join(root, "runtime", "task-packets", tid)
    os.makedirs(out_dir, exist_ok=True)

    # 1) task.yaml
    _gov.dump_yaml(os.path.join(out_dir, "task.yaml"), data)

    # 2) input-index.yaml
    # 任务实例是当次执行契约的权威来源；模板只为未内联输入的任务提供默认值。
    # 这样已存在的旧任务包不会因平台模板升级而被悄悄追加新必填项。
    required = (
        task.get("inputs", {}).get("required")
        or tmpl.get("required_inputs")
        or [])
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
    ctx_dir = os.path.join(root, "runtime", "context")
    ctx_candidates = []
    if os.path.isdir(ctx_dir):
        prefix = "CTX-%s-" % tid
        ctx_candidates = sorted(
            (os.path.join(ctx_dir, f) for f in os.listdir(ctx_dir)
             if f.startswith(prefix) and f.endswith(".md")),
            key=os.path.getmtime,
            reverse=True,
        )
    ctx_path = ctx_candidates[0] if ctx_candidates else None
    ctx_lines = ["# Context Package（%s）" % tid, ""]
    if ctx_path and os.path.isfile(ctx_path):
        ctx_rel = os.path.relpath(ctx_path, root).replace("\\", "/")
        ctx_lines.append("完整最小上下文已生成：%s" % ctx_rel)
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
    guidance_path, guidance_ok = _resolve_input(
        root, "style_guidance", task)
    guidance_hash = ""
    if guidance_ok and isinstance(guidance_path, str):
        try:
            guidance_hash = (
                _gov.load_yaml(guidance_path) or {}
            ).get("style_guidance_sha256", "")
        except Exception:
            guidance_hash = ""
    _gov.dump_yaml(os.path.join(out_dir, "execution-manifest.yaml"), {
        "task_id": tid,
        "role": (task.get("agent") or {}).get("required_role"),
        "mode": ep.get("agent_mode", "single"),
        "budget_tokens": 12000,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "packet_version": "1.0.0",
        "style_guidance_sha256": guidance_hash,
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

# -*- coding: utf-8 -*-
"""review_orchestrator.py — 单 Agent 多阶段审查编排（Phase B4）

核心定位（路线图 §4.5 L2）：脚本负责「确定性准备」——生成审查证据包 +
五阶段顺序指令 + 空报告模板；AI 主 Agent 按顺序逐阶段深读、填 findings、
脚本校验落盘。不委派子 Agent、不并行（复用 Phase5 单 Agent 策略）。

  platform review run --task T --project-root R

证据包落盘：runtime/reviews/REVIEW-<task>/
  plan.yaml          五阶段指令（注入实际 inputs 路径）
  report.yaml        空 findings 模板（按 review-report.schema.yaml）
  evidence/context.md    最小上下文（context_builder）
  evidence/l1-findings.json  Level-1 脚本预检事实（validators）
  evidence/chapter.md      完整章节正文（AI 深读用）
  review-brief.md     给 AI 的审查简报
"""
import os
import sys
import io
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _gov
import index_builder as IB
import context_builder as CB
import validators as V

PLAN_PATH = os.path.join(HERE, "..", "core", "review", "review-plan.yaml")
SCHEMA_PATH = os.path.join(HERE, "..", "core", "contracts", "review-report.schema.yaml")


def _now_iso():
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


def _load_task(root, task_id):
    import task_engine as TE
    st, data = TE.load_task(root, task_id)
    if st is None:
        return None
    return data


def _find_chapter_path(root, chapter_ref):
    if not chapter_ref:
        return None
    import re
    m = re.search(r"\d+", str(chapter_ref))
    if not m:
        return None
    num = int(m.group(0))
    for c in IB.scan_chapters(root):
        if c.get("number") == num:
            return c.get("path")
    return None


def _run_l1(root, chapter_path):
    """跑 Level-1 预检，返回 findings（捕获 stdout 避免污染）。"""
    if not chapter_path or not os.path.isfile(chapter_path):
        return [{"check": "artifact", "severity": "warn",
                 "detail": "章节文件缺失，跳过 L1 预检"}]
    import types
    args = types.SimpleNamespace(file=chapter_path, project_root=root,
                                 required="", min=None, max=None)
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        findings = V._check_artifact(args)
    except Exception as e:
        findings = [{"check": "artifact", "severity": "fail",
                     "detail": "L1 预检异常: %s" % e}]
    finally:
        sys.stdout = old
    return findings


def run_review(project_root, task_id):
    data = _load_task(project_root, task_id)
    if data is None:
        raise RuntimeError("任务不存在: %s" % task_id)
    chapter_ref = (data.get("chapter_ref") or
                   (data.get("task") or {}).get("chapter_ref"))
    chapter_path = _find_chapter_path(project_root, chapter_ref)

    # 证据包目录
    base = os.path.join(project_root, "runtime", "reviews", "REVIEW-%s" % task_id)
    ev_dir = os.path.join(base, "evidence")
    os.makedirs(ev_dir, exist_ok=True)

    # 1) 上下文（最小）
    ctx_path = None
    try:
        ctx_path = CB.build_context(project_root, task_id, 12000)
    except Exception as e:
        ctx_path = None
    if ctx_path and os.path.isfile(ctx_path):
        import shutil
        shutil.copy(ctx_path, os.path.join(ev_dir, "context.md"))

    # 2) L1 预检事实
    l1 = _run_l1(project_root, chapter_path)
    with open(os.path.join(ev_dir, "l1-findings.json"), "w", encoding="utf-8") as f:
        json.dump(l1, f, ensure_ascii=False, indent=2)

    # 3) 完整章节正文
    if chapter_path and os.path.isfile(chapter_path):
        with open(chapter_path, "r", encoding="utf-8") as f:
            chapter_text = f.read()
        with open(os.path.join(ev_dir, "chapter.md"), "w", encoding="utf-8") as f:
            f.write(chapter_text)
    else:
        with open(os.path.join(ev_dir, "chapter.md"), "w", encoding="utf-8") as f:
            f.write("(章节文件未定位: %s)\n" % chapter_ref)

    # 4) 五阶段计划（注入实际 inputs 路径）
    plan = _gov.load_yaml(PLAN_PATH) or {}
    stages = plan.get("plan", {}).get("stages", [])
    for s in stages:
        if "immersive" in s.get("name", ""):
            s["inputs_resolved"] = {"previous_summary": "summaries/ (若有)",
                                    "full_chapter_text": "evidence/chapter.md"}
        elif "continuity" in s.get("name", ""):
            s["inputs_resolved"] = {"validators_findings": "evidence/l1-findings.json",
                                    "full_chapter_text": "evidence/chapter.md"}
        elif "structural" in s.get("name", "") or "character" in s.get("name", ""):
            s["inputs_resolved"] = {"context": "evidence/context.md",
                                    "full_chapter_text": "evidence/chapter.md"}
        else:
            s["inputs_resolved"] = {"full_chapter_text": "evidence/chapter.md"}
    with open(os.path.join(base, "plan.yaml"), "w", encoding="utf-8") as f:
        _gov.dump_yaml(os.path.join(base, "plan.yaml"), {"plan": plan.get("plan", {})})

    # 5) 空报告模板（按 schema）
    schema = _gov.load_yaml(SCHEMA_PATH) or {}
    finding_req = (schema.get("finding", {}).get("required", [])
                   or ["id", "category", "severity", "location", "observation",
                       "evidence", "reasoning", "impact", "recommended_fix"])
    report = {
        "review_id": "REVIEW-%s" % task_id,
        "task_id": task_id,
        "chapter_ref": chapter_ref,
        "created_at": _now_iso(),
        "stages": [s.get("name") for s in stages],
        "findings": [],  # AI 逐条填充，每条含 finding_req 字段
        "finding_template": {k: None for k in finding_req},
        "verdict": None,  # pass / pass_with_fixes / fail / blocked
    }
    _gov.dump_yaml(os.path.join(base, "report.yaml"), report)

    # 6) 审查简报（给 AI）
    brief = _render_brief(task_id, chapter_ref, stages, l1, base)
    with open(os.path.join(base, "review-brief.md"), "w", encoding="utf-8") as f:
        f.write(brief)

    return os.path.join(base, "review-brief.md")


def _render_brief(task_id, chapter_ref, stages, l1, base):
    lines = []
    lines.append("# 审查简报 · %s" % task_id)
    lines.append("")
    lines.append("- 章节: %s" % chapter_ref)
    lines.append("- 证据包: `%s`" % base)
    lines.append("- 模式: 单 Agent 串行五阶段（不委派/不并行）")
    lines.append("")
    lines.append("## 执行顺序（务必按此顺序）")
    lines.append("")
    for s in stages:
        lines.append("### 阶段 %s · %s" % (s.get("order"), s.get("name")))
        lines.append("- 目的: %s" % s.get("purpose"))
        lines.append("- 聚焦: %s" % "、".join(s.get("focus", [])))
        lines.append("- 输入: %s" % "、".join(s.get("inputs", [])))
        lines.append("- 规则参考: %s" % s.get("policy_ref"))
        lines.append("")
    lines.append("## L1 脚本预检事实（已就绪，先读）")
    lines.append("")
    fails = [f for f in l1 if f.get("severity") in ("fail", "warn")]
    if fails:
        for f in fails:
            lines.append("- [%s] %s: %s" % (f.get("severity"), f.get("check"), f.get("detail")))
    else:
        lines.append("- L1 预检无 fail/warn（或章节未定位）。")
    lines.append("")
    lines.append("## 你的任务")
    lines.append("")
    lines.append("1. 按上述五阶段顺序深读 `evidence/chapter.md`（配合 `evidence/context.md` 与 `evidence/l1-findings.json`）。")
    lines.append("2. 每发现一个问题，按 report.yaml 的 `finding_template` 字段写成一条 finding，追加到 `report.yaml` 的 `findings` 列表。")
    lines.append("3. 阶段 continuity 发现的硬一致性问题 severity 标 `block`（Fatal A 级）。")
    lines.append("4. 全部阶段完成后，给 `verdict`：pass / pass_with_fixes / fail / blocked。")
    lines.append("5. 脚本不替你下质量结论——仅你基于正文与证据判断。")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(prog="review", description="单 Agent 多阶段审查编排")
    ap.add_argument("action", nargs="?", default="run", choices=["run"])
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--task", required=True)
    args = ap.parse_args()
    try:
        brief = run_review(args.project_root, args.task)
        print("✓ 审查证据包已生成，简报：%s" % brief)
    except RuntimeError as e:
        print("ERROR: %s" % e)
        sys.exit(2)


if __name__ == "__main__":
    main()

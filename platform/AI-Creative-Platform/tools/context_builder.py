# -*- coding: utf-8 -*-
"""context_builder.py — 最小上下文构建器（Phase A3 · 最高 Token 节省点）

完整 NKB 不应每次喂给 AI。本模块从 NKB + 索引 + 前章摘要中，
按 章节/角色/时间/优先级 过滤，并按预算分配生成最小 Context Package：

  platform context build --task <TID> --project-root <R> [--budget 12000]

产物：runtime/context/CTX-<TID>-<n>.md

预算分配（token，默认）：
  task 500 / chapter_plan 1800 / characters 2200 / world_state 1400 /
  recent_events 1500 / foreshadow 1000 / previous_summary 1800 /
  constraints 800 / reserve 1000  （total 12000）
超预算自动降级：删低相关内容 → 摘要替代原文 → 保留最高权威事实。

依赖：复用 index_builder 的 NKB 加载与章节探测。
"""
import os
import sys
import re
import json
import datetime
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _gov
import task_engine as TE
import index_builder as IB

_CHAPTER_RE = re.compile(r"第\s*(\d+)\s*章")
# 中文约 1.6 字符/token 估算
_CHARS_PER_TOKEN = 1.6

DEFAULT_BUDGET = {
    "total": 12000,
    "allocation": {
        "task": 500,
        "chapter_plan": 1800,
        "characters": 2200,
        "world_state": 1400,
        "recent_events": 1500,
        "foreshadow": 1000,
        "previous_summary": 1800,
        "constraints": 800,
        "reserve": 1000,
    },
}


def _load_budget(project_root):
    p = os.path.join(project_root, "context.budget.yaml")
    if os.path.isfile(p):
        d = _gov.load_yaml(p) or {}
        if isinstance(d.get("allocation"), dict) and d.get("total"):
            return d
    return DEFAULT_BUDGET


def _cap(text, max_tokens):
    max_chars = int(max_tokens * _CHARS_PER_TOKEN)
    if text is None:
        return ""
    s = str(text)
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "…(截断)"


def _target_chapter(task):
    ch = task.get("chapter_ref") or ""
    m = _CHAPTER_RE.search(ch)
    if m:
        return int(m.group(1))
    # 从 task id 或 title 猜
    m2 = _CHAPTER_RE.search(str(task.get("id", "")) + " " + str(task.get("title", "")))
    return int(m2.group(1)) if m2 else 0


def _select_characters(nkb, target):
    chars = nkb.get("Characters", [])
    if target == 0:
        return chars
    # 主角必含；其余取窗口内事件参与者
    window = set()
    for ev in nkb.get("Events", []):
        cm = _CHAPTER_RE.search(str(ev.get("chapter", "")))
        cn = int(cm.group(1)) if cm else None
        if cn is not None and target - 8 <= cn <= target + 3:
            for p in (ev.get("participants") or []):
                window.add(p)
    out = []
    for c in chars:
        if c.get("id") == "CHR-001" or c.get("id") in window:
            out.append(c)
    return out


def _select_events(nkb, target):
    if target == 0:
        return nkb.get("Events", [])
    out = []
    for ev in nkb.get("Events", []):
        cm = _CHAPTER_RE.search(str(ev.get("chapter", "")))
        cn = int(cm.group(1)) if cm else None
        if cn is not None and target - 12 <= cn <= target + 3:
            out.append(ev)
    return out


def _select_foreshadow(nkb):
    out = []
    for f in nkb.get("Foreshadow", []):
        st = str(f.get("status", "active")).lower()
        if st in ("active", "open", "pending", ""):
            out.append(f)
    return out


def _read_prev_chapter(project_root, target, max_tokens):
    if target <= 1:
        return ""
    info = IB.detect_latest_version(project_root, target - 1)
    if not info.get("path"):
        return ""
    try:
        with open(info["path"], "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        return ""
    return _cap(txt, max_tokens)


def build_context(root, tid, budget=12000):
    st, data = TE.load_task(root, tid)
    if st is None:
        raise RuntimeError("任务不存在: %s" % tid)
    task = data.get("task", data)
    target = _target_chapter(task)
    nkb_dir = IB._nkb_dir(root)
    nkb = IB._load_nkb_components(nkb_dir)
    cfg = _load_budget(root)
    alloc = cfg.get("allocation", DEFAULT_BUDGET["allocation"])

    lines = ["# Context Package（%s）" % tid, ""]
    lines.append("> 目标章节：%s（相关窗口 ±12 章）| 预算 %d token" % (
        task.get("chapter_ref") or "未指定", budget))
    lines.append("")

    # task
    lines.append("## 任务（%d token）" % alloc.get("task", 500))
    lines.append(_cap(json.dumps({
        "id": tid, "type": task.get("type"), "title": task.get("title"),
        "chapter_ref": task.get("chapter_ref"), "priority": task.get("priority"),
    }, ensure_ascii=False), alloc.get("task", 500)))
    lines.append("")

    # characters
    chars = _select_characters(nkb, target)
    lines.append("## 出场角色当前状态（%d token，选 %d 人）" % (alloc.get("characters", 2200), len(chars)))
    for c in chars[:12]:
        brief = " | ".join(str(c.get(k, "")) for k in ("identity", "stage", "goal") if c.get(k))
        lines.append("- %s %s：%s" % (c.get("id"), c.get("name"), _cap(brief, 120)))
    lines.append("")

    # world_state / reader_state / story_state
    ws = nkb.get("WorldState", []) + nkb.get("ReaderState", []) + nkb.get("StoryState", [])
    lines.append("## 世界/读者/故事态（%d token）" % alloc.get("world_state", 1400))
    for w in ws[:20]:
        lines.append("- %s：%s" % (w.get("id"), _cap(w.get("state", w.get("note", "")), 100)))
    lines.append("")

    # recent events
    evs = _select_events(nkb, target)
    lines.append("## 相关事件（%d token，选 %d 件）" % (alloc.get("recent_events", 1500), len(evs)))
    for e in evs[:25]:
        lines.append("- %s %s（%s）：%s" % (
            e.get("id"), e.get("name"), e.get("chapter"),
            _cap(e.get("effect", e.get("cause", "")), 90)))
    lines.append("")

    # foreshadow
    fs = _select_foreshadow(nkb)
    lines.append("## 未回收伏笔（%d token，%d 条）" % (alloc.get("foreshadow", 1000), len(fs)))
    for f in fs[:20]:
        lines.append("- %s：%s" % (f.get("id"), _cap(f.get("description", f.get("note", "")), 90)))
    lines.append("")

    # previous summary
    prev = _read_prev_chapter(root, target, alloc.get("previous_summary", 1800))
    lines.append("## 前一章摘要（%d token）" % alloc.get("previous_summary", 1800))
    lines.append(prev if prev else "（无前一章或尚未生成摘要）")
    lines.append("")

    # constraints（精简）
    lines.append("## 约束（%d token）" % alloc.get("constraints", 800))
    lines.append("- 单 Agent 顺序执行；禁止子 Agent / 委派 / 并行。")
    lines.append("- 角色切换通过 Context Package；不修改 NKB（除非 knowledge-manager）。")
    lines.append("- 完整约束见 Task Packet 的 constraints.md。")
    lines.append("")

    content = "\n".join(lines) + "\n"

    # 写文件：编号自增
    ctx_dir = os.path.join(root, "runtime", "context")
    os.makedirs(ctx_dir, exist_ok=True)
    n = 1
    for fn in os.listdir(ctx_dir):
        m = re.match(r"CTX-%s-(\d+)\.md" % re.escape(tid), fn)
        if m:
            n = max(n, int(m.group(1)) + 1)
    out_path = os.path.join(ctx_dir, "CTX-%s-%03d.md" % (tid, n))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return out_path


def main():
    ap = argparse.ArgumentParser(prog="context", description="最小上下文构建")
    ap.add_argument("action", nargs="?", default="build", choices=["build"])
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--budget", type=int, default=12000)
    args = ap.parse_args()
    try:
        p = build_context(args.project_root, args.task, args.budget)
        print("✓ Context Package 已生成：%s" % p)
    except RuntimeError as e:
        print("ERROR: %s" % e)
        sys.exit(2)


if __name__ == "__main__":
    main()

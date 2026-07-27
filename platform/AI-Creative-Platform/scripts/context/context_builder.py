# -*- coding: utf-8 -*-
"""context_builder.py — 最小上下文构建器（Phase A3 · 最高 Token 节省点）

完整 NKB 不应每次喂给 AI。本模块从 NKB + 索引 + 前章摘要中，
按 章节/角色/时间/优先级 过滤，并按预算分配生成最小 Context Package：

  platform context build --task <TID> --project-root <R> [--budget 12000]

产物：runtime/context/CTX-<TID>-<n>.md

预算分配（token，默认）：
  task 500 / chapter_plan 1800 / writing_strategy 800 / characters 2200 / world_state 1400 /
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
import index_builder as IB

_CHAPTER_RE = re.compile(r"(?:第\s*(\d+)\s*章|CH[-_ ]*0*(\d+))", re.I)
# 中文约 1.6 字符/token 估算
_CHARS_PER_TOKEN = 1.6

DEFAULT_BUDGET = {
    "total": 12000,
    "allocation": {
        "task": 400,
        "chapter_plan": 1200,
        "writing_strategy": 800,
        "canon": 800,
        "characters": 1800,
        "entities": 700,
        "world_state": 900,
        "recent_events": 1200,
        "timeline": 500,
        "assets": 500,
        "foreshadow": 700,
        "terminology": 400,
        "graph": 400,
        "previous_summary": 1300,
        "constraints": 600,
        "reserve": 600,
    },
}

PLATFORM_TASK_TYPES = {"system_maintenance", "system_verify"}
CONTENT_TASK_TYPES = {
    "chapter_write", "chapter_review", "chapter_fix", "continuity_fix",
    "chapter_publish", "nkb_update", "nkb_sync", "plan_write",
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
    m = _CHAPTER_RE.search(str(ch))
    if m:
        return int(m.group(1) or m.group(2))
    # 从 task id 或 title 猜
    m2 = _CHAPTER_RE.search(str(task.get("id", "")) + " " + str(task.get("title", "")))
    return int(m2.group(1) or m2.group(2)) if m2 else 0


def _chapter_number(value):
    match = _CHAPTER_RE.search(str(value or ""))
    return int(match.group(1) or match.group(2)) if match else None


def _select_characters(nkb, target):
    chars = nkb.get("Characters", [])
    if target == 0:
        return chars
    # 主角必含；其余取窗口内事件参与者
    window = set()
    for ev in nkb.get("Events", []):
        cn = _chapter_number(ev.get("chapter"))
        if cn is not None and target - 8 <= cn <= target + 3:
            for p in (ev.get("participants") or []):
                window.add(p)
    out = []
    for c in chars:
        if (c.get("role") == "protagonist" or c.get("protagonist") is True
                or c.get("id") == "CHR-001" or c.get("id") in window):
            out.append(c)
    return out


def _select_events(nkb, target):
    if target == 0:
        return nkb.get("Events", [])
    out = []
    for ev in nkb.get("Events", []):
        cn = _chapter_number(ev.get("chapter"))
        if cn is not None and target - 12 <= cn <= target + 3:
            out.append(ev)
    return out


def _select_foreshadow(nkb):
    out = []
    for f in nkb.get("Foreshadow", []):
        st = str(f.get("status", "active")).lower()
        if st not in (
                "paid_off", "closed", "abandoned", "recycled",
                "已回收", "已废弃", "完成"):
            out.append(f)
    return out


def _record_excerpt(record, fields, max_tokens=180):
    data = {}
    for field in fields:
        value = record.get(field)
        if value not in (None, "", [], {}):
            data[field] = value
    return _cap(json.dumps(data, ensure_ascii=False), max_tokens)


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


def _learning_guidance(project_root, task_type, max_tokens=1200):
    """Render project-private learned guidance into creative task context."""
    refs = [
        ("审查反补写作约束", "runtime/learning/writing-guidance.yaml"),
        ("参考作品项目实验规则", "runtime/learning/reference-guidance.yaml"),
    ]
    if task_type in ("chapter_review", "chapter_fix", "continuity_fix"):
        refs.append(("历史问题回归检查", "runtime/learning/review-regression.yaml"))
    sections = []
    for title, rel in refs:
        path = os.path.join(project_root, rel.replace("/", os.sep))
        if not os.path.isfile(path):
            continue
        try:
            data = _gov.load_yaml(path) or {}
            sections.append("### %s\n%s" % (
                title, _cap(json.dumps(data, ensure_ascii=False), max_tokens)))
        except Exception:
            continue
    return _cap("\n\n".join(sections), max_tokens)


def _chapter_plan(project_root, task, max_tokens):
    """Resolve and load the governed chapter plan used by the task."""
    try:
        import task_packet
        path, resolved = task_packet._resolve_input(
            project_root, "chapter_plan", task)
    except Exception:
        path, resolved = None, False
    if not resolved or not path or not os.path.isfile(path):
        return "（未解析到章节计划；应在 Ready Check 阶段阻断开写）"
    try:
        with open(path, "r", encoding="utf-8") as stream:
            return _cap(stream.read(), max_tokens)
    except Exception:
        return "（章节计划读取失败）"


def _writing_strategy(project_root, task, max_tokens):
    """Load the per-chapter adaptive craft composition plan."""
    try:
        import task_packet
        path, resolved = task_packet._resolve_input(
            project_root, "writing_strategy", task)
    except Exception:
        path, resolved = None, False
    if not resolved or not path or not os.path.isfile(path):
        return "（未解析到写作手法编排；治理项目应在 claim 阶段阻断）"
    try:
        with open(path, "r", encoding="utf-8") as stream:
            return _cap(stream.read(), max_tokens)
    except Exception:
        return "（写作手法编排读取失败）"


def _write_context(root, tid, content):
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

    # Context 与 Task Packet 是一个执行单元；生成上下文后同步 Packet 引用，
    # 避免 Packet 永久保留“尚未生成”的陈旧占位。
    packet_context = os.path.join(
        root, "runtime", "task-packets", tid, "context.md")
    if os.path.isdir(os.path.dirname(packet_context)):
        rel = os.path.relpath(out_path, root).replace("\\", "/")
        with open(packet_context, "w", encoding="utf-8") as f:
            f.write("# Context Package（%s）\n\n" % tid)
            f.write("完整最小上下文已生成：%s\n" % rel)
            f.write("（由 `platform context build --task %s` 产出）\n" % tid)
    return out_path


def _build_platform_context(root, tid, task, budget):
    """Build maintenance context without loading project NKB."""
    platform_root = _gov.find_platform_root()
    values = (task.get("inputs") or {}).get("values") or {}
    permissions = task.get("permissions") or {}
    entrypoints = [
        "AGENTS.md",
        "platform.yaml",
        "core/core.yaml",
        "registry/versions.yaml",
        "registry/projects.yaml",
        "schemas/registry.yaml",
        "templates/registry.yaml",
    ]
    present = [
        p for p in entrypoints
        if os.path.isfile(os.path.join(platform_root, p))
    ]
    lines = [
        "# Platform Context Package（%s）" % tid,
        "",
        "> 任务类型：%s | 预算 %d token | NKB 注入：禁用" %
        (task.get("type"), budget),
        "",
        "## 变更简报",
        str(values.get("change_brief") or task.get("title") or ""),
        "",
        "## 授权",
        "- explicit_user_approval: %s" %
        bool(values.get("explicit_user_approval")),
        "- confirmation_source: %s" %
        (values.get("confirmation_source") or "unknown"),
        "",
        "## 平台权威入口",
    ]
    lines.extend("- %s" % p for p in present)
    lines += [
        "",
        "## 允许范围",
        "- read: %s" % permissions.get("read", []),
        "- write: %s" % permissions.get("write", []),
        "- forbidden: %s" % permissions.get("forbidden", []),
        "",
        "## 执行约束",
        "- 单 Agent 串行；禁止子 Agent、委派、并行 Agent 与后台工作单元。",
        "- 先形成影响评估，再修改；修改后运行 selfcheck、bootstrap、doctor 与全量测试。",
        "- 不读取或修改任何项目 NKB/正文，除非另有独立项目任务授权。",
        "",
    ]
    return _write_context(root, tid, "\n".join(lines))


def _build_non_content_context(root, tid, task, budget):
    """Minimal project context for governance tasks that are not creative content."""
    project_yaml = os.path.join(root, "project.yaml")
    lines = [
        "# Governance Context Package（%s）" % tid,
        "",
        "> 任务类型：%s | 预算 %d token | 创作 NKB 注入：禁用" %
        (task.get("type"), budget),
        "",
        "## 任务",
        json.dumps({
            "id": tid,
            "type": task.get("type"),
            "title": task.get("title"),
            "priority": task.get("priority"),
        }, ensure_ascii=False),
        "",
        "## 项目入口",
        "- project.yaml: %s" % ("present" if os.path.isfile(project_yaml) else "missing"),
        "",
        "## 约束",
        "- 单 Agent 串行；完整权限见 Task Packet。",
        "- 本任务不是章节创作，不加载人物、事件、伏笔或读者态。",
        "",
    ]
    return _write_context(root, tid, "\n".join(lines))


def build_context(root, tid, budget=12000):
    st, data = TE.load_task(root, tid)
    if st is None:
        raise RuntimeError("任务不存在: %s" % tid)
    task = data.get("task", data)
    task_type = task.get("type")
    if task_type in PLATFORM_TASK_TYPES:
        return _build_platform_context(root, tid, task, budget)
    if task_type not in CONTENT_TASK_TYPES:
        return _build_non_content_context(root, tid, task, budget)
    target = _target_chapter(task)
    nkb_dir = IB._nkb_dir(root)
    nkb = IB._load_nkb_components(nkb_dir)
    cfg = _load_budget(root)
    configured = cfg.get("allocation", DEFAULT_BUDGET["allocation"])
    configured_total = max(int(cfg.get("total", 12000)), 1)
    scale = min(1.0, float(budget) / configured_total)
    alloc = {
        name: max(40, int(value * scale))
        for name, value in configured.items()
    }

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

    lines.append("## 章节计划（%d token）" % alloc.get(
        "chapter_plan", 1200))
    lines.append(_chapter_plan(
        root, task, alloc.get("chapter_plan", 1200)))
    lines.append("")

    lines.append("## 写作手法编排（%d token）" % alloc.get(
        "writing_strategy", 800))
    lines.append(_writing_strategy(
        root, task, alloc.get("writing_strategy", 800)))
    lines.append("")

    # Canon is a mandatory writing boundary, not archival metadata.
    canon = nkb.get("Canon", [])
    lines.append("## Canon 不可违背事实（%d token）" % alloc.get("canon", 800))
    for record in canon[:20]:
        lines.append("- %s" % _record_excerpt(
            record, ("id", "name", "category", "statement", "detail",
                     "severity", "exceptions"), 120))
    lines.append("")

    # characters
    chars = _select_characters(nkb, target)
    lines.append("## 出场角色当前状态（%d token，选 %d 人）" % (alloc.get("characters", 2200), len(chars)))
    for c in chars[:12]:
        lines.append("- %s" % _record_excerpt(
            c, ("id", "name", "status", "identity", "personality", "goal",
                "motivation", "abilities", "limits", "relationships",
                "speech", "location", "arc_stage"), 220))
    lines.append("")

    entities = nkb.get("Locations", []) + nkb.get("Organizations", [])
    lines.append("## 地点与组织（%d token）" % alloc.get("entities", 700))
    for record in entities[:20]:
        lines.append("- %s" % _record_excerpt(
            record, ("id", "name", "type", "status", "parent_location",
                     "controlling_faction", "goals", "relationships",
                     "accessibility", "travel_times"), 110))
    lines.append("")

    # world_state / reader_state / story_state
    ws = nkb.get("WorldState", []) + nkb.get("ReaderState", []) + nkb.get("StoryState", [])
    lines.append("## 世界/读者/故事态（%d token）" % alloc.get("world_state", 1400))
    for w in ws[:20]:
        lines.append("- %s" % _record_excerpt(
            w, ("id", "name", "state", "value", "fact_id",
                "epistemic_status", "learned_at", "evidence",
                "active_conflicts", "unresolved_questions",
                "next_constraints", "note"), 130))
    lines.append("")

    timeline = nkb.get("Timeline", [])
    lines.append("## 时间线（%d token）" % alloc.get("timeline", 500))
    for record in timeline[-20:]:
        chapter = _chapter_number(record.get("chapter"))
        if target and chapter and not (target - 12 <= chapter <= target + 3):
            continue
        lines.append("- %s" % _record_excerpt(
            record, ("id", "chapter", "story_time", "event_id", "event"), 90))
    lines.append("")

    # recent events
    evs = _select_events(nkb, target)
    lines.append("## 相关事件（%d token，选 %d 件）" % (alloc.get("recent_events", 1500), len(evs)))
    for e in evs[:25]:
        lines.append("- %s %s（%s）：%s" % (
            e.get("id"), e.get("name"), e.get("chapter"),
            _cap(e.get("effect", e.get("cause", "")), 90)))
    lines.append("")

    assets = nkb.get("Assets", [])
    lines.append("## 资产与能力状态（%d token）" % alloc.get("assets", 500))
    for record in assets[:20]:
        lines.append("- %s" % _record_excerpt(
            record, ("id", "name", "type", "owner", "state",
                     "quantity", "location", "abilities", "limitations",
                     "acquired_event", "lost_event"), 100))
    lines.append("")

    # foreshadow
    fs = _select_foreshadow(nkb)
    lines.append("## 未回收伏笔（%d token，%d 条）" % (alloc.get("foreshadow", 1000), len(fs)))
    for f in fs[:20]:
        lines.append("- %s" % _record_excerpt(
            f, ("id", "name", "content", "status", "planted_at",
                "buried_at", "payoff_window", "deadline_chapter",
                "related_entities", "recycle_plan", "note"), 110))
    lines.append("")

    terms = nkb.get("Terminology", [])
    lines.append("## 术语约束（%d token）" % alloc.get("terminology", 400))
    for record in terms[:30]:
        lines.append("- %s" % _record_excerpt(
            record, ("id", "name", "canonical", "standard",
                     "forbidden", "aliases", "note"), 70))
    lines.append("")

    graphs = nkb.get("Graph", [])
    lines.append("## 关系图摘要（%d token）" % alloc.get("graph", 400))
    for record in graphs[:5]:
        lines.append("- %s" % _record_excerpt(
            record, ("id", "name", "nodes", "edges"), 160))
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

    learned = _learning_guidance(
        root, task_type, alloc.get("reserve", 600))
    if learned:
        lines.append("## 项目学习与审查反补")
        lines.append(learned)
        lines.append("")

    content = "\n".join(lines) + "\n"

    return _write_context(root, tid, content)


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

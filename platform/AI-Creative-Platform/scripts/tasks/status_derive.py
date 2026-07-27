# -*- coding: utf-8 -*-
"""状态派生：从任务系统 + NKB 派生项目状态（不手填）。

CLI：platform status derive --project-root <root>
派生产物：project/status.derived.yaml（可重生成，绝不覆盖手填的 project/status.yaml）

设计原则（呼应 Phase C「维护成本降低」）：
- 脚本负责确定性聚合：任务计数 / 章节前沿 / NKB 组件计数 / 伏笔未回收 / 阻塞检测。
- 脚本不替 AI 下质量结论，只输出客观派生态势，供 AI / doctor 决策。
- 单一事实源仍是任务文件系统 + NKB；派生文件属「可重生产物」，不进版本噪声。
"""
import os
import sys
import re
import datetime

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
import task_engine

SCHEMA = "project-status-derived@1.0.0"
PLANNED_TOTAL_CHAPTERS = 1000  # 六卷总体规划
VOL1_PLANNED = 100

# 手填状态（project/status.yaml）与派生状态（project/status.derived.yaml）的漂移阈值
_CHAPTER_DRIFT = 0


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _path(project_root):
    return os.path.join(project_root, "project", "status.derived.yaml")


def _chapter_from_task(d):
    """从任务 id + title 抽取章节号（如 Ch21 / Ch2-20）。返回 (min, max) 或 None。"""
    t = (d.get("task") or {})
    text = "%s %s" % (t.get("id") or "", t.get("title") or "")
    nums = re.findall(r"Ch(\d+)", text)
    if not nums:
        return None
    nums = [int(n) for n in nums]
    return (min(nums), max(nums))


def _read_yaml(p):
    try:
        d = _gov.load_yaml(p)
    except Exception:
        return None
    return d if isinstance(d, dict) else None


def derive(project_root, write=True):
    """从任务系统 + NKB 派生项目状态。返回 dict（统一派生结构）。"""
    # ── 1. 任务系统聚合 ──
    tasks_by_state = task_engine.list_tasks(project_root)  # {state: [ids]}
    by_state = {s: len(v) for s, v in tasks_by_state.items()}
    total_tasks = sum(by_state.values())
    active_types = set()
    failed = []
    task_records = []
    chapter_max = 0
    chapter_min = None
    completed_chapter_tasks = 0

    for st, ids in tasks_by_state.items():
        for tid in ids:
            stt, d = task_engine.load_task(project_root, tid)
            if not d:
                continue
            t = (d.get("task") or {})
            task_records.append((stt, tid, t))
            ttype = t.get("type")
            if ttype:
                active_types.add(ttype)
            if stt == "completed" and str(ttype or "").startswith("chapter"):
                completed_chapter_tasks += 1
            rng = _chapter_from_task(d)
            if rng:
                chapter_max = max(chapter_max, rng[1])
                chapter_min = rng[0] if chapter_min is None else min(chapter_min, rng[0])

    # Failed files are an audit history, not necessarily a permanent project
    # blocker. A later completed replacement with the same type/title, or an
    # explicit failure.resolved_by link, closes that failure.
    completed_by_id = {
        tid: t for stt, tid, t in task_records if stt == "completed"
    }
    for stt, tid, t in task_records:
        if stt != "failed":
            continue
        failure = t.get("failure") or {}
        resolved_by = failure.get("resolved_by")
        resolved = resolved_by in completed_by_id
        if not resolved:
            for candidate_state, _, candidate in task_records:
                if candidate_state != "completed":
                    continue
                same_work = (
                    candidate.get("type") == t.get("type")
                    and candidate.get("title") == t.get("title")
                )
                newer = str(candidate.get("created") or "") > str(t.get("created") or "")
                if same_work and newer:
                    resolved = True
                    break
        if not resolved:
            failed.append((tid, t.get("title")))

    blocked = len(failed) > 0
    blocked_reason = None
    if failed:
        names = ", ".join(tid for tid, _ in failed[:5])
        blocked_reason = "%d 个失败任务: %s" % (len(failed), names)

    # ── 2. NKB 聚合 ──
    nkb_dir = os.path.join(project_root, "NKB")
    nkb_present = os.path.isdir(nkb_dir)
    component_counts = {}
    open_foreshadows = 0
    total_foreshadows = 0
    if nkb_present:
        for fn in sorted(os.listdir(nkb_dir)):
            if not fn.endswith(".yaml"):
                continue
            d = _read_yaml(os.path.join(nkb_dir, fn))
            if not d:
                continue
            recs = d.get("records") or []
            component_counts[fn[:-5]] = len(recs)
            if fn == "Foreshadow.yaml":
                for r in recs:
                    stt = (r.get("status") or "").strip()
                    total_foreshadows += 1
                    if stt not in ("已回收", "回收", "resolved", "done", "_closed"):
                        open_foreshadows += 1

    # ── 3. 派生进度 ──
    vol1_ratio = round(completed_chapter_tasks / float(VOL1_PLANNED), 3) if VOL1_PLANNED else None
    progress = {
        "planned_total_chapters": PLANNED_TOTAL_CHAPTERS,
        "vol1_planned": VOL1_PLANNED,
        "current_chapter_frontier": chapter_max,
        "chapter_min_seen": chapter_min,
        "completed_chapter_tasks": completed_chapter_tasks,
        "completion_ratio_vol1": vol1_ratio,
    }

    # ── 4. 手填漂移检测（轻量，仅提示）──
    drift = []
    manual = _read_yaml(os.path.join(project_root, "project", "status.yaml"))
    if manual:
        mcur = ((manual.get("current") or {}).get("chapter") or {})
        m_ch = mcur.get("current")
        if m_ch is not None and chapter_max and abs(int(m_ch) - chapter_max) > _CHAPTER_DRIFT:
            drift.append("手填 current.chapter=%s 与派生前沿 %s 不一致" % (m_ch, chapter_max))
        m_blocked = bool((manual.get("current") or {}).get("blocked"))
        if m_blocked != blocked:
            drift.append("手填 blocked=%s 与派生 blocked=%s 不一致" % (m_blocked, blocked))

    health_status = "blocked" if blocked else ("degraded" if not nkb_present else "active")

    result = {
        "schema": SCHEMA,
        "derived_at": _now(),
        "source": "task_system + NKB (auto-derived, not hand-filled)",
        "tasks": {
            "by_state": by_state,
            "total": total_tasks,
            "active_types": sorted(x for x in active_types if x),
        },
        "nkb": {
            "present": nkb_present,
            "component_counts": component_counts,
            "open_foreshadows": open_foreshadows,
            "total_foreshadows": total_foreshadows,
        },
        "progress": progress,
        "blocked": {
            "is_blocked": blocked,
            "reason": blocked_reason,
            "failed_tasks": [tid for tid, _ in failed],
        },
        "drift": drift,
        "health": {"status": health_status},
    }
    if write:
        os.makedirs(os.path.dirname(_path(project_root)), exist_ok=True)
        with open(_path(project_root), "w", encoding="utf-8") as f:
            f.write(_gov.dump_block(result))
    return result


def govern(project_root, write=False):
    """派生状态健康自检（StatusGov 块，统一 Gov 契约）。
    - block   : project.yaml 或 NKB 缺失（项目无法派生）
    - caution : 存在失败/阻塞任务 / 尚未生成 status.derived.yaml / 手填漂移
    - proceed : 派生正常
    注意：caution 不阻断内容型任务 submit（派生状态非章节内容门禁）。
    """
    project_yaml = os.path.join(project_root, "project.yaml")
    nkb_dir = os.path.join(project_root, "NKB")
    derived = _path(project_root)

    if not os.path.isfile(project_yaml):
        return {"gate": {"decision": "block",
                         "reasons": ["project.yaml 缺失，无法派生状态"]},
                "composite": {"health": 0},
                "response": {"project_yaml": False}}
    if not os.path.isdir(nkb_dir):
        return {"gate": {"decision": "block",
                         "reasons": ["NKB 目录缺失，无法派生状态"]},
                "composite": {"health": 0},
                "response": {"nkb": False}}

    res = derive(project_root, write=False)
    reasons = []
    if res["blocked"]["is_blocked"]:
        reasons.append("存在 %d 个失败任务，项目阻塞" % len(res["blocked"]["failed_tasks"]))
    if not os.path.isfile(derived):
        reasons.append("尚未生成 status.derived.yaml（运行 platform status derive）")
    reasons.extend(res.get("drift") or [])

    if reasons:
        health = max(0, 100 - 10 * len(reasons))
        return {"gate": {"decision": "caution", "reasons": reasons},
                "composite": {"health": health},
                "response": {"derived": os.path.isfile(derived),
                             "blocked": res["blocked"]["is_blocked"],
                             "open_foreshadows": res["nkb"]["open_foreshadows"]}}
    return {"gate": {"decision": "proceed", "reasons": []},
            "composite": {"health": 100},
            "response": {"derived": True, "blocked": False,
                         "open_foreshadows": res["nkb"]["open_foreshadows"]}}


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="status_derive", description="状态派生（任务+NKB）")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--no-write", action="store_true", help="只计算不落盘")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = derive(args.project_root, write=not args.no_write)
    if args.json:
        import json
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(_gov.dump_block(res))


if __name__ == "__main__":
    main()

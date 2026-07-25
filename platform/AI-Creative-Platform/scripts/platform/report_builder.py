# -*- coding: utf-8 -*-
"""报告生成器（Phase C · PC-4）：把既有派生数据渲染为可读 Markdown 报告。

子命令（platform report <type> --project-root R）：
  project-status    项目派生状态（复用 status_derive，不手填）
  chapter-quality   章节质量/读者评分聚合（analysis/quality + analysis/reader）
  open-foreshadow   NKB 未回收伏笔清单（Foreshadow.yaml）
  task-progress     任务系统推进态势（tasks/<status> 计数 + 阻塞）
  nkb-health        NKB 组件健康（组件计数 + 空组件标记）
  all               以上全部

设计原则（呼应 Phase C「维护成本降低」）：
- 脚本只做确定性聚合与渲染，不替 AI 下质量结论。
- 缺失数据源时降级提示（如「需先运行 platform quality/reader」），绝不崩溃。
- 报告产物为 Markdown 文本，默认打印，可选 --output 落盘（不进版本噪声）。
"""
import os
import sys
import glob

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
import status_derive
import task_engine

CLOSED_FORESHADOW = ("已回收", "回收", "resolved", "done", "_closed")


def _h1(t):
    return "\n# %s\n" % t


def _h2(t):
    return "\n## %s\n" % t


def _kv(rows):
    return "\n".join("- **%s**：%s" % (k, v) for k, v in rows)


def _table(headers, rows):
    if not rows:
        return "（无数据）"
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(lines)


def report_project_status(project_root):
    res = status_derive.derive(project_root, write=False)
    t = res["tasks"]
    n = res["nkb"]
    p = res["progress"]
    b = res["blocked"]
    out = []
    out.append(_h1("项目派生状态报告（自动派生·不手填）"))
    out.append(_kv([
        ("派生时间", res["derived_at"]),
        ("数据来源", res["source"]),
        ("健康状态", res["health"]["status"]),
    ]))
    out.append(_h2("任务系统"))
    by_state = t["by_state"]
    out.append(_kv([
        ("任务总数", t["total"]),
        ("活跃类型", ", ".join(t["active_types"]) or "—"),
    ]))
    state_rows = [[s, c] for s, c in sorted(by_state.items(), key=lambda x: -x[1])]
    out.append(_table(["状态", "数量"], state_rows))
    out.append(_h2("NKB 知识库"))
    out.append(_kv([
        ("是否存在", "是" if n["present"] else "否"),
        ("伏笔未回收", "%d / %d" % (n["open_foreshadows"], n["total_foreshadows"])),
    ]))
    comp_rows = [[k, v] for k, v in sorted(n["component_counts"].items())]
    out.append(_table(["组件", "记录数"], comp_rows))
    out.append(_h2("进度派生"))
    out.append(_kv([
        ("章节前沿(current_chapter_frontier)", p["current_chapter_frontier"] or "—"),
        ("已完成章节任务", p["completed_chapter_tasks"]),
        ("卷一完成比", "%.1f%%" % (p["completion_ratio_vol1"] * 100 if p["completion_ratio_vol1"] is not None else 0)),
    ]))
    out.append(_h2("阻塞态势"))
    if b["is_blocked"]:
        out.append("- ⚠️ **项目阻塞**：%s" % b["reason"])
        out.append("- 失败任务：%s" % ", ".join(b["failed_tasks"]))
    else:
        out.append("- 无失败任务，未阻塞。")
    if res.get("drift"):
        out.append(_h2("手填漂移提示"))
        out.append("\n".join("- %s" % d for d in res["drift"]))
    return "\n".join(out) + "\n"


def _load_yaml_safe(p):
    try:
        d = _gov.load_yaml(p)
    except Exception:
        return None
    return d if isinstance(d, dict) else None


def report_chapter_quality(project_root):
    qdir = os.path.join(project_root, "analysis", "quality")
    rdir = os.path.join(project_root, "analysis", "reader")
    out = []
    out.append(_h1("章节质量 / 读者体验报告"))
    q_files = []
    r_files = []
    if os.path.isdir(qdir):
        for f in os.listdir(qdir):
            if f.startswith("QUAL-") and f.endswith(".yaml"):
                q_files.append(os.path.join(qdir, f))
        q_files.sort()
    if os.path.isdir(rdir):
        for f in os.listdir(rdir):
            if f.startswith("READ-") and f.endswith(".yaml"):
                r_files.append(os.path.join(rdir, f))
        r_files.sort()
    if not q_files and not r_files:
        out.append("\n（暂无评分数据：需先运行 `platform quality` / `platform reader` 生成 analysis/quality 与 analysis/reader）")
        return "\n".join(out) + "\n"

    qd = {}
    for f in q_files:
        d = _load_yaml_safe(f)
        if not d:
            continue
        tid = (d.get("target") or {}).get("target_id")
        comp = (d.get("composite") or {}).get("value")
        gd = (d.get("gate") or {}).get("decision")
        if tid is not None:
            qd[tid] = {"q": comp, "qgate": gd}
    rd = {}
    for f in r_files:
        d = _load_yaml_safe(f)
        if not d:
            continue
        tid = (d.get("target") or {}).get("target_id")
        if tid is not None:
            rd[tid] = {"ri": d.get("reader_index"), "pi": d.get("pi"),
                       "fatal": d.get("fatal"), "rgate": (d.get("gate") or {}).get("decision")}

    chapters = sorted(set(qd) | set(rd), key=lambda x: int(x) if str(x).isdigit() else x)
    rows = []
    q_vals, ri_vals = [], []
    blocked = 0
    for c in chapters:
        q = qd.get(c, {})
        r = rd.get(c, {})
        qv = q.get("q")
        riv = r.get("ri")
        if qv is not None:
            q_vals.append(float(qv))
        if riv is not None:
            ri_vals.append(float(riv))
        if (q.get("qgate") == "block") or (r.get("rgate") == "block") or r.get("fatal"):
            blocked += 1
        rows.append([c,
                     ("%.1f" % qv) if qv is not None else "—",
                     q.get("qgate") or "—",
                     ("%.1f" % riv) if riv is not None else "—",
                     ("%.1f" % r["pi"]) if r.get("pi") is not None else "—",
                     r.get("rgate") or "—"])
    out.append(_table(["章", "质量分", "质量门禁", "读者指数RI", "PI", "读者门禁"], rows))
    out.append(_h2("汇总"))
    avg_q = (sum(q_vals) / len(q_vals)) if q_vals else None
    avg_ri = (sum(ri_vals) / len(ri_vals)) if ri_vals else None
    out.append(_kv([
        ("评分章节数", len(chapters)),
        ("平均质量分", "%.1f" % avg_q if avg_q is not None else "—"),
        ("平均读者指数RI", "%.1f" % avg_ri if avg_ri is not None else "—"),
        ("门禁阻断章节", blocked),
    ]))
    return "\n".join(out) + "\n"


def report_open_foreshadow(project_root):
    fp = os.path.join(project_root, "NKB", "Foreshadow.yaml")
    out = []
    out.append(_h1("未回收伏笔清单（Open Foreshadow）"))
    d = _load_yaml_safe(fp)
    if not d:
        out.append("\n（NKB/Foreshadow.yaml 缺失或无数据）")
        return "\n".join(out) + "\n"
    recs = d.get("records") or []
    open_list = [r for r in recs if (r.get("status") or "").strip() not in CLOSED_FORESHADOW]
    rows = []
    for r in open_list:
        rows.append([r.get("id"), r.get("name"), r.get("buried_at"),
                     r.get("deadline_chapter"), r.get("recycle_plan")])
    out.append(_kv([
        ("未回收", len(open_list)),
        ("总计", len(recs)),
    ]))
    out.append(_table(["ID", "名称", "埋设点", "最迟回收章", "回收计划"], rows))
    return "\n".join(out) + "\n"


def report_task_progress(project_root):
    out = []
    out.append(_h1("任务系统推进报告"))
    by_state = task_engine.list_tasks(project_root)
    total = sum(len(v) for v in by_state.values())
    active_types = set()
    failed = []
    frontier = 0
    for st, ids in by_state.items():
        for tid in ids:
            _, d = task_engine.load_task(project_root, tid)
            if not d:
                continue
            tt = (d.get("task") or {}).get("type")
            if tt:
                active_types.add(tt)
            if st == "failed":
                failed.append(tid)
            rng = status_derive._chapter_from_task(d)
            if rng:
                frontier = max(frontier, rng[1])
    out.append(_kv([
        ("任务总数", total),
        ("活跃类型", ", ".join(sorted(x for x in active_types if x)) or "—"),
        ("章节前沿", frontier or "—"),
    ]))
    rows = [[s, len(v)] for s, v in sorted(by_state.items(), key=lambda x: -len(x[1]))]
    out.append(_table(["状态", "数量"], rows))
    out.append(_h2("阻塞"))
    if failed:
        out.append("- ⚠️ 失败任务：%s" % ", ".join(failed))
    else:
        out.append("- 无失败任务。")
    return "\n".join(out) + "\n"


def report_nkb_health(project_root):
    nkb_dir = os.path.join(project_root, "NKB")
    out = []
    out.append(_h1("NKB 组件健康报告"))
    if not os.path.isdir(nkb_dir):
        out.append("\n（NKB 目录缺失）")
        return "\n".join(out) + "\n"
    counts = {}
    for fn in sorted(os.listdir(nkb_dir)):
        if not fn.endswith(".yaml"):
            continue
        d = _load_yaml_safe(os.path.join(nkb_dir, fn))
        if not d:
            continue
        counts[fn[:-5]] = len(d.get("records") or [])
    empty = [k for k, v in counts.items() if v == 0]
    total_recs = sum(counts.values())
    out.append(_kv([
        ("组件数", len(counts)),
        ("总记录数", total_recs),
        ("空组件(待填充)", ", ".join(empty) if empty else "无"),
    ]))
    out.append(_table(["组件", "记录数"], [[k, v] for k, v in sorted(counts.items())]))
    if empty:
        out.append("\n⚠️ 以下组件记录为空，建议优先填充：%s" % ", ".join(empty))
    return "\n".join(out) + "\n"


def render_all(project_root):
    return "\n".join([
        report_project_status(project_root),
        report_chapter_quality(project_root),
        report_open_foreshadow(project_root),
        report_task_progress(project_root),
        report_nkb_health(project_root),
    ])


def govern(project_root, write=False):
    """报告生成器健康自检（ReportGov 块，统一 Gov 契约）。
    - block  : 无（报告生成器本身不阻断内容任务）
    - caution : NKB 缺失（open-foreshadow / nkb-health 报告降级为空）
    - proceed : NKB 存在，五类报告均可生成
    """
    nkb_dir = os.path.join(project_root, "NKB")
    if not os.path.isdir(nkb_dir):
        return {"gate": {"decision": "caution",
                         "reasons": ["NKB 目录缺失，open-foreshadow/nkb-health 报告降级为空"]},
                "composite": {"health": 80},
                "response": {"nkb": False}}
    return {"gate": {"decision": "proceed", "reasons": []},
            "composite": {"health": 100},
            "response": {"nkb": True}}


_DISPATCH = {
    "project-status": report_project_status,
    "chapter-quality": report_chapter_quality,
    "open-foreshadow": report_open_foreshadow,
    "task-progress": report_task_progress,
    "nkb-health": report_nkb_health,
    "all": render_all,
}


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="report_builder", description="报告生成器（Phase C PC-4）")
    ap.add_argument("rtype", choices=list(_DISPATCH.keys()),
                    help="报告类型")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--output", default=None, help="落盘 Markdown 文件路径（默认打印）")
    args = ap.parse_args()
    md = _DISPATCH[args.rtype](args.project_root)
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(md)
        print("✓ report written -> %s" % args.output)
    else:
        print(md)


if __name__ == "__main__":
    main()

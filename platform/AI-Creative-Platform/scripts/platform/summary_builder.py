# -*- coding: utf-8 -*-
"""summary_builder.py — 章节/卷/弧/滚动摘要落盘（Phase B2）

设计原则（路线图 §4.4）：章节结构化摘要属语义内容，**由 AI 在产出契约里填写
plot/character_changes/new_events/new_information/open_threads，脚本只负责落盘与聚合**，
脚本不反向从正文抽取语义。摘要与 NKB 同属事实源，落盘到项目根 summaries/（入库，不 gitignore）。
"""
import os
import sys
import json
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

_SUM_FIELDS = ["chapter_id", "title", "volume", "arc", "plot",
               "character_changes", "new_events", "new_information", "open_threads"]


def _sum_dir(project_root):
    return os.path.join(project_root, "summaries", "chapters")


def _now_iso():
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


def _load_data(data_str, data_file):
    if data_file:
        if not os.path.isfile(data_file):
            raise RuntimeError("data-file 不存在: %s" % data_file)
        return _gov.load_yaml(data_file)
    if data_str:
        try:
            return json.loads(data_str)
        except Exception:
            return _yaml_lite_load(data_str)
    return {}


def _yaml_lite_load(text):
    import _yaml_lite
    return _yaml_lite.load(text)


def build_chapter_summary(project_root, chapter_id, data=None, source_task=None):
    """AI 填契约字段 → 脚本落盘 summaries/chapters/<chapter_id>-summary.yaml。

    data 可含：title/volume/arc/plot/character_changes/new_events/new_information/open_threads。
    返回落盘路径。summary_version 自动递增（同章已有摘要则 +1）。
    """
    data = data or {}
    cid = chapter_id or data.get("chapter_id")
    if not cid:
        raise RuntimeError("chapter_id 缺失（需 --chapter 或 data.chapter_id）")
    d = dict(data)
    d["chapter_id"] = cid
    if source_task:
        d["source_task"] = source_task

    out_dir = _sum_dir(project_root)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "%s-summary.yaml" % cid)

    existing = {}
    if os.path.isfile(path):
        try:
            existing = _gov.load_yaml(path) or {}
        except Exception:
            existing = {}
    cur_ver = existing.get("summary_version") or 0
    d["summary_version"] = cur_ver + 1
    d["created_at"] = existing.get("created_at") or _now_iso()
    d["updated_at"] = _now_iso()

    # 列表字段默认空列表，保证 schema 稳定
    for k in ("character_changes", "new_events", "new_information", "open_threads"):
        if d.get(k) is None:
            d[k] = []

    _gov.dump_yaml(path, d)
    return path


def _scan_chapter_summaries(project_root):
    out_dir = _sum_dir(project_root)
    if not os.path.isdir(out_dir):
        return []
    out = []
    for fn in sorted(os.listdir(out_dir)):
        if not fn.endswith(".yaml"):
            continue
        try:
            d = _gov.load_yaml(os.path.join(out_dir, fn))
        except Exception:
            continue
        if isinstance(d, dict):
            out.append(d)
    return out


def _dedup_merge(items):
    seen = set()
    out = []
    for x in items:
        h = json.dumps(x, ensure_ascii=False, sort_keys=True)
        if h in seen:
            continue
        seen.add(h)
        out.append(x)
    return out


def aggregate_volume(project_root, volume):
    """聚合该卷所有章节摘要 → summaries/volumes/<volume>-summary.yaml。"""
    all_sum = _scan_chapter_summaries(project_root)
    vols = [s for s in all_sum if (s.get("volume") or "") == volume]
    if not vols:
        raise RuntimeError("未找到 volume=%s 的章节摘要" % volume)
    agg = {
        "volume": volume,
        "chapter_count": len(vols),
        "chapters": [s.get("chapter_id") for s in vols],
        "plots": [{"chapter_id": s.get("chapter_id"), "plot": s.get("plot")} for s in vols],
        "character_changes": _dedup_merge(
            [c for s in vols for c in (s.get("character_changes") or [])]),
        "new_events": _dedup_merge(
            [e for s in vols for e in (s.get("new_events") or [])]),
        "open_threads": _dedup_merge(
            [t for s in vols for t in (s.get("open_threads") or [])]),
        "updated_at": _now_iso(),
    }
    out_dir = os.path.join(project_root, "summaries", "volumes")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "%s-summary.yaml" % volume)
    _gov.dump_yaml(path, agg)
    return path


def aggregate_arc(project_root, arc):
    """聚合该弧所有章节摘要 → summaries/arcs/<arc>-summary.yaml。"""
    all_sum = _scan_chapter_summaries(project_root)
    arcs = [s for s in all_sum if (s.get("arc") or "") == arc]
    if not arcs:
        raise RuntimeError("未找到 arc=%s 的章节摘要" % arc)
    agg = {
        "arc": arc,
        "chapter_count": len(arcs),
        "chapters": [s.get("chapter_id") for s in arcs],
        "plots": [{"chapter_id": s.get("chapter_id"), "plot": s.get("plot")} for s in arcs],
        "character_changes": _dedup_merge(
            [c for s in arcs for c in (s.get("character_changes") or [])]),
        "new_events": _dedup_merge(
            [e for s in arcs for e in (s.get("new_events") or [])]),
        "open_threads": _dedup_merge(
            [t for s in arcs for t in (s.get("open_threads") or [])]),
        "updated_at": _now_iso(),
    }
    out_dir = os.path.join(project_root, "summaries", "arcs")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "%s-summary.yaml" % arc)
    _gov.dump_yaml(path, agg)
    return path


def rollup(project_root):
    """全局滚动摘要 → summaries/rollup.yaml。"""
    all_sum = _scan_chapter_summaries(project_root)
    by_volume = {}
    open_threads = []
    for s in all_sum:
        v = s.get("volume") or "(未分卷)"
        by_volume.setdefault(v, 0)
        by_volume[v] += 1
        for t in (s.get("open_threads") or []):
            if t not in open_threads:
                open_threads.append(t)
    agg = {
        "chapter_count": len(all_sum),
        "by_volume": by_volume,
        "open_threads_total": len(open_threads),
        "open_threads": open_threads,
        "updated_at": _now_iso(),
    }
    out_dir = os.path.join(project_root, "summaries")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "rollup.yaml")
    _gov.dump_yaml(path, agg)
    return path


def main():
    ap = argparse.ArgumentParser(prog="summary", description="章节/卷/弧/滚动摘要落盘")
    ap.add_argument("action", nargs="?", default="build",
                    choices=["build", "aggregate", "rollup"])
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--chapter", default=None)
    ap.add_argument("--data", default=None)
    ap.add_argument("--data-file", default=None)
    ap.add_argument("--volume", default=None)
    ap.add_argument("--arc", default=None)
    ap.add_argument("--task", default=None)
    args = ap.parse_args()

    if args.action == "build":
        if not (args.data or args.data_file):
            print("ERROR: build 需 --data 或 --data-file（AI 填好的结构化字段）")
            sys.exit(2)
        data = _load_data(args.data, args.data_file)
        p = build_chapter_summary(args.project_root, args.chapter, data, args.task)
        print("✓ 章节摘要已落盘：%s" % p)
    elif args.action == "aggregate":
        if args.volume:
            p = aggregate_volume(args.project_root, args.volume)
        elif args.arc:
            p = aggregate_arc(args.project_root, args.arc)
        else:
            print("ERROR: aggregate 需 --volume 或 --arc")
            sys.exit(2)
        print("✓ 聚合摘要已落盘：%s" % p)
    elif args.action == "rollup":
        p = rollup(args.project_root)
        print("✓ 滚动摘要已落盘：%s" % p)


if __name__ == "__main__":
    main()

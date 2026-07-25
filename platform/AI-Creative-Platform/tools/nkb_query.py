# -*- coding: utf-8 -*-
"""nkb_query.py — NKB 查询与投影接口（Phase A5）

AI 不应直接读取所有 NKB YAML。本模块提供查询接口，只返回任务所需结果：

  platform query get <component> <id> [--project-root X]
  platform query state <component> <id> [--at <chapter>]
  platform query events --entity <id> [--before <chapter>]
  platform query foreshadow --status active [--chapter <ch>]
  platform query reader-known [--at <chapter>]
  platform query project assets <id> [--at <event>]

component 接受：character/event/asset/terminology/foreshadow/reader/world/story/timeline/canon/graph
（也接受 NKB 组件原名，如 Characters）。

投影：project assets 通过事件溯源（按章节序）推导某角色当前持有物品。
"""
import os
import sys
import re
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import index_builder as IB

_CHAPTER_RE = re.compile(r"第\s*(\d+)\s*章")
_COMP_MAP = {
    "character": "Characters", "characters": "Characters",
    "event": "Events", "events": "Events",
    "asset": "Assets", "assets": "Assets",
    "terminology": "Terminology", "term": "Terminology",
    "foreshadow": "Foreshadow", "reader": "ReaderState",
    "world": "WorldState", "story": "StoryState",
    "timeline": "Timeline", "canon": "Canon", "graph": "Graph",
}


def _comp_name(component):
    return _COMP_MAP.get(component.lower(), component)


def _resolve_root(explicit):
    if explicit:
        return os.path.abspath(explicit)
    d = os.getcwd()
    while True:
        if os.path.isfile(os.path.join(d, "project.yaml")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.getcwd()


def _find(proot, component, rid):
    nkb = IB._load_nkb_components(IB._nkb_dir(proot))
    comp = _comp_name(component)
    for r in nkb.get(comp, []):
        if str(r.get("id")) == str(rid):
            return r
    return None


def _events_for(proot, entity, before=None):
    nkb = IB._load_nkb_components(IB._nkb_dir(proot))
    out = []
    for e in nkb.get("Events", []):
        if entity not in (e.get("participants") or []):
            continue
        if before is not None:
            cm = _CHAPTER_RE.search(str(e.get("chapter", "")))
            cn = int(cm.group(1)) if cm else None
            if cn is None or cn >= int(before):
                continue
        out.append(e)
    return out


def _event_chapter(proot, evid):
    if not evid:
        return None
    ev = _find(proot, "Events", evid)
    if not ev:
        return None
    cm = _CHAPTER_RE.search(str(ev.get("chapter", "")))
    return int(cm.group(1)) if cm else None


def _project_assets(proot, entity, at_event=None):
    """事件溯源投影：角色当前持有物品。"""
    nkb = IB._load_nkb_components(IB._nkb_dir(proot))
    owned = [a for a in nkb.get("Assets", []) if a.get("owner") == entity]
    if at_event is None:
        return [a.get("id") for a in owned]
    tchap = _event_chapter(proot, at_event)
    held = []
    for a in owned:
        acq_ch = _event_chapter(proot, a.get("acquired_event"))
        lost_ch = _event_chapter(proot, a.get("lost_event"))
        if acq_ch is not None and tchap is not None and acq_ch > tchap:
            continue
        if lost_ch is not None and tchap is not None and lost_ch <= tchap:
            continue
        held.append(a.get("id"))
    return held


def _norm_chapter(ch):
    if ch is None:
        return None
    ch = str(ch).lstrip("CH-").lstrip("0") or "0"
    return int(ch)


def _parent():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--project-root", default=None)
    return p


def main():
    ap = argparse.ArgumentParser(prog="query", description="NKB 查询/投影")
    ap.add_argument("--project-root", default=None)
    sub = ap.add_subparsers(dest="action")
    parent = _parent()

    g = sub.add_parser("get", parents=[parent], help="取单条记录")
    g.add_argument("component")
    g.add_argument("id")

    s = sub.add_parser("state", parents=[parent], help="取实体状态（含至某章的事件）")
    s.add_argument("component")
    s.add_argument("id")
    s.add_argument("--at", default=None, help="章节号（CH-020 或 20）")

    e = sub.add_parser("events", parents=[parent], help="查实体相关事件")
    e.add_argument("--entity", required=True)
    e.add_argument("--before", default=None, help="仅返回此章之前的事件")

    f = sub.add_parser("foreshadow", parents=[parent], help="查伏笔")
    f.add_argument("--status", default="active")
    f.add_argument("--chapter", default=None)

    r = sub.add_parser("reader-known", parents=[parent], help="读者已知/未知")
    r.add_argument("--at", default=None)

    pj = sub.add_parser("project", parents=[parent], help="投影（事件溯源）")
    pj.add_argument("kind", choices=["assets"])
    pj.add_argument("id")
    pj.add_argument("--at", default=None, help="事件 ID（如 EVT-035）")

    args = ap.parse_args()
    proot = _resolve_root(getattr(args, "project_root", None))

    if args.action == "get":
        rec = _find(proot, args.component, args.id)
        print(json.dumps(rec, ensure_ascii=False, indent=2) if rec else "# 未找到 %s/%s" % (args.component, args.id))
    elif args.action == "state":
        rec = _find(proot, args.component, args.id)
        if not rec:
            print("# 未找到 %s/%s" % (args.component, args.id))
            return
        evs = _events_for(proot, args.id, before=_norm_chapter(args.at))
        print(json.dumps({"record": rec, "events_up_to": evs}, ensure_ascii=False, indent=2))
    elif args.action == "events":
        evs = _events_for(proot, args.entity, before=_norm_chapter(args.before))
        print(json.dumps(evs, ensure_ascii=False, indent=2))
    elif args.action == "foreshadow":
        nkb = IB._load_nkb_components(IB._nkb_dir(proot))
        fs = [f for f in nkb.get("Foreshadow", []) if str(f.get("status", "active")).lower() == args.status.lower()]
        print(json.dumps(fs, ensure_ascii=False, indent=2))
    elif args.action == "reader-known":
        nkb = IB._load_nkb_components(IB._nkb_dir(proot))
        print(json.dumps(nkb.get("ReaderState", []), ensure_ascii=False, indent=2))
    elif args.action == "project":
        if args.kind == "assets":
            held = _project_assets(proot, args.id, at_event=args.at)
            print(json.dumps({"entity": args.id, "held_assets": held}, ensure_ascii=False, indent=2))
    else:
        ap.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()

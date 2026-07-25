#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""graph_viz.py — Phase 3-5 图谱可视化（Knowledge Graph Viz）

把 NKB 组件（Characters/Events/Graph/WorldState/Canon）转 graph JSON（nodes/edges），
渲染 HTML/SVG。**只读 NKB，不修改**。空 NKB→空图（0 节点/0 边），不报错。
零依赖：复用同目录 _yaml_lite / _gov。
"""
import os
import sys
import json
import argparse
import datetime
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
# [Phase2] 把 scripts 各分组目录加入 sys.path，保持跨组裸名 import 可用
_SCRIPTS = os.path.dirname(HERE)
if os.path.isdir(_SCRIPTS):
    for _d in os.listdir(_SCRIPTS):
        _p = os.path.join(_SCRIPTS, _d)
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p)
sys.path.insert(0, HERE)
import _yaml_lite
import _gov

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

# 节点类型调色板（渲染用）
_TYPE_COLOR = {
    "character": "#4C72B0",
    "event": "#C44E52",
    "faction": "#8172B3",
    "location": "#55A868",
    "item": "#CCB974",
    "concept": "#64B5CD",
    "other": "#999999",
}


def _nkb_path(project_root, name):
    return os.path.join(project_root, "NKB", name)


def _load_nkb(project_root, name):
    p = _nkb_path(project_root, name)
    if not os.path.isfile(p):
        return []
    try:
        d = _yaml_lite.load_file(p)
    except Exception:
        return []
    if isinstance(d, dict):
        recs = d.get("records")
        if isinstance(recs, list):
            return recs
    return []


def _rec_id(rec, fallback_idx):
    if isinstance(rec, dict):
        for k in ("id", "name", "key"):
            if rec.get(k):
                return str(rec[k])
    return "n%d" % fallback_idx


# ── 构建图 ──────────────────────────────────────────────
def build_graph(project_root):
    """从 NKB 组件回收 nodes/edges（只读，不修改 NKB）。空 NKB→空图。"""
    nodes = {}
    edges = []

    def add_node(nid, label, ntype):
        if nid and nid not in nodes:
            nodes[nid] = {"id": nid, "label": label or nid, "type": ntype}

    def add_edge(src, tgt, kind):
        if src and tgt:
            edges.append({"source": src, "target": tgt, "kind": kind or "related"})

    # 1) Characters → character 节点 + relationships/faction 边
    for i, rec in enumerate(_load_nkb(project_root, "Characters.yaml")):
        if not isinstance(rec, dict):
            continue
        cid = _rec_id(rec, i)
        add_node(cid, rec.get("name") or rec.get("id"), "character")
        # 关系边
        for rel in (rec.get("relationships") or []):
            if isinstance(rel, dict):
                tgt = rel.get("target") or rel.get("to")
                add_edge(cid, str(tgt) if tgt is not None else None, rel.get("kind") or "relationship")
            elif isinstance(rel, str):
                add_edge(cid, rel, "relationship")
        # 阵营归属
        for fld in ("faction", "allegiance", "affiliation"):
            fv = rec.get(fld)
            if fv:
                fid = "faction:%s" % fv
                add_node(fid, str(fv), "faction")
                add_edge(cid, fid, "affiliation")

    # 2) Events → event 节点 + participants/related 边
    for i, rec in enumerate(_load_nkb(project_root, "Events.yaml")):
        if not isinstance(rec, dict):
            continue
        eid = _rec_id(rec, i)
        add_node(eid, rec.get("name") or rec.get("id"), "event")
        for fld in ("participants", "related", "characters", "involved"):
            for p in (rec.get(fld) or []):
                add_edge(eid, str(p) if p is not None else None, "participant")

    # 3) Graph.yaml → 显式 nodes/edges（优先），否则逐条作节点
    for i, rec in enumerate(_load_nkb(project_root, "Graph.yaml")):
        if not isinstance(rec, dict):
            continue
        if rec.get("nodes") or rec.get("edges"):
            for n in (rec.get("nodes") or []):
                if isinstance(n, dict):
                    add_node(str(n.get("id")), n.get("label"), n.get("type") or "other")
            for e in (rec.get("edges") or []):
                if isinstance(e, dict):
                    add_edge(str(e.get("source")), str(e.get("target")), e.get("kind"))
        else:
            gid = _rec_id(rec, i)
            add_node(gid, rec.get("label") or rec.get("name") or rec.get("id"), "concept")

    # 4) WorldState / Canon → faction / location 节点 + members 边
    for comp, ntype in (("WorldState.yaml", "location"), ("Canon.yaml", "concept")):
        for i, rec in enumerate(_load_nkb(project_root, comp)):
            if not isinstance(rec, dict):
                continue
            rid = _rec_id(rec, i)
            add_node(rid, rec.get("name") or rec.get("id"), ntype)
            for mem in (rec.get("members") or []):
                add_edge(rid, str(mem) if mem is not None else None, "member")

    return {"nodes": list(nodes.values()), "edges": edges}


# ── HTML 渲染 ───────────────────────────────────────────
def render_html(graph, title="NKB 知识图谱"):
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    n = len(nodes)
    W, H = 900, 600
    # 圆周布局
    import math
    cx, cy = W / 2, H / 2
    r = min(W, H) / 2 - 60
    pos = {}
    for i, nd in enumerate(nodes):
        ang = 2 * math.pi * i / n if n else 0
        pos[nd["id"]] = (cx + r * math.cos(ang), cy + r * math.sin(ang)) if n else (cx, cy)
    svg_parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d">' % (W, H)]
    svg_parts.append('<rect width="100%%" height="100%%" fill="#fafafa"/>')
    # edges
    for e in edges:
        a = pos.get(e.get("source"))
        b = pos.get(e.get("target"))
        if a and b:
            svg_parts.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#bbb" stroke-width="1"/>'
                              % (a[0], a[1], b[0], b[1]))
    # nodes
    for nd in nodes:
        p = pos.get(nd["id"])
        if not p:
            continue
        color = _TYPE_COLOR.get(nd.get("type"), "#999999")
        svg_parts.append('<circle cx="%.1f" cy="%.1f" r="14" fill="%s" stroke="#333" stroke-width="1"/>'
                          % (p[0], p[1], color))
        lbl = (nd.get("label") or nd["id"])
        if len(lbl) > 10:
            lbl = lbl[:10] + "…"
        svg_parts.append('<text x="%.1f" y="%.1f" font-size="11" text-anchor="middle" dy="28">%s</text>'
                          % (p[0], p[1], _esc(lbl)))
    svg_parts.append('</svg>')
    svg = "".join(svg_parts)
    legend = "".join(
        '<span style="color:%s">●</span> %s ' % (c, t)
        for t, c in _TYPE_COLOR.items())
    html = (
        "<!DOCTYPE html><html lang=\"zh\"><head><meta charset=\"utf-8\">"
        "<title>%s</title></head><body style=\"font-family:sans-serif;margin:24px\">"
        "<h2>%s</h2>"
        "<p>节点 %d · 边 %d</p>"
        "<div>图例：%s</div>"
        "<div>%s</div>"
        "</body></html>" % (_esc(title), _esc(title), n, len(edges), legend, svg)
    )
    return html


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ── doctor 自检 ─────────────────────────────────────────
def govern(project_root, write=False):
    graph = build_graph(project_root)
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    node_ids = {nd["id"] for nd in nodes}
    caution = []
    dangling = 0
    for e in edges:
        if e.get("source") not in node_ids or e.get("target") not in node_ids:
            dangling += 1
    if dangling:
        caution.append("悬空边 %d 条（引用不存在的节点）" % dangling)
    if nodes and len(edges) == 0:
        caution.append("图谱有 %d 节点但无边（孤立节点）" % len(nodes))
    decision = "caution" if caution else "proceed"
    health = 100 - 10 * len(caution)
    report = {
        "meta": {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "component": "graph-viz",
            "version": "1.0.0",
            "project_root": project_root,
        },
        "request": {},
        "response": {"nodes": len(nodes), "edges": len(edges)},
        "decision": decision,
        "gate": {"decision": decision, "reasons": caution},
        "composite": {"health": health},
    }
    if write:
        out_dir = os.path.join(project_root, "analysis", "graph")
        os.makedirs(out_dir, exist_ok=True)
        idx = 1
        for fn in os.listdir(out_dir):
            if fn.startswith("GRAPH-") and fn.endswith(".yaml"):
                try:
                    idx = max(idx, int(fn[6:-5]) + 1)
                except Exception:
                    pass
        with open(os.path.join(out_dir, "GRAPH-%02d.yaml" % idx), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    return report


# ── CLI ─────────────────────────────────────────────────
def _next_graph_file(out_dir, prefix, ext):
    os.makedirs(out_dir, exist_ok=True)
    idx = 1
    for fn in os.listdir(out_dir):
        if fn.startswith(prefix) and fn.endswith(ext):
            try:
                idx = max(idx, int(fn[len(prefix):-len(ext)]) + 1)
            except Exception:
                pass
    return os.path.join(out_dir, "%s%02d%s" % (prefix, idx, ext))


def main():
    ap = argparse.ArgumentParser(prog="graph-viz", description="Phase 3-5 图谱可视化")
    sub = ap.add_subparsers(dest="cmd")

    pb = sub.add_parser("build", help="从 NKB 构建 graph JSON（nodes/edges）")
    pb.add_argument("--project-root", required=True)
    pb.add_argument("--write", action="store_true", help="写回 analysis/graph/GRAPH-NN.json")

    pr = sub.add_parser("render", help="渲染 HTML/SVG")
    pr.add_argument("--project-root", required=True)
    pr.add_argument("--input", default=None, help="指定 GRAPH json；省略则自动 build")
    pr.add_argument("--write", action="store_true", help="写回 analysis/graph/GRAPH-NN.html")

    pv = sub.add_parser("validate", help="doctor 自检（图谱健康提示）")
    pv.add_argument("--project-root", required=True)

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        sys.exit(2)

    if args.cmd == "build":
        g = build_graph(args.project_root)
        if args.write:
            p = _next_graph_file(os.path.join(args.project_root, "analysis", "graph"),
                                 "GRAPH-", ".json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"schema_version": "1.0.0", "graph": g}, f,
                          ensure_ascii=False, indent=2)
            print(json.dumps({"written": p, "nodes": len(g["nodes"]),
                             "edges": len(g["edges"])}, ensure_ascii=False))
        else:
            print(json.dumps({"nodes": len(g["nodes"]), "edges": len(g["edges"])},
                            ensure_ascii=False))
        sys.exit(0)

    if args.cmd == "render":
        if args.input:
            with open(args.input, "r", encoding="utf-8") as f:
                data = json.load(f)
            g = data.get("graph", data)
        else:
            g = build_graph(args.project_root)
        html = render_html(g)
        if args.write:
            p = _next_graph_file(os.path.join(args.project_root, "analysis", "graph"),
                                 "GRAPH-", ".html")
            with open(p, "w", encoding="utf-8") as f:
                f.write(html)
            print(json.dumps({"written": p}, ensure_ascii=False))
        else:
            print(html)
        sys.exit(0)

    if args.cmd == "validate":
        rep = govern(args.project_root, write=False)
        print(json.dumps(rep["gate"], ensure_ascii=False, indent=2))
        sys.exit(1 if rep["gate"]["decision"] == "block" else 0)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""冲击分析仪（Impact Analyzer）—— Phase 2 系统 #1。

拼接 NKB 关系图 + 任务依赖 + 章节→实体索引 + 伏笔关联，
对变更目标做 BFS 爆炸半径推算，输出影响报告 + 门禁(proceed/caution/block)。

CLI：platform impact --project-root <root> <analyze|from-task|index|show> ...
"""
import os
import sys
import re
import datetime
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _gov
import audit_log

MAX_HOPS = 3


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _safe_load(p):
    try:
        return _gov.load_yaml(p)
    except Exception:
        return None


def _rel(project_root, p):
    return os.path.relpath(p, project_root)


# ───────────────────────── NKB 实体 ─────────────────────────
def _load_nkb_entities(project_root):
    ents = []
    nkb_dir = os.path.join(project_root, "NKB")
    if not os.path.isdir(nkb_dir):
        return ents
    for fn in sorted(os.listdir(nkb_dir)):
        if not fn.endswith(".yaml") or fn in ("NKB.md", "Derived.yaml"):
            continue
        d = _safe_load(os.path.join(nkb_dir, fn))
        if not isinstance(d, dict):
            continue
        kind = fn[:-5]
        recs = d.get("records")
        if not isinstance(recs, list):
            continue
        for r in recs:
            if not isinstance(r, dict):
                continue
            nid = r.get("id") or r.get("name")
            name = r.get("name") or nid
            if nid:
                ents.append({"id": "%s/%s" % (kind, nid), "name": name, "kind": kind})
    return ents


# ───────────────────────── 图构建 ─────────────────────────
def _build_graph(project_root, name_to_id):
    adj = {}

    def add(a, b, rel):
        if not a or not b or a == b:
            return
        adj.setdefault(a, []).append((b, rel))
        adj.setdefault(b, []).append((a, rel))

    nkb_dir = os.path.join(project_root, "NKB")
    # G1: NKB 关系字段
    if os.path.isdir(nkb_dir):
        for fn in sorted(os.listdir(nkb_dir)):
            if not fn.endswith(".yaml") or fn in ("NKB.md", "Derived.yaml"):
                continue
            d = _safe_load(os.path.join(nkb_dir, fn))
            if not isinstance(d, dict):
                continue
            kind = fn[:-5]
            for r in (d.get("records") or []):
                if not isinstance(r, dict):
                    continue
                rid = "%s/%s" % (kind, r.get("id") or r.get("name"))
                for fld in ("relations", "related", "affiliation", "affiliations",
                            "participants", "members", "targets", "allies", "enemies"):
                    for v in _as_list(r.get(fld)):
                        nb = _norm_ref(v, name_to_id)
                        if nb:
                            add(rid, nb, fld)
    # G2: 任务依赖 + 任务→章节
    tasks_dir = os.path.join(project_root, "tasks")
    if os.path.isdir(tasks_dir):
        try:
            import task_engine
        except Exception:
            task_engine = None
        if task_engine:
            for st in ("backlog", "ready", "claimed", "running", "submitted",
                       "reviewing", "passed", "completed", "failed"):
                sd = os.path.join(tasks_dir, st)
                if not os.path.isdir(sd):
                    continue
                for fn in os.listdir(sd):
                    if not fn.endswith(".yaml"):
                        continue
                    tid = fn[:-5]
                    _, td = task_engine.load_task(project_root, tid)
                    t = (td or {}).get("task", {}) if td else {}
                    tnode = "task/%s" % tid
                    for dep in (t.get("dependencies") or []):
                        add(tnode, "task/%s" % dep, "depends_on")
                    cref = t.get("chapter_ref")
                    if cref:
                        add(tnode, "chapter/%s" % cref, "targets_chapter")
    # G4: 伏笔关联
    fs = os.path.join(nkb_dir, "Foreshadow.yaml") if os.path.isdir(nkb_dir) else None
    if fs and os.path.isfile(fs):
        d = _safe_load(fs)
        for r in (d.get("records") or []):
            if not isinstance(r, dict):
                continue
            fid = "foreshadow/%s" % (r.get("id") or r.get("name"))
            for fld in ("targets", "target", "related"):
                for v in _as_list(r.get(fld)):
                    nb = _norm_ref(v, name_to_id)
                    if nb:
                        add(fid, nb, fld)
    # G5: 章节→实体索引
    idx = _load_index(project_root)
    for item in (idx.get("index") or []):
        ch = "chapter/%s" % _chapter_key(item.get("chapter"))
        for eid in (item.get("entities") or []):
            add(ch, eid, "references")
    return adj


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def _norm_ref(v, name_to_id):
    if isinstance(v, dict):
        v = v.get("id") or v.get("name")
    if v is None:
        return None
    s = str(v)
    if s in name_to_id:
        return name_to_id[s]
    if "/" in s:
        return s
    return None


def _load_index(project_root):
    p = os.path.join(project_root, "analysis", "index", "chapter-entities.yaml")
    if not os.path.isfile(p):
        return {}
    return _safe_load(p) or {}


# ───────────────────────── 索引构建 ─────────────────────────
def render_index(project_root):
    ents = _load_nkb_entities(project_root)
    index = []
    scan_dirs = ["approved", "txt", "chapters", "chapters/drafts", "drafts"]
    for sd in scan_dirs:
        base = os.path.join(project_root, sd)
        if not os.path.isdir(base):
            continue
        for root, _, files in os.walk(base):
            for fn in files:
                if not fn.endswith((".txt", ".md", ".yaml")):
                    continue
                fp = os.path.join(root, fn)
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        text = f.read()
                except Exception:
                    continue
                matched = []
                for e in ents:
                    nm = e["name"]
                    if nm and nm in text:
                        matched.append(e["id"])
                if matched:
                    cid = _chapter_id(fn)
                    index.append({"chapter": cid, "path": _rel(project_root, fp),
                                   "entities": matched})
    out = {"meta": {"built_at": _now(), "project": _project_id(project_root)},
           "index": index}
    d = os.path.join(project_root, "analysis", "index")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "chapter-entities.yaml"), "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(out))
    return out


def _chapter_id(filename):
    stem = os.path.splitext(os.path.basename(filename))[0]
    m = re.search(r"(\d+)", stem)
    return m.group(1) if m else stem


def _chapter_key(cid):
    """归一化章号：'042'/42/'7' 一律 -> 整数字符串 '42'/'7'。

    规避 _yaml_lite 把前导零标量 042 重载成 int 42 的歧义，
    使「种子节点 / 索引节点 / 已发布章节判定」三处都统一为整数字符串，
    不再出现 'chapter/042'(seed) 与 'chapter/42'(index) 失配导致 block 失效。
    """
    try:
        return str(int(cid))
    except (ValueError, TypeError):
        return str(cid)


# ───────────────────────── 分析 ─────────────────────────
def _resolve_seed(target_type, target_id):
    target_id = str(target_id)
    if target_type == "chapter":
        return "chapter/%s" % _chapter_key(target_id)
    if target_type == "nkb":
        return target_id if "/" in target_id else "nkb/%s" % target_id
    if target_type in ("outline", "world", "asset"):
        return "%s/%s" % (target_type, target_id)
    return target_id


def analyze(project_root, target_type, target_id, diff_summary="", proposed_by="unknown",
            model="unknown", max_hops=MAX_HOPS, write=True):
    if target_type == "chapter":
        target_id = _chapter_key(target_id)
    ents = _load_nkb_entities(project_root)
    name_to_id = {}
    for e in ents:
        name_to_id[e["name"]] = e["id"]
        name_to_id[e["id"]] = e["id"]
    adj = _build_graph(project_root, name_to_id)
    seed = _resolve_seed(target_type, target_id)
    affected = {}
    visited = {seed: 0}
    queue = [(seed, 0)]
    while queue:
        node, hop = queue.pop(0)
        if hop >= max_hops:
            continue
        for (nb, rel) in adj.get(node, []):
            if nb not in visited:
                visited[nb] = hop + 1
                affected[nb] = {"id": nb, "relation": rel, "hops": hop + 1}
                queue.append((nb, hop + 1))
    affected_list = []
    for nid, info in affected.items():
        kind, crit = _classify_node(project_root, nid)
        hops = info["hops"]
        sev = "direct" if hops <= 1 else ("indirect" if hops == 2 else "cascade")
        affected_list.append({"kind": kind, "id": nid, "relation": info["relation"],
                              "severity": sev, "criticality": crit, "evidence": ""})
    decision, reasons = _decide(project_root, affected_list, seed)
    report = {
        "meta": {"analyzer": "impact-analyzer", "analyzed_at": _now(),
                 "project": _project_id(project_root), "change_ref": ""},
        "change": {"target_type": target_type, "target_id": str(target_id),
                   "diff_summary": diff_summary, "proposed_by": proposed_by},
        "affected": affected_list,
        "gate": {"decision": decision, "reasons": reasons},
        "recommendations": _recommend(affected_list, decision),
    }
    if write:
        _write_report(project_root, report, target_type, target_id, proposed_by, model)
    return report


def analyze_task(project_root, task_id, **kw):
    import task_engine
    _, data = task_engine.load_task(project_root, task_id)
    if not data:
        raise FileNotFoundError(task_id)
    t = data["task"]
    tt = t.get("type")
    target = None
    if t.get("chapter_ref"):
        target = ("chapter", str(t["chapter_ref"]))
    elif (t.get("target") or {}).get("type"):
        target = (t["target"]["type"], t["target"]["id"])
    elif tt == "nkb_update":
        target = ("nkb", t.get("nkb_ref") or (t.get("inputs") or {}).get("nkb_id") or task_id)
    if not target:
        target = ("nkb", task_id)
    return analyze(project_root, target[0], target[1],
                   proposed_by=(t.get("owner") or "unknown"), **kw)


def _classify_node(project_root, nid):
    if nid.startswith("chapter/"):
        crit = "high" if _is_approved_chapter(project_root, nid) else "low"
        return "chapter", crit
    if nid.startswith("task/"):
        return "task", "low"
    if nid.startswith("foreshadow/"):
        return "foreshadow", "medium"
    return "nkb", "low"


def _is_approved_chapter(project_root, nid):
    cid = nid[len("chapter/"):]
    ap = os.path.join(project_root, "approved")
    if not os.path.isdir(ap):
        return False
    for root, _, files in os.walk(ap):
        for fn in files:
            if _chapter_key(_chapter_id(fn)) == _chapter_key(cid):
                return True
    return False


def _decide(project_root, affected_list, seed):
    reasons = []
    if seed.startswith("chapter/") and _is_approved_chapter(project_root, seed):
        reasons.append("变更目标为已发布章节 %s" % seed)
    for a in affected_list:
        if a["kind"] == "chapter" and a["criticality"] == "high":
            reasons.append("影响已发布章节 %s" % a["id"])
    if reasons:
        return "block", reasons
    high = [a for a in affected_list if a["criticality"] == "high"]
    if high:
        return "caution", ["存在高优先级受影响项：%s" % ", ".join(a["id"] for a in high)]
    if affected_list:
        return "caution", ["存在受影响项（均非高优）：%s" % ", ".join(a["id"] for a in affected_list[:5])]
    return "proceed", ["无外溢影响"]


def _recommend(affected_list, decision):
    recs = []
    if decision == "block":
        for a in affected_list:
            if a["kind"] == "chapter" and a["criticality"] == "high":
                recs.append({"action": "human_review", "target": a["id"],
                             "detail": "已发布章节受影响，需 human_gate 放行"})
    elif decision == "caution":
        for a in affected_list:
            recs.append({"action": "create_task", "target": a["id"],
                         "detail": "建议同步更新（%s）" % a["severity"]})
    return recs


def _project_id(project_root):
    p = os.path.join(project_root, "project.yaml")
    if os.path.isfile(p):
        d = _safe_load(p)
        if isinstance(d, dict):
            return str((d.get("project") or {}).get("id") or d.get("id") or os.path.basename(project_root))
    return os.path.basename(project_root)


def _write_report(project_root, report, target_type, target_id, proposed_by, model):
    d = os.path.join(project_root, "analysis", "impact")
    os.makedirs(d, exist_ok=True)
    seq = 1
    prefix = "IMP-%s-%s" % (target_type, str(target_id).replace("/", "-"))
    while os.path.isfile(os.path.join(d, "%s-%02d.yaml" % (prefix, seq))):
        seq += 1
    rid = "%s-%02d" % (prefix, seq)
    report["meta"]["report_id"] = rid
    report["meta"]["change_ref"] = rid
    p = os.path.join(d, rid + ".yaml")
    with open(p, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(report))
    audit_log.record(project_root, "impact_analysis", agent=proposed_by, model=model,
                     files=[_rel(project_root, p)], result="success",
                     detail="gate=%s target=%s/%s" % (report["gate"]["decision"], target_type, target_id))
    return rid


# ───────────────────────── CLI ─────────────────────────
def _print_report(rep):
    g = rep.get("gate", {})
    print("门禁：%s" % g.get("decision", "?"))
    for r in g.get("reasons", []):
        print("  理由：%s" % r)
    print("受影响项：%d" % len(rep.get("affected", [])))
    for a in rep.get("affected", []):
        print("  - [%s] %s  (%s/%s)  via %s" % (a["severity"], a["id"], a["kind"], a["criticality"], a["relation"]))
    for rc in rep.get("recommendations", []):
        print("  建议：%s -> %s" % (rc["action"], rc["target"]))


def main():
    ap = argparse.ArgumentParser(prog="impact", description="冲击分析仪")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("verb", choices=["analyze", "from-task", "index", "show"])
    ap.add_argument("--target-type", default="nkb")
    ap.add_argument("--target-id", default=None)
    ap.add_argument("--reason", default="")
    ap.add_argument("--task", default=None)
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    if args.verb == "analyze":
        if not args.target_id:
            ap.error("analyze requires --target-id")
        rep = analyze(args.project_root, args.target_type, args.target_id, diff_summary=args.reason)
        _print_report(rep)
    elif args.verb == "from-task":
        if not args.task:
            ap.error("from-task requires --task")
        rep = analyze_task(args.project_root, args.task, diff_summary=args.reason)
        _print_report(rep)
    elif args.verb == "index":
        idx = render_index(args.project_root)
        print("✓ 索引构建：%d 章节条目" % len(idx.get("index") or []))
    elif args.verb == "show":
        if not args.report:
            ap.error("show requires --report")
        p = os.path.join(args.project_root, "analysis", "impact", args.report)
        if os.path.isfile(p):
            print(_gov.dump_block(_safe_load(p)))
        else:
            print("# 报告不存在: %s" % args.report)


if __name__ == "__main__":
    main()

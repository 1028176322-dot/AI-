# -*- coding: utf-8 -*-
"""
资产管理引擎（Asset Management）· Phase 2 #5

对项目内容资产（章节 / NKB / sources / artifacts / 参考 / 图片）做体检：
  AT1 inventory 资产清单
  AT2 orphan 孤儿资产
  AT3 missing 缺失资产（引用断裂 → block）
  AT4 duplicate 重复资产
  AT5 dependency 依赖图
  AT6 health 健康分

门禁：报告式（missing→block→doctor FAIL；orphan/duplicate→caution；不阻断 task submit）。
复用 memory_governor 的模式（_gov / audit_log / _yaml_lite），相似度 helper 内联以保持独立。
"""
import os
import re
import sys
import argparse
import datetime

import _gov
import audit_log


# ─────────────────────── 共享 helper（内联，保持工具独立） ───────────────────────
def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _safe_load(p):
    try:
        return _gov.load_yaml(p)
    except Exception:
        return None


def _rel(root, p):
    return os.path.relpath(p, root)


def _normalize(text):
    if not text:
        return ""
    s = text.lower()
    s = re.sub(r"[^\w\u4e00-\u9fff]", "", s)
    return s


def _bigrams(s):
    return set(s[i:i + 2] for i in range(len(s) - 1)) if len(s) > 1 else set(s)


def _similarity(a, b):
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    ba, bb = _bigrams(na), _bigrams(nb)
    if not ba or not bb:
        return 1.0 if na == nb else 0.0
    inter = len(ba & bb)
    union = len(ba | bb)
    return inter / union if union else 0.0


# 引用路径提取（轻量，不解析语义）
_REF_RE = re.compile(
    r'(图片/[^\s"\')]+|'
    r'参考资料/[^\s"\')]+|'
    r'\./sources/[^\s"\')]+|'
    r'\.\./sources/[^\s"\')]+|'
    r'\./NKB/[^\s"\')]+|'
    r'[A-Za-z0-9_\-./]+\.md)'
)


def _load_cfg():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "registry", "asset.yaml")
    d = _safe_load(p)
    if not isinstance(d, dict):
        d = {}
    ad = d.get("asset_dirs", {}) or {}
    rc = d.get("reference_check", {}) or {}
    orph = d.get("orphan", {}) or {}
    ded = d.get("dedup", {}) or {}
    gate = d.get("gate", {}) or {}
    return {
        "asset_dirs": ad,
        "ref_enabled": bool(rc.get("enabled", True)),
        "scan_dirs": rc.get("scan_dirs", ["txt", "NKB", "sources"]),
        "ref_prefixes": rc.get("ref_prefixes", []),
        "nkb_ref_fields": rc.get("nkb_ref_fields", ["source", "ref", "references"]),
        "inbox_as_orphan": bool(orph.get("inbox_as_orphan", True)),
        "artifacts_orphan": bool(orph.get("artifacts_unreferenced_as_orphan", True)),
        "sim_threshold": float(ded.get("similarity_threshold", 0.85)),
        "same_type_only": bool(ded.get("same_type_only", True)),
        "fatal_penalty": int(gate.get("fatal_penalty", 40)),
        "caution_penalty": int(gate.get("caution_penalty", 5)),
    }


def _resolve_dirs(project_root, cfg):
    paths = {}
    pp = os.path.join(project_root, "project.yaml")
    if os.path.isfile(pp):
        pd = _safe_load(pp) or {}
        paths = (pd.get("paths") or {})

    def _d(key, default):
        rel = paths.get(key, cfg["asset_dirs"].get(key, default))
        return os.path.normpath(os.path.join(project_root, rel))

    ad = cfg["asset_dirs"]
    return {
        "chapters": _d("chapters", "./txt"),
        "nkb": _d("nkb", "./NKB"),
        "artifacts": _d("artifacts", "./artifacts"),
        "sources": os.path.normpath(os.path.join(project_root, ad.get("sources", "./sources"))),
        "references": os.path.normpath(os.path.join(project_root, ad.get("references", "./参考资料"))),
        "images": os.path.normpath(os.path.join(project_root, ad.get("images", "./图片"))),
        "outline": os.path.normpath(os.path.join(
            project_root, paths.get("outline", ad.get("outline", "./大纲_1000章总体规划.md")))),
    }


def _list_files(root_dir, exts=None):
    out = []
    if not os.path.isdir(root_dir):
        return out
    for dp, _, fns in os.walk(root_dir):
        for fn in fns:
            if exts and not fn.lower().endswith(tuple(exts)):
                continue
            out.append(os.path.join(dp, fn))
    out.sort()
    return out


def _read_text(p, cache):
    if p in cache:
        return cache[p]
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as fh:
            c = fh.read()
    except Exception:
        c = ""
    cache[p] = c
    return c


def _resolve_ref(ref, sf, project_root):
    """解析引用路径：项目根级资产目录（图片/参考资料/sources/NKB）一律相对项目根，
    其余（如 .md 章节间引用）相对当前文件目录。"""
    dn = os.path.dirname(sf)
    if (ref.startswith("图片/") or ref.startswith("参考资料/")
            or ref.startswith("sources/") or ref.startswith("./sources/")
            or ref.startswith("../sources/") or ref.startswith("NKB/")
            or ref.startswith("./NKB/")):
        r = ref
        if r.startswith("./"):
            r = r[2:]
        elif r.startswith("../"):
            r = r[3:]
        return os.path.normpath(os.path.join(project_root, r))
    return os.path.normpath(os.path.join(dn, ref))


def _content_for_dup(f, t, cache):
    """重复检测的内容：NKB 去除模板头部与注释/空行（schema_version/project_id/
    project/records + 注释），仅留实质记录，避免空组件模板相同误判重复。"""
    c = _read_text(f, cache)
    if t == "nkb":
        lines = []
        for ln in c.splitlines():
            s = ln.strip()
            if not s or s.startswith("#"):
                continue
            if re.match(r'^\s*(schema_version|project_id|project|records):', ln):
                continue
            lines.append(ln)
        return "\n".join(lines).strip()
    return c


def govern(project_root, write=True, proposed_by="unknown", model="unknown"):
    """对项目内容资产做体检，返回 report dict。"""
    cfg = _load_cfg()
    dirs = _resolve_dirs(project_root, cfg)

    # ── AT1 inventory ──
    ch_files = _list_files(dirs["chapters"], exts=[".md", ".txt"])
    nkb_files = _list_files(dirs["nkb"], exts=[".yaml"])
    src_files = _list_files(dirs["sources"])
    art_files = [f for f in _list_files(dirs["artifacts"]) if os.path.basename(f).lower() != "readme.md"]
    ref_files = _list_files(dirs["references"])
    img_files = _list_files(dirs["images"])
    outline_files = [dirs["outline"]] if os.path.isfile(dirs["outline"]) else []

    all_assets = []
    for f in ch_files:
        all_assets.append((f, "chapter", os.path.getsize(f), os.path.getmtime(f)))
    for f in nkb_files:
        all_assets.append((f, "nkb", os.path.getsize(f), os.path.getmtime(f)))
    for f in src_files:
        all_assets.append((f, "source", os.path.getsize(f), os.path.getmtime(f)))
    for f in art_files:
        all_assets.append((f, "artifact", os.path.getsize(f), os.path.getmtime(f)))
    for f in ref_files:
        all_assets.append((f, "reference", os.path.getsize(f), os.path.getmtime(f)))
    for f in img_files:
        all_assets.append((f, "image", os.path.getsize(f), os.path.getmtime(f)))
    for f in outline_files:
        all_assets.append((f, "outline", os.path.getsize(f), os.path.getmtime(f)))

    by_type = {}
    for f, t, sz, mt in all_assets:
        b = by_type.setdefault(t, {"count": 0, "bytes": 0, "latest": 0})
        b["count"] += 1
        b["bytes"] += sz
        b["latest"] = max(b["latest"], mt)
    inventory = {}
    for t, v in by_type.items():
        inventory[t] = {
            "count": v["count"],
            "bytes": v["bytes"],
            "latest_mtime": (datetime.datetime.fromtimestamp(v["latest"]).isoformat(timespec="seconds")
                             if v["latest"] else None),
        }

    text_cache = {}

    # NKB record 引用收集（source/ref/references 字段）
    nkb_refs = []
    for nf in nkb_files:
        d = _safe_load(nf)
        if not isinstance(d, dict):
            continue
        for rec in (d.get("records") or []):
            if not isinstance(rec, dict):
                continue
            for fld in cfg["nkb_ref_fields"]:
                val = rec.get(fld)
                if isinstance(val, str) and val.strip():
                    nkb_refs.append((nf, val.strip()))
                elif isinstance(val, list):
                    for v in val:
                        if isinstance(v, str) and v.strip():
                            nkb_refs.append((nf, v.strip()))

    # ── AT3 missing：NKB ref 路径不存在 ──
    missing = []
    for nf, ref in nkb_refs:
        cand = _resolve_ref(ref, nf, project_root)
        if cand is None or not os.path.exists(cand):
            missing.append({"from": _rel(project_root, nf), "ref": ref,
                            "resolved": (_rel(project_root, cand) if cand else "<unresolved>")})

    # ── AT3 missing：章节/NKB/源 文本引用路径不存在 ──
    scan_files = ch_files + nkb_files + src_files
    for sf in scan_files:
        txt = _read_text(sf, text_cache)
        for m in _REF_RE.finditer(txt):
            ref = m.group(1).strip("`").rstrip("。，,；;")
            cand = _resolve_ref(ref, sf, project_root)
            if cand is None or not os.path.exists(cand):
                missing.append({"from": _rel(project_root, sf), "ref": ref,
                                "resolved": (_rel(project_root, cand) if cand else "<unresolved>")})

    # ── AT2 orphan：inbox 未归类 ──
    orphans = []
    inbox_dir = os.path.join(dirs["sources"], "inbox")
    if cfg["inbox_as_orphan"] and os.path.isdir(inbox_dir):
        for f in _list_files(inbox_dir):
            if os.path.basename(f).startswith("."):
                continue
            orphans.append({"path": _rel(project_root, f), "reason": "inbox 未归类"})

    # ── AT2 orphan：artifacts 未被任何文本引用 ──
    if cfg["artifacts_orphan"] and art_files:
        corpus = ""
        for sf in ch_files + nkb_files + src_files:
            corpus += _read_text(sf, text_cache) + "\n"
        for af in art_files:
            rel = _rel(project_root, af)
            base = os.path.basename(af)
            if base not in corpus and rel not in corpus:
                orphans.append({"path": rel, "reason": "artifacts 未被任何文本引用"})

    # ── AT4 duplicate：同类型内相似度 ──
    duplicates = []
    groups = {}
    for f, t, sz, mt in all_assets:
        groups.setdefault(t, []).append(f)
    for t, files in groups.items():
        for i in range(len(files)):
            for j in range(i + 1, len(files)):
                ca = _content_for_dup(files[i], t, text_cache)
                cb = _content_for_dup(files[j], t, text_cache)
                if not ca and not cb:
                    continue
                sim = _similarity(ca, cb)
                if sim >= cfg["sim_threshold"]:
                    duplicates.append({"a": _rel(project_root, files[i]),
                                       "b": _rel(project_root, files[j]),
                                       "type": t, "similarity": round(sim, 3)})

    # ── AT5 dependency 依赖图 ──
    dep_graph = []
    for nf, ref in nkb_refs:
        cand = os.path.normpath(os.path.join(os.path.dirname(nf), ref))
        if os.path.exists(cand):
            dep_graph.append({"from": _rel(project_root, nf),
                              "to": _rel(project_root, cand), "kind": "nkb_ref"})
    for sf in scan_files:
        txt = _read_text(sf, text_cache)
        for m in _REF_RE.finditer(txt):
            ref = m.group(1).strip("`").rstrip("。，,；;")
            cand = _resolve_ref(ref, sf, project_root)
            if cand and os.path.exists(cand):
                dep_graph.append({"from": _rel(project_root, sf),
                                  "to": _rel(project_root, cand), "kind": "text_ref"})

    # ── signals ──
    signals = [
        {"name": "AT1_inventory", "ok": True,
         "detail": "%d 资产 / %d 类型" % (len(all_assets), len(inventory))},
        {"name": "AT2_orphan", "ok": not orphans, "detail": "%d 孤儿" % len(orphans)},
        {"name": "AT3_missing", "ok": not missing, "detail": "%d 缺失" % len(missing)},
        {"name": "AT4_duplicate", "ok": not duplicates, "detail": "%d 对重复" % len(duplicates)},
        {"name": "AT5_dependency", "ok": True, "detail": "%d 条边" % len(dep_graph)},
        {"name": "AT6_health", "ok": True, "detail": "健康分计算"},
    ]

    fatal = bool(missing)
    caution_count = len(orphans) + len(duplicates)
    health = max(0, 100 - (cfg["fatal_penalty"] if fatal else 0)
                 - caution_count * cfg["caution_penalty"])

    if fatal:
        decision = "block"
    elif caution_count > 0:
        decision = "caution"
    else:
        decision = "proceed"

    reasons = []
    for m in missing:
        reasons.append("MISSING %s 引用 %s (解析=%s)" % (m["from"], m["ref"], m["resolved"]))
    for o in orphans:
        reasons.append("ORPHAN %s: %s" % (o["path"], o["reason"]))
    for d in duplicates:
        reasons.append("DUP %s ~ %s (sim=%.2f)" % (d["a"], d["b"], d["similarity"]))

    recs = []
    if missing:
        recs.append("修复引用断裂：补回缺失资产或修正引用路径")
    if orphans:
        recs.append("处理孤儿资产：归类 inbox 事实入 NKB，或删除无用 artifacts")
    if duplicates:
        recs.append("合并重复资产，保留权威版本")

    report = {
        "meta": {"scorer": "asset-manager", "scored_at": _now(),
                 "project": os.path.basename(project_root)},
        "target": {"target_type": "asset",
                   "project_root": os.path.basename(project_root),
                   "asset_summary": inventory},
        "signals": signals,
        "composite": {"health": health},
        "fatal": fatal,
        "gate": {"decision": decision, "reasons": reasons},
        "orphans": orphans,
        "missing": missing,
        "duplicates": duplicates,
        "dependency_graph": dep_graph,
        "recommendations": recs,
    }

    if write:
        _write_report(project_root, report, proposed_by, model)
    return report


def _write_report(project_root, report, proposed_by, model):
    d = os.path.join(project_root, "analysis", "asset")
    os.makedirs(d, exist_ok=True)
    seq = 1
    while os.path.isfile(os.path.join(d, "AST-%02d.yaml" % seq)):
        seq += 1
    rid = "AST-%02d" % seq
    report["meta"]["report_id"] = rid
    p = os.path.join(d, rid + ".yaml")
    with open(p, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(report))
    audit_log.record(project_root, "asset_mgmt", agent=proposed_by, model=model,
                     files=[_rel(project_root, p)], result="success",
                     detail="gate=%s" % report["gate"]["decision"])
    return rid


def _print_report(rep):
    g = rep.get("gate", {})
    comp = rep.get("composite", {})
    print("门禁：%s" % g.get("decision", "?"))
    print("健康分：%s" % comp.get("health"))
    print("资产清单：")
    for t, v in rep.get("target", {}).get("asset_summary", {}).items():
        print("  %-10s %d 文件 / %d 字节" % (t, v["count"], v["bytes"]))
    print("信号：")
    for s in rep.get("signals", []):
        flag = "OK " if s.get("ok") else "FAIL"
        print("  [%s] %s | %s" % (flag, s["name"], s.get("detail")))
    for r in g.get("reasons", []):
        print("  理由：%s" % r)
    for o in rep.get("orphans", []):
        print("  孤儿：%s (%s)" % (o["path"], o["reason"]))
    for m in rep.get("missing", []):
        print("  缺失：%s -> %s" % (m["from"], m["ref"]))
    for d in rep.get("duplicates", []):
        print("  重复：%s ~ %s (sim=%.2f, %s)" % (d["a"], d["b"], d["similarity"], d["type"]))
    for rc in rep.get("recommendations", []):
        print("  建议：%s" % rc)


def main():
    p = argparse.ArgumentParser(prog="asset_manager")
    p.add_argument("--project-root", required=True)
    p.add_argument("cmd", choices=["inventory", "report", "orphans", "missing", "dedup"])
    p.add_argument("--no-write", action="store_true")
    p.add_argument("--proposed-by", default="unknown")
    p.add_argument("--model", default="unknown")
    args = p.parse_args()
    rep = govern(args.project_root, write=not args.no_write,
                 proposed_by=args.proposed_by, model=args.model)
    if args.cmd == "inventory":
        for t, v in rep["target"]["asset_summary"].items():
            print("%s: %d 文件 / %d 字节" % (t, v["count"], v["bytes"]))
    elif args.cmd == "orphans":
        for o in rep["orphans"]:
            print("%s (%s)" % (o["path"], o["reason"]))
        print("孤儿数：%d" % len(rep["orphans"]))
    elif args.cmd == "missing":
        for m in rep["missing"]:
            print("%s -> %s" % (m["from"], m["ref"]))
        print("缺失数：%d" % len(rep["missing"]))
    elif args.cmd == "dedup":
        for d in rep["duplicates"]:
            print("%s ~ %s (sim=%.2f, %s)" % (d["a"], d["b"], d["similarity"], d["type"]))
        print("重复对数：%d" % len(rep["duplicates"]))
    else:
        _print_report(rep)
    sys.exit(0 if rep["gate"]["decision"] != "block" else 1)


if __name__ == "__main__":
    main()

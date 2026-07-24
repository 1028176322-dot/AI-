#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""market.py — Phase 3-6 市场分析（Market Analysis）

摄取 sources/research/market/*.yaml 市场信号 → 按 genre 机会打分 → 产出 market brief；
可选写入 NKB Market 组件（市场事实）。不替代创作决策。零依赖复用 _yaml_lite/_gov。
"""
import os
import sys
import json
import argparse
import datetime
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _yaml_lite
import _gov

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

_DEFAULT_WEIGHTS = {"trend_score": 0.4, "competition": 0.3, "reader_demand": 0.3}
_WEIGHT_KEYS = ("trend_score", "competition", "reader_demand")


def _market_dir(project_root):
    return os.path.join(project_root, "sources", "research", "market")


def _load_market_registry(platform_root):
    p = os.path.join(platform_root, "registry", "market.yaml")
    if not os.path.isfile(p):
        return None
    try:
        return _yaml_lite.load_file(p)
    except Exception:
        return None


# ── 摄取 ────────────────────────────────────────────────
def ingest(project_root):
    """读取 sources/research/market/*.yaml → 信号列表。"""
    out = []
    d = _market_dir(project_root)
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not fn.endswith((".yaml", ".yml")):
            continue
        data = _load_any(os.path.join(d, fn))
        if not isinstance(data, dict):
            continue
        # 支持单信号或 signals 列表
        if "signals" in data and isinstance(data["signals"], list):
            for s in data["signals"]:
                if isinstance(s, dict) and s.get("genre"):
                    out.append(s)
        elif data.get("genre"):
            out.append(data)
    return out


def _load_any(path):
    try:
        return _yaml_lite.load_file(path)
    except Exception:
        return None


# ── 打分 ────────────────────────────────────────────────
def score(project_root, platform_root, weights=None):
    """按 genre 聚合机会分。opportunity = Σ w_k * f_k，其中 competition 取 (1-comp)。"""
    if weights is None:
        reg = _load_market_registry(platform_root)
        weights = (reg.get("weights") if isinstance(reg, dict) else None) or _DEFAULT_WEIGHTS
    signals = ingest(project_root)
    by_genre = collections.defaultdict(list)
    for s in signals:
        g = s.get("genre")
        if not g:
            continue
        vals = {}
        ok = True
        for k in _WEIGHT_KEYS:
            v = s.get(k)
            if not isinstance(v, (int, float)):
                ok = False
                break
            vals[k] = float(v)
        if not ok:
            continue
        opp = (weights.get("trend_score", 0) * vals["trend_score"]
               + weights.get("competition", 0) * (1 - vals["competition"])
               + weights.get("reader_demand", 0) * vals["reader_demand"])
        by_genre[g].append(opp)
    out = {}
    for g, lst in by_genre.items():
        out[g] = round(sum(lst) / len(lst), 4) if lst else 0.0
    return out


# ── brief ───────────────────────────────────────────────
def brief(project_root, platform_root):
    signals = ingest(project_root)
    scores = score(project_root, platform_root)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top = ranked[0] if ranked else None
    reg = _load_market_registry(platform_root)
    floor = ((reg or {}).get("thresholds") or {}).get("opportunity_floor", 0.5)
    recommendations = []
    for g, sc in ranked:
        verdict = "高机会" if sc >= floor else ("中等" if sc >= floor * 0.7 else "偏低")
        recommendations.append({"genre": g, "score": sc, "verdict": verdict})
    return {
        "ingested_signals": len(signals),
        "per_genre_score": scores,
        "top_opportunity": {"genre": top[0], "score": top[1]} if top else None,
        "recommendations": recommendations,
        "opportunity_floor": floor,
    }


# ── 写入 NKB（可选）────────────────────────────────────
def sync_nkb(project_root, platform_root, write=False):
    """把市场机会分作为市场事实写入 NKB/Market.yaml（新增组件，不覆盖既有）。"""
    b = brief(project_root, platform_root)
    facts = []
    for g, sc in (b.get("per_genre_score") or {}).items():
        facts.append({
            "genre": g,
            "opportunity_score": sc,
            "verdict": (b.get("recommendations") or [{}])[0].get("verdict", "n/a") if False else None,
        })
    # 关联 verdict
    verdict_map = {r["genre"]: r["verdict"] for r in (b.get("recommendations") or [])}
    for f in facts:
        f["verdict"] = verdict_map.get(f["genre"])
    if not write:
        return {"would_write": len(facts), "facts": facts}
    p = os.path.join(project_root, "NKB", "Market.yaml")
    existing = []
    if os.path.isfile(p):
        try:
            ed = _yaml_lite.load_file(p)
            if isinstance(ed, dict):
                existing = ed.get("market_facts") or []
        except Exception:
            existing = []
    merged = list(existing)
    seen = {f.get("genre") for f in existing}
    for f in facts:
        if f.get("genre") not in seen:
            merged.append(f)
    out = {"schema_version": "1.2.0", "project_id": _project_id(project_root),
           "market_facts": merged}
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(out))
    return {"written": p, "market_facts": len(merged)}


def _project_id(project_root):
    p = os.path.join(project_root, "project.yaml")
    if os.path.isfile(p):
        try:
            d = _yaml_lite.load_file(p)
            if isinstance(d, dict):
                return (d.get("project") or {}).get("id")
        except Exception:
            pass
    return None


# ── doctor 自检 ─────────────────────────────────────────
def govern(platform_root, project_root, write=False):
    reg = _load_market_registry(platform_root)
    fatal = []
    caution = []
    if not reg:
        caution.append("未配置市场分析（registry/market.yaml 缺失，可选）")
        weights = None
    else:
        weights = reg.get("weights")
        if not isinstance(weights, dict):
            fatal.append("market.yaml weights 非法")
        else:
            for k in _WEIGHT_KEYS:
                if not isinstance(weights.get(k), (int, float)):
                    fatal.append("market.yaml weights 缺/非数值：%s" % k)
                    break
            else:
                s = sum(float(weights[k]) for k in _WEIGHT_KEYS)
                if abs(s - 1.0) > 0.001:
                    fatal.append("market.yaml weights 和不为 1.0（=%.3f）" % s)
    # sources 信号健康检查（仅提示，不致命）
    signals = ingest(project_root)
    bad = 0
    for s in signals:
        if not isinstance(s.get("trend_score"), (int, float)):
            bad += 1
    if bad:
        caution.append("市场信号 %d 条缺 trend_score 等数值字段" % bad)
    decision = "block" if fatal else ("caution" if caution else "proceed")
    health = 100 - 40 * len(fatal) - 5 * len(caution)
    report = {
        "meta": {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "component": "market",
            "version": "1.0.0",
            "platform_root": platform_root,
            "project_root": project_root,
        },
        "request": {},
        "response": {"signals": len(signals), "has_registry": reg is not None},
        "decision": decision,
        "gate": {"decision": decision, "reasons": fatal + caution},
        "composite": {"health": health},
    }
    if write:
        out_dir = os.path.join(project_root, "analysis", "market")
        os.makedirs(out_dir, exist_ok=True)
        idx = 1
        for fn in os.listdir(out_dir):
            if fn.startswith("BRIEF-") and fn.endswith(".yaml"):
                try:
                    idx = max(idx, int(fn[6:-5]) + 1)
                except Exception:
                    pass
        with open(os.path.join(out_dir, "BRIEF-%02d.yaml" % idx), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    return report


# ── CLI ─────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(prog="market", description="Phase 3-6 市场分析")
    sub = ap.add_subparsers(dest="cmd")

    pi = sub.add_parser("ingest", help="摄取 sources/research/market/*.yaml 信号")
    pi.add_argument("--project-root", required=True)

    ps = sub.add_parser("score", help="按 genre 机会打分")
    ps.add_argument("--project-root", required=True)
    ps.add_argument("--platform-root", required=True)

    pb = sub.add_parser("brief", help="产出 market brief（机会排序）")
    pb.add_argument("--project-root", required=True)
    pb.add_argument("--platform-root", required=True)

    psn = sub.add_parser("sync", help="写入 NKB Market 组件（市场事实）")
    psn.add_argument("--project-root", required=True)
    psn.add_argument("--platform-root", required=True)
    psn.add_argument("--write", action="store_true")

    pv = sub.add_parser("validate", help="doctor 自检")
    pv.add_argument("--platform-root", required=True)
    pv.add_argument("--project-root", required=True)

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        sys.exit(2)

    if args.cmd == "ingest":
        sigs = ingest(args.project_root)
        print(json.dumps({"signals": len(sigs), "sample": sigs[:3]}, ensure_ascii=False, indent=2))
        sys.exit(0)

    if args.cmd == "score":
        print(json.dumps(score(args.project_root, args.platform_root), ensure_ascii=False, indent=2))
        sys.exit(0)

    if args.cmd == "brief":
        print(json.dumps(brief(args.project_root, args.platform_root), ensure_ascii=False, indent=2))
        sys.exit(0)

    if args.cmd == "sync":
        res = sync_nkb(args.project_root, args.platform_root, write=args.write)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        sys.exit(0)

    if args.cmd == "validate":
        rep = govern(args.platform_root, args.project_root, write=False)
        print(json.dumps(rep["gate"], ensure_ascii=False, indent=2))
        sys.exit(1 if rep["gate"]["decision"] == "block" else 0)


if __name__ == "__main__":
    main()

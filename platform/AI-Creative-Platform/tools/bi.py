#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bi.py — Phase 3-4 BI 分析（Business Intelligence）

聚合既有 analysis 产出（quality / reader / experiment）+ audit_log，
产出 per-dimension rollup + dashboard JSON。不做实时采集，空数据→0 占位不报错。
零依赖：复用同目录 _yaml_lite / _gov。
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

_METRIC_ENUM = ["quality", "reader", "payment", "ci", "cost", "count"]
_DIM_ENUM = ["project", "model", "capability", "component", "experiment"]
_DIM_FIELD = {
    "project": "project_id",
    "model": "model",
    "capability": "capability",
    "component": "component",
    "experiment": "experiment_id",
}


def _bi_path(platform_root):
    return os.path.join(platform_root, "registry", "bi.yaml")


def _load_bi(platform_root):
    p = _bi_path(platform_root)
    if not os.path.isfile(p):
        return None
    try:
        return _yaml_lite.load_file(p)
    except Exception:
        return None


def _parse_ts(s):
    """取日期桶 YYYY-MM-DD；无法解析→unknown。"""
    if not s or not isinstance(s, str):
        return "unknown"
    for i, ch in enumerate(s):
        if ch in ("T", " "):
            return s[:i]
    return s[:10] if len(s) >= 10 else s


# ── 采集 ────────────────────────────────────────────────
def collect(platform_root, project_root):
    """从 quality/reader/experiment 源回收统一 record 列表。

    record = {project_id, model, capability, component, experiment_id, ts, metrics{}}
    空源→返回 []（BI 不报错，调用方按 empty→0 处理）。
    """
    records = []
    # 1) quality 报告（项目级）
    qdir = os.path.join(project_root, "analysis", "quality")
    if os.path.isdir(qdir):
        for fn in os.listdir(qdir):
            if not fn.endswith((".yaml", ".yml", ".json")):
                continue
            d = _load_any(os.path.join(qdir, fn))
            if not isinstance(d, dict):
                continue
            comp = (d.get("composite") or {})
            val = comp.get("value")
            if not isinstance(val, (int, float)):
                continue
            meta = d.get("meta") or {}
            tgt = d.get("target") or {}
            records.append({
                "project_id": meta.get("project"),
                "model": meta.get("model"),
                "capability": tgt.get("target_type"),
                "component": "quality",
                "experiment_id": None,
                "ts": _parse_ts(meta.get("scored_at")),
                "metrics": {"quality": val},
            })
    # 2) reader 报告（项目级）
    rdir = os.path.join(project_root, "analysis", "reader")
    if os.path.isdir(rdir):
        for fn in os.listdir(rdir):
            if not fn.endswith((".yaml", ".yml", ".json")):
                continue
            d = _load_any(os.path.join(rdir, fn))
            if not isinstance(d, dict):
                continue
            meta = d.get("meta") or {}
            tgt = d.get("target") or {}
            ri = d.get("reader_index")
            pi = d.get("pi")
            metrics = {}
            if isinstance(ri, (int, float)):
                metrics["reader"] = ri
            if isinstance(pi, (int, float)):
                metrics["payment"] = pi
            if not metrics:
                continue
            records.append({
                "project_id": meta.get("project"),
                "model": meta.get("model"),
                "capability": tgt.get("target_type"),
                "component": "reader",
                "experiment_id": None,
                "ts": _parse_ts(meta.get("simulated_at")),
                "metrics": metrics,
            })
    # 3) experiment 样本（平台级，analysis/experiment/EXP-samples.yaml）
    spath = os.path.join(platform_root, "analysis", "experiment", "EXP-samples.yaml")
    if os.path.isfile(spath):
        d = _load_any(spath)
        samples = (d.get("samples") or []) if isinstance(d, dict) else []
        # 惰性取 variant→model 映射
        exp_model = {}
        try:
            import experiment as _exp
            for e in (_exp.load_experiments(platform_root).get("experiments") or []):
                vs = e.get("variants") or []
                for i, v in enumerate(vs):
                    if isinstance(v, dict):
                        exp_model[(e.get("id"), i)] = v.get("model")
        except Exception:
            pass
        for s in samples:
            if not isinstance(s, dict):
                continue
            eid = s.get("experiment_id")
            vi = s.get("variant")
            mets = s.get("metrics")
            if not isinstance(mets, dict):
                continue
            rec_metrics = {}
            for k in ("quality", "reader", "ci", "cost"):
                if isinstance(mets.get(k), (int, float)):
                    rec_metrics[k] = mets[k]
            if not rec_metrics:
                continue
            records.append({
                "project_id": None,
                "model": exp_model.get((eid, vi)),
                "capability": None,
                "component": "experiment",
                "experiment_id": eid,
                "ts": "unknown",
                "metrics": rec_metrics,
            })
    return records


def _load_any(path):
    try:
        if path.endswith(".json"):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return _yaml_lite.load_file(path)
    except Exception:
        return None


# ── 聚合 ────────────────────────────────────────────────
def _match_filters(rec, filters):
    if not filters:
        return True
    for k, v in (filters or {}).items():
        if v is None:
            continue
        if rec.get(k) != v:
            return False
    return True


def rollup(records, dimension, metric, filters=None):
    """按 dimension 分组，聚合 metric 均值。metric='count' 时统计记录数。"""
    if dimension not in _DIM_ENUM:
        raise ValueError("非法 dimension：%s" % dimension)
    if metric not in _METRIC_ENUM:
        raise ValueError("非法 metric：%s" % metric)
    field = _DIM_FIELD[dimension]
    groups = collections.defaultdict(list)
    for r in records:
        if not _match_filters(r, filters):
            continue
        if metric == "count":
            groups[r.get(field)].append(1)
        else:
            m = (r.get("metrics") or {}).get(metric)
            if isinstance(m, (int, float)):
                groups[r.get(field)].append(m)
    out = {}
    for key, vals in groups.items():
        out[key if key is not None else "(none)"] = {
            "mean": round(sum(vals) / len(vals), 4) if vals else 0,
            "n": len(vals),
            "sum": round(sum(vals), 4),
        }
    return out


def time_series(records, metric, bucket="day", filters=None):
    """按时间桶（默认按日）聚合 metric。"""
    if metric not in _METRIC_ENUM:
        raise ValueError("非法 metric：%s" % metric)
    buckets = collections.defaultdict(list)
    for r in records:
        if not _match_filters(r, filters):
            continue
        if metric == "count":
            buckets[r.get("ts")].append(1)
        else:
            m = (r.get("metrics") or {}).get(metric)
            if isinstance(m, (int, float)):
                buckets[r.get("ts")].append(m)
    out = []
    for b in sorted(buckets.keys()):
        vals = buckets[b]
        out.append({
            "bucket": b,
            "mean": round(sum(vals) / len(vals), 4) if vals else 0,
            "n": len(vals),
        })
    return out


def dashboard(platform_root, project_root, dash_def, records=None):
    """按单个 dashboard 定义产出 rollup + time_series。"""
    if records is None:
        records = collect(platform_root, project_root)
    metrics = dash_def.get("metrics") or []
    dims = dash_def.get("dimensions") or []
    filters = dash_def.get("filters") or {}
    by_dim = {}
    for dim in dims:
        by_dim[dim] = {m: rollup(records, dim, m, filters) for m in metrics}
    # time-series：取首个 metric 的日趋势
    ts_metric = metrics[0] if metrics else "count"
    series = time_series(records, ts_metric, "day", filters)
    return {
        "id": dash_def.get("id"),
        "title": dash_def.get("title"),
        "metrics": metrics,
        "dimensions": dims,
        "filters": filters,
        "by_dimension": by_dim,
        "time_series": {"metric": ts_metric, "points": series},
        "record_count": len(records),
    }


# ── doctor 自检 ─────────────────────────────────────────
def govern(platform_root, write=False):
    reg = _load_bi(platform_root)
    fatal = []
    caution = []
    if not reg:
        caution.append("未配置 BI 仪表盘（registry/bi.yaml 缺失，可选）")
        ndash = 0
    else:
        dashboards = reg.get("dashboards") or []
        ndash = len(dashboards)
        for d in dashboards:
            if not isinstance(d, dict):
                fatal.append("仪表盘定义非法（非 dict）")
                continue
            if not d.get("id"):
                fatal.append("仪表盘缺 id")
            ms = d.get("metrics") or []
            if not ms:
                fatal.append("仪表盘 %s 缺 metrics" % d.get("id", "?"))
            elif any(m not in _METRIC_ENUM for m in ms):
                fatal.append("仪表盘 %s metrics 含非法枚举" % d.get("id", "?"))
            ds = d.get("dimensions") or []
            if not ds:
                fatal.append("仪表盘 %s 缺 dimensions" % d.get("id", "?"))
            elif any(x not in _DIM_ENUM for x in ds):
                fatal.append("仪表盘 %s dimensions 含非法枚举" % d.get("id", "?"))

    decision = "block" if fatal else ("caution" if caution else "proceed")
    health = 100 - 40 * len(fatal) - 5 * len(caution)
    report = {
        "meta": {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "component": "bi",
            "version": "1.0.0",
            "platform_root": platform_root,
        },
        "request": {},
        "response": {"dashboards": ndash},
        "decision": decision,
        "gate": {"decision": decision, "reasons": fatal + caution},
        "composite": {"health": health},
    }
    if write:
        out_dir = os.path.join(platform_root, "analysis", "bi")
        os.makedirs(out_dir, exist_ok=True)
        idx = 1
        for fn in os.listdir(out_dir):
            if fn.startswith("DASH-") and fn.endswith(".yaml"):
                try:
                    idx = max(idx, int(fn[5:-5]) + 1)
                except Exception:
                    pass
        with open(os.path.join(out_dir, "DASH-%02d.yaml" % idx), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    return report


# ── CLI ─────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(prog="bi", description="Phase 3-4 BI 分析")
    sub = ap.add_subparsers(dest="cmd")

    pr = sub.add_parser("rollup", help="按维度聚合某指标均值")
    pr.add_argument("--platform-root", required=True)
    pr.add_argument("--project-root", required=True)
    pr.add_argument("--dimension", required=True, choices=_DIM_ENUM)
    pr.add_argument("--metric", required=True, choices=_METRIC_ENUM)
    pr.add_argument("--filter-project", default=None)
    pr.add_argument("--filter-model", default=None)
    pr.add_argument("--filter-experiment", default=None)

    pd = sub.add_parser("dashboard", help="按 bi.yaml 仪表盘定义产出 dashboard JSON")
    pd.add_argument("--platform-root", required=True)
    pd.add_argument("--project-root", required=True)
    pd.add_argument("--id", default=None, help="指定 dashboard id；省略则全部")
    pd.add_argument("--write", action="store_true", help="写回 analysis/bi/DASH-NN.yaml")

    pv = sub.add_parser("validate", help="doctor 自检")
    pv.add_argument("--platform-root", required=True)

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        sys.exit(2)

    if args.cmd == "rollup":
        recs = collect(args.platform_root, args.project_root)
        filters = {
            "project_id": getattr(args, "filter_project", None),
            "model": getattr(args, "filter_model", None),
            "experiment_id": getattr(args, "filter_experiment", None),
        }
        res = rollup(recs, args.dimension, args.metric, filters)
        print(json.dumps({"dimension": args.dimension, "metric": args.metric,
                         "rollup": res}, ensure_ascii=False, indent=2))
        sys.exit(0)

    if args.cmd == "dashboard":
        reg = _load_bi(args.platform_root)
        if not reg:
            print(json.dumps({"error": "registry/bi.yaml 缺失"}, ensure_ascii=False))
            sys.exit(1)
        dashes = reg.get("dashboards") or []
        if args.id:
            dashes = [d for d in dashes if d.get("id") == args.id]
            if not dashes:
                print(json.dumps({"error": "未定义 dashboard：%s" % args.id},
                                ensure_ascii=False))
                sys.exit(1)
        recs = collect(args.platform_root, args.project_root)
        out = [dashboard(args.platform_root, args.project_root, d, recs) for d in dashes]
        if args.write:
            out_dir = os.path.join(args.platform_root, "analysis", "bi")
            os.makedirs(out_dir, exist_ok=True)
            idx = 1
            for fn in os.listdir(out_dir):
                if fn.startswith("DASH-") and fn.endswith(".yaml"):
                    try:
                        idx = max(idx, int(fn[5:-5]) + 1)
                    except Exception:
                        pass
            p = os.path.join(out_dir, "DASH-%02d.yaml" % idx)
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"schema_version": "1.0.0", "dashboards": out},
                          f, ensure_ascii=False, indent=2)
            print(json.dumps({"written": p, "dashboards": len(out)}, ensure_ascii=False))
        else:
            print(json.dumps({"dashboards": out}, ensure_ascii=False, indent=2))
        sys.exit(0)

    if args.cmd == "validate":
        rep = govern(args.platform_root, write=False)
        print(json.dumps(rep["gate"], ensure_ascii=False, indent=2))
        sys.exit(1 if rep["gate"]["decision"] == "block" else 0)


if __name__ == "__main__":
    main()

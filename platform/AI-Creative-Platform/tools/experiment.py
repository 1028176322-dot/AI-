#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""experiment.py — Phase 3-3 实验系统（Experiment）

定义 Prompt/模型 A/B 对照实验，按 split 分配 variant，回收 quality/reader/ci/cost
指标，判定胜者。不自己跑创作（挂在 task submit / model-router 上）。
零依赖：复用同目录 _yaml_lite / _gov。
"""
import os
import sys
import json
import hashlib
import argparse
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _yaml_lite
import _gov

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

_SPLIT_ENUM = ["chapter", "project", "random"]
_METRIC_ENUM = ["quality", "reader", "ci", "cost"]
_SAMPLES_FILE = "EXP-samples.yaml"


def _experiments_path(platform_root):
    return os.path.join(platform_root, "registry", "experiments.yaml")


def _samples_path(platform_root):
    return os.path.join(platform_root, "analysis", "experiment", _SAMPLES_FILE)


def _load(platform_root):
    if not os.path.isfile(_experiments_path(platform_root)):
        return None
    try:
        return _yaml_lite.load_file(_experiments_path(platform_root))
    except Exception:
        return None


def load_experiments(platform_root):
    return _load(platform_root) or {}


def get_experiment(platform_root, exp_id):
    for e in (load_experiments(platform_root).get("experiments") or []):
        if isinstance(e, dict) and e.get("id") == exp_id:
            return e
    return None


def _stable_hash(s):
    return int(hashlib.md5(str(s).encode("utf-8")).hexdigest(), 16)


def assign_variant(exp, unit_id):
    """确定性分配 variant（同一 unit 始终同一 variant）。"""
    variants = exp.get("variants") or []
    n = len(variants)
    if n == 0:
        return None
    split = exp.get("split")
    if not isinstance(split, dict):
        split = {}
    ratio = split.get("ratio")
    if n == 2 and isinstance(ratio, (int, float)):
        return 0 if (_stable_hash(unit_id) % 100) < int(ratio * 100) else 1
    return _stable_hash(unit_id) % n


# ── 定义 ────────────────────────────────────────────────
def define(platform_root, exp_def, write=False):
    """校验并登记一个实验。返回 (ok, errors, exp_id)。"""
    errors = []
    if not isinstance(exp_def, dict):
        return False, ["exp_def 必须是 dict"], None
    eid = exp_def.get("id")
    if not eid:
        errors.append("缺少 id")
    variants = exp_def.get("variants") or []
    if not variants:
        errors.append("缺少 variants")
    for v in variants:
        if not isinstance(v, dict) or not v.get("model"):
            errors.append("variant 缺 model")
    split = exp_def.get("split") or {}
    if split.get("by") not in _SPLIT_ENUM:
        errors.append("split.by 非法（须 chapter/project/random）")
    ms = exp_def.get("min_samples", 0)
    if not isinstance(ms, int) or ms <= 0:
        errors.append("min_samples 非法（须正整数）")
    metrics = exp_def.get("metrics") or []
    if not metrics:
        errors.append("缺少 metrics")
    if errors:
        return False, errors, None

    reg = _load(platform_root) or {"schema_version": "1.0.0", "experiments": []}
    exps = reg.get("experiments") or []
    if any((isinstance(e, dict) and e.get("id") == eid) for e in exps):
        return False, ["id 已存在：%s" % eid], None
    exps.append({
        "id": eid,
        "name": exp_def.get("name", eid),
        "variants": variants,
        "split": split,
        "metrics": metrics,
        "min_samples": ms,
        "significance": exp_def.get("significance", 0.05),
    })
    reg["experiments"] = exps
    if write:
        os.makedirs(os.path.dirname(_experiments_path(platform_root)), exist_ok=True)
        with open(_experiments_path(platform_root), "w", encoding="utf-8") as f:
            f.write(_gov.dump_block(reg))
    return True, [], eid


# ── 样本回收 ────────────────────────────────────────────
def _load_samples(platform_root):
    p = _samples_path(platform_root)
    if not os.path.isfile(p):
        return []
    try:
        d = _yaml_lite.load_file(p)
        return (d.get("samples") or []) if isinstance(d, dict) else []
    except Exception:
        return []


def record_sample(platform_root, exp_id, unit_id, metrics, write=False):
    """为某实验单元记录一次样本（先按 split 分配 variant）。"""
    exp = get_experiment(platform_root, exp_id)
    if not exp:
        return None
    variant = assign_variant(exp, unit_id)
    sample = {
        "experiment_id": exp_id,
        "unit_id": unit_id,
        "variant": variant,
        "metrics": {m: metrics.get(m) for m in exp.get("metrics", [])},
    }
    if write:
        samples = _load_samples(platform_root)
        samples.append(sample)
        out = {"schema_version": "1.0.0", "samples": samples}
        out_dir = os.path.join(platform_root, "analysis", "experiment")
        os.makedirs(out_dir, exist_ok=True)
        with open(_samples_path(platform_root), "w", encoding="utf-8") as f:
            f.write(_gov.dump_block(out))
    return sample


# ── 聚合 + 判定 ─────────────────────────────────────────
def aggregate(platform_root, exp_id):
    exp = get_experiment(platform_root, exp_id)
    if not exp:
        return None
    samples = [s for s in _load_samples(platform_root)
               if s.get("experiment_id") == exp_id]
    per = {i: {m: [] for m in exp["metrics"]} for i in range(len(exp["variants"]))}
    for s in samples:
        vi = s.get("variant")
        if vi is None or vi not in per:
            continue
        for m, v in (s.get("metrics") or {}).items():
            if m in per[vi] and isinstance(v, (int, float)):
                per[vi][m].append(v)
    out = {}
    for vi, mm in per.items():
        out[vi] = {}
        for m, vals in mm.items():
            out[vi][m] = (round(sum(vals) / len(vals), 4) if vals else None)
        out[vi]["_n"] = len([s for s in samples if s.get("variant") == vi])
    return out


def decide_winner(platform_root, exp_id):
    exp = get_experiment(platform_root, exp_id)
    if not exp:
        return None
    min_samples = exp.get("min_samples", 0)
    agg = aggregate(platform_root, exp_id)
    if not agg:
        return None
    if any((agg.get(vi, {}).get("_n", 0) < min_samples) for vi in agg):
        return None  # 样本不足不判定
    primary = (exp.get("metrics") or ["quality"])[0]
    scored = [(vi, (agg[vi].get(primary) or 0)) for vi in agg]
    scored.sort(key=lambda x: x[1], reverse=True)
    winner, best = scored[0]
    return {
        "winner": winner,
        "primary_metric": primary,
        "primary_value": best,
        "ranking": scored,
        "confidence": "heuristic（样本充足，按主指标均值排序）",
    }


# ── doctor 自检 ─────────────────────────────────────────
def govern(platform_root, write=False, proposed_by="unknown"):
    reg = _load(platform_root)
    fatal = []
    caution = []
    if not reg:
        fatal.append("registry/experiments.yaml 缺失或不可解析")
    else:
        for e in (reg.get("experiments") or []):
            eid = e.get("id")
            if not eid:
                fatal.append("实验缺 id")
                continue
            if not (e.get("variants") or []):
                fatal.append("实验 %s 无 variants" % eid)
                continue
            for v in (e.get("variants") or []):
                if not isinstance(v, dict) or not v.get("model"):
                    fatal.append("实验 %s variant 缺 model" % eid)
            split = e.get("split")
            if not isinstance(split, dict) or split.get("by") not in _SPLIT_ENUM:
                fatal.append("实验 %s split.by 非法" % eid)
            ms = e.get("min_samples", 0)
            if not isinstance(ms, int) or ms <= 0:
                fatal.append("实验 %s min_samples 非法" % eid)
            if not (e.get("metrics") or []):
                fatal.append("实验 %s 无 metrics" % eid)
            # caution: 样本不足（结论未定）
            n = len([s for s in _load_samples(platform_root)
                     if s.get("experiment_id") == eid])
            if 0 < n < ms:
                caution.append("实验 %s 样本 %d < min_samples %d（结论未定）" % (eid, n, ms))

    decision = "block" if fatal else ("caution" if caution else "proceed")
    health = 100 - 40 * len(fatal) - 5 * len(caution)
    report = {
        "meta": {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "component": "experiment",
            "version": "1.0.0",
            "platform_root": platform_root,
        },
        "request": {"experiment_id": None},
        "response": {"experiments": len(reg.get("experiments") or []) if reg else 0},
        "decision": decision,
        "gate": {"decision": decision, "reasons": fatal + caution},
        "composite": {"health": health},
    }
    if write:
        out_dir = os.path.join(platform_root, "analysis", "experiment")
        os.makedirs(out_dir, exist_ok=True)
        idx = 1
        for fn in os.listdir(out_dir):
            if fn.endswith(".yaml") and fn.startswith("EXP-") and fn != _SAMPLES_FILE:
                try:
                    num = int(fn[4:-5].split("-")[0])
                    idx = max(idx, num + 1)
                except Exception:
                    pass
        with open(os.path.join(out_dir, "EXP-%02d.yaml" % idx), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    return report


# ── CLI ─────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(prog="experiment", description="Phase 3-3 实验系统")
    sub = ap.add_subparsers(dest="cmd")

    pd = sub.add_parser("define", help="定义实验（写回 registry/experiments.yaml）")
    pd.add_argument("--platform-root", required=True)
    pd.add_argument("--id", required=True)
    pd.add_argument("--name", default=None)
    pd.add_argument("--variants", required=True, help="JSON 列表 [{model,prompt,temp},...]")
    pd.add_argument("--split-by", required=True)
    pd.add_argument("--split-ratio", default=0.5, type=float)
    pd.add_argument("--metrics", default="quality,reader,ci,cost")
    pd.add_argument("--min-samples", type=int, default=8)

    pr = sub.add_parser("run", help="为单元分配 variant（确定性）")
    pr.add_argument("--platform-root", required=True)
    pr.add_argument("--experiment", required=True)
    pr.add_argument("--unit", required=True)

    pp = sub.add_parser("report", help="聚合指标 + 判定胜者")
    pp.add_argument("--platform-root", required=True)
    pp.add_argument("--experiment", required=True)

    psv = sub.add_parser("sample", help="记录一次样本（自动分配 variant）")
    psv.add_argument("--platform-root", required=True)
    psv.add_argument("--experiment", required=True)
    psv.add_argument("--unit", required=True)
    psv.add_argument("--metrics", required=True, help="JSON {quality,reader,ci,cost}")

    pv = sub.add_parser("validate", help="doctor 自检")
    pv.add_argument("--platform-root", required=True)

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        sys.exit(2)

    if args.cmd == "define":
        try:
            variants = json.loads(args.variants)
        except Exception:
            print(json.dumps({"ok": False, "errors": ["variants 非合法 JSON"]},
                            ensure_ascii=False))
            sys.exit(1)
        exp_def = {
            "id": args.id, "name": args.name,
            "variants": variants,
            "split": {"by": args.split_by, "ratio": args.split_ratio},
            "metrics": [m.strip() for m in args.metrics.split(",") if m.strip()],
            "min_samples": args.min_samples,
        }
        ok, errs, eid = define(args.platform_root, exp_def, write=True)
        if not ok:
            print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False, indent=2))
            sys.exit(1)
        print(json.dumps({"ok": True, "experiment_id": eid}, ensure_ascii=False))
        sys.exit(0)

    if args.cmd == "run":
        exp = get_experiment(args.platform_root, args.experiment)
        if not exp:
            print(json.dumps({"error": "未定义实验：%s" % args.experiment},
                            ensure_ascii=False))
            sys.exit(1)
        vi = assign_variant(exp, args.unit)
        print(json.dumps({"experiment_id": args.experiment, "unit_id": args.unit,
                         "variant": vi}, ensure_ascii=False))
        sys.exit(0)

    if args.cmd == "sample":
        try:
            metrics = json.loads(args.metrics)
        except Exception:
            print(json.dumps({"ok": False, "errors": ["metrics 非合法 JSON"]},
                            ensure_ascii=False))
            sys.exit(1)
        s = record_sample(args.platform_root, args.experiment, args.unit, metrics, write=True)
        if not s:
            print(json.dumps({"error": "未定义实验：%s" % args.experiment},
                            ensure_ascii=False))
            sys.exit(1)
        print(json.dumps(s, ensure_ascii=False))
        sys.exit(0)

    if args.cmd == "report":
        agg = aggregate(args.platform_root, args.experiment)
        winner = decide_winner(args.platform_root, args.experiment)
        print(json.dumps({"experiment_id": args.experiment, "aggregate": agg,
                         "winner": winner}, ensure_ascii=False, indent=2))
        sys.exit(0)

    if args.cmd == "validate":
        rep = govern(args.platform_root, write=False)
        print(json.dumps(rep["gate"], ensure_ascii=False, indent=2))
        sys.exit(1 if rep["gate"]["decision"] == "block" else 0)


if __name__ == "__main__":
    main()

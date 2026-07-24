#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""model_router.py — Phase 3-1 模型布线器（Model Router）

决定每个任务/角色用哪个模型；只做路由决策，返回 model spec，不调用模型。
零依赖：复用同目录 _yaml_lite。
"""
import os
import sys
import json
import argparse
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _yaml_lite

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"


def _load(path):
    if not os.path.isfile(path):
        return None
    try:
        return _yaml_lite.load_file(path)
    except Exception:
        return None


def _models_path(platform_root):
    return os.path.join(platform_root, "registry", "models.yaml")


def _router_path(platform_root):
    return os.path.join(platform_root, "registry", "model-router.yaml")


def load_models(platform_root):
    return _load(_models_path(platform_root)) or {}


def load_router(platform_root):
    return _load(_router_path(platform_root)) or {}


def _available(models_doc):
    out = {}
    for m in (models_doc.get("models") or []):
        if not isinstance(m, dict):
            continue
        if m.get("available", False):
            out[m.get("id")] = m
    return out


def resolve(platform_root, role=None, task_type=None, capability=None,
            quality_tier=None, cost_budget=None, latency_sla=None):
    """返回解析结果 dict 或 None（=block，无法解析可用模型）。"""
    models_doc = load_models(platform_root)
    router_doc = load_router(platform_root)
    if not models_doc or not router_doc:
        return None
    avail = _available(models_doc)
    if not avail:
        return None
    default_id = router_doc.get("default")
    rules = router_doc.get("rules") or []
    tried = []
    matched = None
    for rule in rules:
        m = rule.get("match") or {}
        ok = True
        if "role" in m and role is not None and m["role"] != role:
            ok = False
        if "task_type" in m and task_type is not None and m["task_type"] != task_type:
            ok = False
        if "capability" in m and capability is not None and m["capability"] != capability:
            ok = False
        if "quality_tier_min" in m and quality_tier is not None:
            try:
                if int(quality_tier) < int(m["quality_tier_min"]):
                    ok = False
            except Exception:
                pass
        if ok:
            matched = rule
            break
    candidates = []
    if matched:
        prim = matched.get("primary")
        if prim:
            candidates.append(prim)
        for fb in (matched.get("fallback") or []):
            candidates.append(fb)
    if default_id and default_id not in candidates:
        candidates.append(default_id)
    for cid in candidates:
        tried.append(cid)
        m = avail.get(cid)
        if not m:
            continue
        caps = m.get("supports") or []
        if capability and capability not in caps:
            continue
        if cost_budget is not None:
            try:
                c = float(m.get("cost_per_1k_out", 0) or 0)
                if c > float(cost_budget):
                    continue
            except Exception:
                pass
        return {
            "model_id": cid,
            "endpoint": m.get("endpoint"),
            "ctx_window": m.get("ctx_window"),
            "quality_tier": m.get("quality_tier"),
            "params": {},
            "decision_path": {
                "matched_rule": (matched.get("match") if matched else None),
                "tried": tried,
            },
        }
    return None


def govern(platform_root, write=False, proposed_by="unknown", model="unknown"):
    """doctor 自检：返回 report dict（gate.decision ∈ proceed/caution/block）。"""
    models_doc = load_models(platform_root)
    router_doc = load_router(platform_root)
    fatal = []
    caution = []
    if not models_doc:
        fatal.append("models.yaml 缺失或不可解析")
    else:
        if not (models_doc.get("models") or []):
            fatal.append("models.yaml 无模型（models 为空）")
        if not _available(models_doc):
            fatal.append("models.yaml 中无 available=true 的模型")
    if not router_doc:
        fatal.append("model-router.yaml 缺失或不可解析")
    else:
        default_id = router_doc.get("default")
        avail = _available(models_doc) if models_doc else {}
        if default_id and default_id not in avail:
            caution.append("default 模型 %s 不可用" % default_id)
        for rule in (router_doc.get("rules") or []):
            prim = rule.get("primary")
            if prim and prim not in avail:
                caution.append("规则 primary 引用不可用/未知模型 %s" % prim)
            for fb in (rule.get("fallback") or []):
                if fb and fb not in avail:
                    caution.append("规则 fallback 引用不可用/未知模型 %s" % fb)
    if fatal:
        decision = "block"
    elif caution:
        decision = "caution"
    else:
        decision = "proceed"
    health = 100
    if fatal:
        health -= 40
    health -= 5 * len(caution)
    report = {
        "meta": {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "component": "model-router",
            "version": "1.0.0",
            "platform_root": platform_root,
        },
        "request": {"role": None, "task_type": None, "capability": None},
        "response": {"model_id": None},
        "routing": {"matched_rule": None, "tried": []},
        "decision": decision,
        "gate": {
            "decision": decision,
            "reasons": fatal + caution,
        },
        "composite": {"health": health},
    }
    if write:
        out_dir = os.path.join(platform_root, "analysis", "model-router")
        os.makedirs(out_dir, exist_ok=True)
        idx = 1
        for fn in os.listdir(out_dir):
            if fn.endswith(".yaml"):
                try:
                    n = int(fn.split("-")[-1].split(".")[0])
                    idx = max(idx, n + 1)
                except Exception:
                    pass
        out_path = os.path.join(out_dir, "MR-%02d.yaml" % idx)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def main():
    ap = argparse.ArgumentParser(prog="model_router", description="Phase 3-1 模型布线器")
    sub = ap.add_subparsers(dest="cmd")
    rs = sub.add_parser("resolve", help="按请求解析模型")
    rs.add_argument("--platform-root", required=True)
    rs.add_argument("--role", default=None)
    rs.add_argument("--task-type", default=None)
    rs.add_argument("--capability", default=None)
    rs.add_argument("--quality-tier", default=None)
    rs.add_argument("--cost-budget", default=None)
    rs.add_argument("--latency-sla", default=None)
    va = sub.add_parser("validate", help="校验 models.yaml + model-router.yaml")
    va.add_argument("--platform-root", required=True)
    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        sys.exit(2)
    if args.cmd == "resolve":
        res = resolve(args.platform_root, role=args.role, task_type=args.task_type,
                      capability=args.capability, quality_tier=args.quality_tier,
                      cost_budget=args.cost_budget, latency_sla=args.latency_sla)
        if res is None:
            print(json.dumps({"decision": "block", "error": "无法解析可用模型"}, ensure_ascii=False))
            sys.exit(1)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        sys.exit(0)
    if args.cmd == "validate":
        rep = govern(args.platform_root, write=False)
        print(json.dumps(rep["gate"], ensure_ascii=False, indent=2))
        sys.exit(1 if rep["gate"]["decision"] == "block" else 0)


if __name__ == "__main__":
    main()

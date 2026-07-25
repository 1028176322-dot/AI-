#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""project_health.py — Phase C 项目基线健康检查（ProjectGov）

校验项目自身 project.yaml 的结构健康（不依赖任何能力模块）：
  - 必需顶层键（project / requires / paths）
  - project. 必需字段（id / name / type）
  - gates 数值合法（editor_score/reader_index/payment_intent 0..100；consistency_index 0..1）
  - paths 声明目录存在
返回标准化 {gate:{decision,reasons}, composite:{health}, response:{...}}（与平台其他 Gov 契约一致）。

零依赖：复用同目录 _yaml_lite。
脚本只做确定性结构校验，不下质量结论。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _yaml_lite

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

_REQ_TOP = ["project", "requires", "paths"]
_REQ_PROJECT = ["id", "name", "type"]
_GATE_KEYS = ["editor_score", "consistency_index", "reader_index", "payment_intent"]


def _gate_range(key, v):
    if not isinstance(v, (int, float)):
        return False
    if key == "consistency_index":
        return 0.0 <= v <= 1.0
    return 0 <= v <= 100


def govern(proot, write=False):
    """校验项目 project.yaml 结构健康。返回标准化 Gov 报告。"""
    reasons = []
    resp = {"summary": "ok", "missing_keys": [], "bad_gates": [], "missing_paths": []}
    py = os.path.join(proot, "project.yaml")
    if not os.path.isfile(py):
        resp["summary"] = "project.yaml 缺失"
        return {
            "gate": {"decision": "block", "reasons": ["project.yaml 缺失"]},
            "composite": {"health": 0},
            "response": resp,
        }

    data = _yaml_lite.load_file(py) or {}
    for k in _REQ_TOP:
        if k not in data:
            reasons.append("缺顶层键 %s" % k)
            resp["missing_keys"].append(k)
    proj = data.get("project") or {}
    for k in _REQ_PROJECT:
        if k not in proj:
            reasons.append("project. 缺 %s" % k)
            resp["missing_keys"].append("project.%s" % k)
    gates = data.get("gates") or {}
    for gk in _GATE_KEYS:
        v = gates.get(gk)
        if v is None:
            reasons.append("gates. 缺 %s" % gk)
            resp["bad_gates"].append(gk)
        elif not _gate_range(gk, v):
            reasons.append("gates.%s 非法(%s)" % (gk, v))
            resp["bad_gates"].append(gk)
    paths = data.get("paths") or {}
    for pk, pv in paths.items():
        rel = pv[2:] if isinstance(pv, str) and pv.startswith("./") else pv
        pdir = os.path.join(proot, rel)
        if not os.path.exists(pdir):
            reasons.append("paths.%s 指向不存在目录 %s" % (pk, pv))
            resp["missing_paths"].append(pk)

    if resp["missing_keys"]:
        decision = "block"
    elif reasons:
        decision = "caution"
    else:
        decision = "proceed"
    health = max(0, 100 - 10 * len(reasons)) if reasons else 100
    if reasons:
        resp["summary"] = "%d 项问题" % len(reasons)
    return {
        "gate": {"decision": decision, "reasons": reasons},
        "composite": {"health": health},
        "response": resp,
    }


if __name__ == "__main__":
    import json
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    print(json.dumps(govern(root), ensure_ascii=False, indent=2))

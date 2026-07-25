# -*- coding: utf-8 -*-
# [Phase2-path] 把 scripts 各分组目录加入 sys.path，保持跨组裸名 import 可用
import os as _os, sys as _sys
_H0 = _os.path.dirname(_os.path.abspath(__file__))
_SCR0 = _os.path.dirname(_H0)
if _os.path.isdir(_SCR0):
    for _d in _os.listdir(_SCR0):
        _p = _os.path.join(_SCR0, _d)
        if _os.path.isdir(_p) and _p not in _sys.path:
            _sys.path.insert(0, _p)
"""validate_contract: 校验操作 payload 是否满足契约必填字段。"""
import os
import sys
import argparse
import json
import _gov


def _get(d, dotted):
    cur = d
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", required=True)
    ap.add_argument("--payload", required=True)
    args = ap.parse_args()
    plat = _gov.find_platform_root()
    cpath = os.path.join(plat, "core", "contracts", "%s.contract.yaml" % args.contract)
    if not os.path.isfile(cpath):
        print("ERROR: contract '%s' not found at %s" % (args.contract, cpath))
        sys.exit(2)
    contract = _gov.load_yaml(cpath)
    with open(args.payload, "r", encoding="utf-8") as f:
        text = f.read().strip()
    try:
        payload = json.loads(text) if text.startswith("{") else _gov.load_yaml(text)
    except Exception as e:
        print("ERROR: cannot parse payload: %s" % e)
        sys.exit(2)

    missing = []
    for section in ("input", "output"):
        req = (contract.get(section, {}) or {}).get("required", []) or []
        sec = payload.get(section, {}) or {}
        for field in req:
            if _get(sec, field) is None:
                missing.append("%s.%s" % (section, field))
    if missing:
        print("CONTRACT FAIL: %s missing -> %s" % (args.contract, ", ".join(missing)))
        sys.exit(1)
    print("CONTRACT PASS: %s (all required fields present)" % args.contract)
    sys.exit(0)


if __name__ == "__main__":
    main()

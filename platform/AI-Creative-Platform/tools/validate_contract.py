# -*- coding: utf-8 -*-
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

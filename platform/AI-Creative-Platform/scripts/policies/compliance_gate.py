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
"""compliance_gate: 平台合规门。不查文学质量，只查流程合规。任一 FAIL -> REJECTED_BY_PLATFORM。"""
import os
import sys
import argparse
import _gov


def _norm(d, dotted):
    cur = d
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--operation", default=None)
    ap.add_argument("--role", default=None)
    ap.add_argument("--handoff", default=None)
    args = ap.parse_args()

    plat = _gov.find_platform_root()
    policy = _gov.load_yaml(os.path.join(plat, "core", "policies", "compliance.policy.yaml"))
    checks = policy.get("gate", {}).get("checks", [])

    session = _gov.load_yaml(args.session) if os.path.isfile(args.session) else {}
    operation = _gov.load_yaml(args.operation) if args.operation and os.path.isfile(args.operation) else {}
    role = args.role or (session.get("session", {}).get("role"))

    roles = _gov.load_yaml(os.path.join(plat, "core", "session", "ROLE_REGISTRY.yaml")).get("roles", {})
    facts = {}
    facts["session_manifest_exists"] = os.path.isfile(args.session)
    facts["role_authorized"] = role in roles
    facts["contract_valid"] = bool(operation) and bool(_norm(operation, "inputs.contract_version"))
    facts["platform_version_valid"] = (session.get("session", {}).get("platform_version") not in (None, "unknown"))
    facts["nkb_snapshot_recorded"] = bool(session.get("session", {}).get("loaded", {}).get("nkb")) or (_norm(operation, "inputs.nkb_version") is not None)
    facts["context_hash_recorded"] = _norm(operation, "inputs.context_hash") is not None
    facts["operation_manifest_exists"] = bool(operation)
    forbidden = False
    if operation:
        files = _norm(operation, "changes.files") or []
        for fpath in files:
            ok, _ = _gov.check_permission(role, fpath)
            if not ok:
                forbidden = True
    facts["forbidden_files_modified"] = forbidden
    facts["handoff_complete"] = True if not args.handoff else os.path.isfile(args.handoff)

    failed = []
    for c in checks:
        field = c.get("field")
        expect = c.get("expect")
        val = facts.get(field)
        ok = (val == expect)
        if not ok:
            failed.append(c.get("id"))
        print("[%s] %s = %s (expect %s)" % ("PASS" if ok else "FAIL", field, val, expect))

    if failed:
        print("REJECTED_BY_PLATFORM: %s" % ", ".join(failed))
        sys.exit(1)
    print("COMPLIANCE PASS: ready for content review")
    sys.exit(0)


if __name__ == "__main__":
    main()

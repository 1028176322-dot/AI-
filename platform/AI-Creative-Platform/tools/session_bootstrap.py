# -*- coding: utf-8 -*-
"""Session Bootstrap: 加载平台+项目，生成 Session Manifest。未生成前禁止写操作。"""
import os
import sys
import argparse
import datetime
import glob

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _gov


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--workspace", default=None)
    args = ap.parse_args()

    ws_root = args.workspace or _gov.find_workspace_root()
    plat_root = _gov.find_platform_root()

    role_file = os.path.join(plat_root, "core", "session", "ROLE_REGISTRY.yaml")
    if not os.path.isfile(role_file):
        print("ERROR: ROLE_REGISTRY.yaml missing at %s" % role_file)
        sys.exit(2)
    roles = _gov.load_yaml(role_file).get("roles", {})
    if args.role not in roles:
        print("ERROR: unknown role '%s' (known: %s)" % (args.role, ", ".join(roles.keys())))
        sys.exit(2)

    pdir, pdata = _gov.find_project(ws_root, args.project)
    if pdir is None:
        print("ERROR: project '%s' not found in workspace" % args.project)
        sys.exit(2)

    ver_file = os.path.join(plat_root, "registry", "versions.yaml")
    versions = _gov.load_yaml(ver_file) if os.path.isfile(ver_file) else {}
    core = versions.get("core", {}) if isinstance(versions.get("core"), dict) else {}

    plat_ver = core.get("platform", "unknown")
    con_ver = core.get("contract", "unknown")
    req = pdata.get("requires", {})
    proj_ver = (pdata.get("template") or {}).get("version") or (req.get("templates") or {}).get("xuanhuan", "unknown")
    pol_ver = "1.3.0"

    now = datetime.datetime.now()
    stamp = now.strftime("%Y%m%d")
    sess_dir = os.path.join(pdir, "sessions")
    os.makedirs(sess_dir, exist_ok=True)
    n = len(glob.glob(os.path.join(sess_dir, "SES-%s-*.yaml" % stamp))) + 1
    sid = "SES-%s-%03d" % (stamp, n)

    manifest = {
        "session": {
            "id": sid,
            "project_id": args.project,
            "role": args.role,
            "platform_version": plat_ver,
            "project_version": proj_ver,
            "policy_version": pol_ver,
            "contracts_version": con_ver,
            "created": now.strftime("%Y-%m-%dT%H:%M:%S"),
            "loaded": {
                "constitution": True,
                "specification": True,
                "project_yaml": True,
                "nkb": True,
                "role_policy": True,
                "workflow": True,
            },
        },
        "permissions": {
            "read": roles[args.role].get("may_write", []) + ["NKB/**", "outline/**", "chapters/**"],
            "write": roles[args.role].get("may_write", []),
            "forbidden": roles[args.role].get("may_not_write", []),
        },
    }
    out = os.path.join(sess_dir, "%s.yaml" % sid)
    with open(out, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(manifest))
    print("SESSION MANIFEST: %s" % out)
    print("role=%s project=%s platform=%s policy=%s contracts=%s" % (args.role, args.project, plat_ver, pol_ver, con_ver))
    print("OK")
    sys.exit(0)


if __name__ == "__main__":
    main()

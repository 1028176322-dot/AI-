# -*- coding: utf-8 -*-
"""controlled_write: 受控写工具。AI 只能通过它改项目文件；越权直接拒绝并生成 Operation Manifest。"""
import os
import sys
import argparse
import datetime
import glob
import _gov


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True)
    ap.add_argument("--target", required=True, help="相对项目根的路径，如 chapters/drafts/CH-001.md")
    ap.add_argument("--project", required=True)
    ap.add_argument("--content-file", default=None)
    ap.add_argument("--nkb-version", default=None)
    ap.add_argument("--context-hash", default=None)
    ap.add_argument("--contract-version", default="2.0.0")
    ap.add_argument("--policy-version", default="1.3.0")
    ap.add_argument("--session", default="SES-unknown")
    args = ap.parse_args()

    allowed, reason = _gov.check_permission(args.role, args.target)
    if not allowed:
        print("REJECTED: role=%s cannot write %s -> %s" % (args.role, args.target, reason))
        sys.exit(1)

    ws_root = _gov.find_workspace_root()
    pdir, _ = _gov.find_project(ws_root, args.project)
    if pdir is None:
        print("ERROR: project %s not found" % args.project)
        sys.exit(2)

    full = os.path.join(pdir, args.target)
    if args.content_file:
        with open(args.content_file, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = sys.stdin.read()
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)

    now = datetime.datetime.now()
    stamp = now.strftime("%Y%m%d")
    odir = os.path.join(pdir, "operations")
    os.makedirs(odir, exist_ok=True)
    n = len(glob.glob(os.path.join(odir, "OP-%s-*.yaml" % stamp))) + 1
    opid = "OP-%s-%03d" % (stamp, n)

    nkbv = int(args.nkb_version) if (args.nkb_version and str(args.nkb_version).isdigit()) else args.nkb_version

    op = {
        "operation": {
            "id": opid,
            "session_id": args.session,
            "role": args.role,
            "project_id": args.project,
        },
        "action": {
            "type": "chapter.write" if args.target.startswith("chapters/drafts") else "generic.write",
            "target": args.target,
        },
        "inputs": {
            "nkb_version": nkbv,
            "context_hash": args.context_hash,
            "contract_version": args.contract_version,
            "policy_version": args.policy_version,
        },
        "changes": {
            "files": [args.target],
            "lines_changed": (content.count("\n") + 1) if content else 0,
        },
        "result": {
            "status": "success",
            "regression_required": False,
        },
    }
    opath = os.path.join(odir, "%s.yaml" % opid)
    with open(opath, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(op))
    print("WROTE: %s" % full)
    print("OPERATION MANIFEST: %s" % opath)
    print("OK")
    sys.exit(0)


if __name__ == "__main__":
    main()

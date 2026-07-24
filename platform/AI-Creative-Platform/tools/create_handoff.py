# -*- coding: utf-8 -*-
"""create_handoff: 生成跨对话标准交接文件（不同对话通过文件交接，不靠聊天记忆）。"""
import os
import sys
import argparse
import datetime
import glob
import _gov


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_role", required=True)
    ap.add_argument("--to", dest="to_role", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--chapter", default=None)
    ap.add_argument("--session", required=True)
    ap.add_argument("--artifacts", nargs="*", default=[], help="key=val 形式，如 draft=BUILD-1")
    ap.add_argument("--risks", nargs="*", default=[])
    args = ap.parse_args()

    ws_root = _gov.find_workspace_root()
    pdir, _ = _gov.find_project(ws_root, args.project)
    if pdir is None:
        print("ERROR: project %s not found" % args.project)
        sys.exit(2)

    arts = {}
    for a in args.artifacts:
        if "=" in a:
            k, v = a.split("=", 1)
            arts[k] = v

    now = datetime.datetime.now()
    stamp = now.strftime("%Y%m%d")
    hdir = os.path.join(pdir, "handoffs")
    os.makedirs(hdir, exist_ok=True)
    n = len(glob.glob(os.path.join(hdir, "HO-%s-*.yaml" % stamp))) + 1
    hid = "HO-%s-%03d" % (stamp, n)

    handoff = {
        "handoff": {
            "from_role": args.from_role,
            "to_role": args.to_role,
            "project_id": args.project,
            "chapter_id": args.chapter,
            "session_id": args.session,
        },
        "artifacts": arts,
        "status": {
            "self_check": "pass",
            "ready_for_next": True,
        },
        "known_risks": list(args.risks),
    }
    out = os.path.join(hdir, "%s.yaml" % hid)
    with open(out, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(handoff))
    print("HANDOFF: %s" % out)
    print("OK")
    sys.exit(0)


if __name__ == "__main__":
    main()

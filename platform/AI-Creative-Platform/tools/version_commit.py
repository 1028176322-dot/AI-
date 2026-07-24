# -*- coding: utf-8 -*-
"""内容版本控制：versions/<type>/<id>.yaml（Version Control）。

CLI：platform ver --project-root <root> <commit|log|rollback>
每次内容修改产生一条 revision，支持回滚与追溯。
"""
import os
import sys
import argparse
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _gov
import audit_log

ARTIFACT_TYPES = ["chapter", "nkb", "outline", "world"]


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _path(project_root, artifact_type, artifact_id):
    d = os.path.join(project_root, "versions", artifact_type)
    return d, os.path.join(d, artifact_id + ".yaml")


def commit(project_root, artifact_type, artifact_id, after, before=None,
           reason="", approved=True, author="unknown", model="unknown"):
    if artifact_type not in ARTIFACT_TYPES:
        raise ValueError("unknown artifact_type: %s" % artifact_type)
    d, p = _path(project_root, artifact_type, artifact_id)
    os.makedirs(d, exist_ok=True)
    data = (_gov.load_yaml(p) if os.path.isfile(p) else None) or {
        "meta": {"artifact_type": artifact_type, "artifact_id": artifact_id},
        "revisions": [],
    }
    revs = data.setdefault("revisions", [])
    prev = revs[-1]["after"] if revs else None
    if before is None:
        before = prev
    n = len(revs) + 1
    rid = "REV-%s-%02d" % (artifact_id, n)
    rev = {
        "id": rid, "before": before, "after": after,
        "reason": reason, "approved": approved, "author": author,
        "created": _now(),
    }
    revs.append(rev)
    with open(p, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(data))
    audit_log.record(project_root, "ver_commit", agent=author, model=model,
                     files=[os.path.relpath(p, project_root)],
                     result="success", detail="%s %s" % (rid, reason))
    return rev


def log(project_root, artifact_type, artifact_id):
    _, p = _path(project_root, artifact_type, artifact_id)
    if not os.path.isfile(p):
        return []
    data = _gov.load_yaml(p) or {}
    return data.get("revisions") or []


def rollback(project_root, artifact_type, artifact_id, rev_id, author="unknown", model="unknown"):
    _, p = _path(project_root, artifact_type, artifact_id)
    if not os.path.isfile(p):
        raise FileNotFoundError(p)
    data = _gov.load_yaml(p)
    revs = data.get("revisions") or []
    target = next((r for r in revs if r["id"] == rev_id), None)
    if not target:
        raise KeyError("revision not found: %s" % rev_id)
    n = len(revs) + 1
    rid = "REV-%s-%02d" % (artifact_id, n)
    rev = {
        "id": rid, "before": revs[-1]["after"], "after": target["after"],
        "reason": "rollback to %s" % rev_id, "approved": True,
        "author": author, "created": _now(),
    }
    revs.append(rev)
    with open(p, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(data))
    audit_log.record(project_root, "ver_rollback", agent=author, model=model,
                     files=[os.path.relpath(p, project_root)],
                     result="success", detail="%s <- %s" % (rid, rev_id))
    return rev


def main():
    ap = argparse.ArgumentParser(prog="ver", description="内容版本控制")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("verb", choices=["commit", "log", "rollback"])
    ap.add_argument("--type", choices=ARTIFACT_TYPES, default="chapter")
    ap.add_argument("--id", required=True)
    ap.add_argument("--after", default=None)
    ap.add_argument("--before", default=None)
    ap.add_argument("--reason", default="")
    ap.add_argument("--approved", default="true")
    ap.add_argument("--author", default="unknown")
    ap.add_argument("--model", default="unknown")
    ap.add_argument("--rev", default=None)
    args = ap.parse_args()

    if args.verb == "commit":
        if not args.after:
            ap.error("commit requires --after")
        r = commit(args.project_root, args.type, args.id, args.after,
                   before=args.before, reason=args.reason,
                   approved=(args.approved.lower() != "false"),
                   author=args.author, model=args.model)
        print("✓ committed %s (%s)" % (r["id"], r["after"]))
    elif args.verb == "log":
        revs = log(args.project_root, args.type, args.id)
        if not revs:
            print("# 无版本记录: %s/%s" % (args.type, args.id))
        for r in revs:
            print("  %s  %s -> %s  [%s] %s" % (r["id"], r["before"], r["after"],
                                              "approved" if r["approved"] else "pending", r["reason"]))
    elif args.verb == "rollback":
        if not args.rev:
            ap.error("rollback requires --rev")
        r = rollback(args.project_root, args.type, args.id, args.rev,
                     author=args.author, model=args.model)
        print("✓ rolled back to %s via %s" % (args.rev, r["id"]))


if __name__ == "__main__":
    main()

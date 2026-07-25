# -*- coding: utf-8 -*-
"""项目状态读写：project/status.yaml（Project Status Management）。

CLI：platform status --project-root <root> <init|show|set|block>
单一事实源：AI 不再猜「现在写到哪」，直接读 current。
"""
import os
import sys
import argparse
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _gov
import status_derive

STAGE_ENUM = ["idea", "evaluating", "initiated", "defining", "designing",
              "preparing_knowledge", "readiness_review", "ready_for_writing",
              "writing", "completed", "archived"]


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _path(project_root):
    return os.path.join(project_root, "project", "status.yaml")


def _default_pid(project_root):
    py = os.path.join(project_root, "project.yaml")
    if os.path.isfile(py):
        d = _gov.load_yaml(py) or {}
        return (d.get("project") or {}).get("id") or d.get("id") or "unknown"
    return "unknown"


def load(project_root):
    p = _path(project_root)
    if not os.path.isfile(p):
        return None
    return _gov.load_yaml(p)


def _write(project_root, data):
    data = dict(data)
    data["updated"] = _now()
    os.makedirs(os.path.dirname(_path(project_root)), exist_ok=True)
    with open(_path(project_root), "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(data))


def init(project_root, project_id=None, stage="writing", by="status-updater"):
    pid = project_id or _default_pid(project_root)
    data = {
        "project": {"id": pid},
        "lifecycle": {"stage": stage},
        "phases": {
            "idea": "completed", "initiation": "completed", "design": "completed",
            "nkb_genesis": "completed", "readiness": "completed",
            "writing": "active", "publishing": "pending",
        },
        "current": {
            "volume": {"id": None, "name": None},
            "chapter": {"current": None, "title": None, "workflow_current_step": None},
            "blocked": False, "blocked_reason": None,
        },
        "updated_by": by,
    }
    _write(project_root, data)
    return data


def set_step(project_root, chapter=None, title=None, step=None,
             blocked=None, reason=None, by="task-system"):
    data = load(project_root) or init(project_root, by=by)
    cur = data.setdefault("current", {})
    ch = cur.setdefault("chapter", {})
    if chapter is not None:
        ch["current"] = chapter
    if title is not None:
        ch["title"] = title
    if step is not None:
        ch["workflow_current_step"] = step
    if blocked is not None:
        cur["blocked"] = blocked
        if blocked:
            if reason is not None:
                cur["blocked_reason"] = reason
        else:
            cur["blocked_reason"] = None
    data["updated_by"] = by
    _write(project_root, data)
    return data


def show(project_root):
    data = load(project_root)
    if not data:
        print("# 无 project/status.yaml，请先运行: platform status --project-root <root> init")
        return
    print(_gov.dump_block(data))


def main():
    ap = argparse.ArgumentParser(prog="status", description="项目状态管理")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("verb", choices=["init", "show", "set", "block", "derive"])
    ap.add_argument("--stage", default=None)
    ap.add_argument("--chapter", default=None)
    ap.add_argument("--title", default=None)
    ap.add_argument("--step", default=None)
    ap.add_argument("--reason", default=None)
    args = ap.parse_args()

    if args.verb == "init":
        d = init(args.project_root, stage=args.stage or "writing")
        print("✓ status init: stage=%s" % d["lifecycle"]["stage"])
    elif args.verb == "show":
        show(args.project_root)
    elif args.verb == "set":
        set_step(args.project_root, chapter=args.chapter, title=args.title,
                 step=args.step, by="status-updater")
        print("✓ status updated")
        show(args.project_root)
    elif args.verb == "block":
        set_step(args.project_root, blocked=True, reason=args.reason, by="status-updater")
        print("✓ blocked: %s" % (args.reason or ""))
    elif args.verb == "derive":
        # PC-3：从任务系统 + NKB 派生状态（不手填），落在 project/status.derived.yaml
        res = status_derive.derive(args.project_root, write=True)
        print("✓ status derived -> %s" % status_derive._path(args.project_root))
        print(_gov.dump_block(res))


if __name__ == "__main__":
    main()

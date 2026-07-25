# -*- coding: utf-8 -*-
"""chapter_cli — 章节发布与生命周期诊断命令组（platform chapter ...）

子命令：
  publish         执行 chapter_publish 任务的原子发布（Publish Service）
  workflow        查看章节在 canonical_manifest 中的生命周期态 / revision / hash
  canonical-writes 审计 canonical 正式正文：是否全部经 Publish Service 落盘、有无篡改
  rollback        事故回滚到历史 revision（canonical.rollback 服务动作）

编辑≠发布：writer/fixer 只写工作副本；canonical 仅本命令经授权任务落地。
"""
import os
import sys
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(HERE)
if os.path.isdir(_SCRIPTS):
    for _d in os.listdir(_SCRIPTS):
        _p = os.path.join(_SCRIPTS, _d)
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import publish_chapter as PC
import manifest as MF
import auth_engine as AE


def _canon_files(project_root):
    out = []
    for d in sorted(os.listdir(project_root)):
        dp = os.path.join(project_root, d)
        if not os.path.isdir(dp):
            continue
        import re
        if not re.match(r"^第.卷_", d):
            continue
        for fn in sorted(os.listdir(dp)):
            if fn.endswith(".md") or fn.endswith(".txt"):
                out.append("%s/%s" % (d, fn))
    return out


def cmd_publish(args):
    try:
        entry = PC.publish(args.project_root, args.task_id, role=args.role,
                           agent=args.agent, model=args.model)
    except Exception as e:
        print("PUBLISH FAILED: %s" % e)
        sys.exit(1)
    print("PUBLISH OK: %s r%d (hash=%s)" % (entry["path"], entry["revision"], entry["hash"][:10]))
    sys.exit(0)


def cmd_workflow(args):
    entries = MF.list_entries(args.project_root)
    if args.chapter:
        e = entries.get(args.chapter.replace("\\", "/"))
        print(json.dumps(e or {"error": "not published yet"}, ensure_ascii=False, indent=2))
        return
    rows = []
    for k, v in sorted(entries.items()):
        rows.append({"path": k, "status": v.get("status"), "revision": v.get("revision"),
                     "hash": (v.get("hash") or "")[:10], "source": v.get("source"),
                     "versions": len(v.get("versions", []))})
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def cmd_canonical_writes(args):
    """审计 canonical：每个正式文件是否都在 manifest 且 hash 一致（防篡改 / 防直写）。"""
    root = args.project_root
    files = _canon_files(root)
    entries = MF.list_entries(root)
    findings = []
    for f in files:
        e = entries.get(f)
        absf = os.path.join(root, f)
        cur_hash = MF.hash_content(open(absf, "r", encoding="utf-8").read()) if os.path.isfile(absf) else None
        if not e:
            findings.append({"check": "canonical_writes", "severity": "fail",
                             "detail": "canonical 文件 %s 不在 manifest（疑似未经 Publish Service 直写）" % f})
        elif cur_hash != e.get("hash"):
            findings.append({"check": "canonical_writes", "severity": "fail",
                             "detail": "canonical %s 当前 hash(%s) 与 manifest(%s) 不一致（疑似篡改）"
                             % (f, (cur_hash or "")[:10], (e.get("hash") or "")[:10])})
        else:
            findings.append({"check": "canonical_writes", "severity": "info",
                             "detail": "canonical %s 经 Publish Service 落盘且 hash 一致 r%d" % (f, e.get("revision"))})
    # manifest 中但文件缺失
    for k in entries:
        if k not in files and not os.path.isfile(os.path.join(root, k)):
            findings.append({"check": "canonical_writes", "severity": "warn",
                             "detail": "manifest 记录 %s 但文件缺失" % k})
    if not findings:
        findings = [{"check": "canonical_writes", "severity": "info", "detail": "无 canonical 文件"}]
    print(json.dumps(findings, ensure_ascii=False, indent=2))


def cmd_rollback(args):
    try:
        entry = PC.rollback(args.project_root, args.task_id, args.target,
                            args.to_revision, role=args.role, agent=args.agent, model=args.model)
    except Exception as e:
        print("ROLLBACK FAILED: %s" % e)
        sys.exit(1)
    print("ROLLBACK OK: %s r%d" % (entry["path"], entry["revision"]))
    sys.exit(0)


def cmd_backfill(args):
    """迁移：把现存 canonical 正式章节回填进 manifest（source=legacy），建立基线。

    既有正式章节在 Publish Service 之前已落盘，未登记进 manifest；回填后
    canonical-writes 审计不再误报，且后续 Publish Service 发布会在此基础上递增 revision。
    """
    root = args.project_root
    files = _canon_files(root)
    entries = MF.list_entries(root)
    n_new, n_skip = 0, 0
    for f in files:
        if f in entries:
            n_skip += 1
            continue
        af = os.path.join(root, f)
        if not os.path.isfile(af):
            continue
        content = open(af, "r", encoding="utf-8").read()
        MF.record_publish(root, f, "legacy-pre-manifest", content, prev_status="published")
        n_new += 1
    print("BACKFILL: 新增 %d，已存在跳过 %d，总计 %d 个 canonical 文件" % (n_new, n_skip, len(files)))
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser(prog="chapter", description="章节发布与生命周期诊断")
    sub = ap.add_subparsers(dest="op")
    p = sub.add_parser("publish", help="执行 chapter_publish 任务原子发布")
    p.add_argument("--project-root", required=True)
    p.add_argument("--task-id", required=True)
    p.add_argument("--role", default="publish_service")
    p.add_argument("--agent", default="publish_service")
    p.add_argument("--model", default="platform")
    p.set_defaults(func=cmd_publish)

    w = sub.add_parser("workflow", help="查看章节生命周期态")
    w.add_argument("--project-root", required=True)
    w.add_argument("--chapter", default=None)
    w.set_defaults(func=cmd_workflow)

    c = sub.add_parser("canonical-writes", help="审计 canonical 是否全部经 Publish Service")
    c.add_argument("--project-root", required=True)
    c.set_defaults(func=cmd_canonical_writes)

    r = sub.add_parser("rollback", help="事故回滚到历史 revision")
    r.add_argument("--project-root", required=True)
    r.add_argument("--task-id", required=True)
    r.add_argument("--target", required=True)
    r.add_argument("--to-revision", type=int, required=True)
    r.add_argument("--role", default="publish_service")
    r.add_argument("--agent", default="publish_service")
    r.add_argument("--model", default="platform")
    r.set_defaults(func=cmd_rollback)

    b = sub.add_parser("backfill", help="迁移：把现存 canonical 章节回填进 manifest 建立基线")
    b.add_argument("--project-root", required=True)
    b.set_defaults(func=cmd_backfill)

    args = ap.parse_args()
    if not getattr(args, "op", None):
        ap.print_help()
        sys.exit(2)
    args.func(args)


if __name__ == "__main__":
    main()

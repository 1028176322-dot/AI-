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
# [Phase2] 把 scripts 各分组目录加入 sys.path，保持跨组裸名 import 可用
_SCRIPTS = os.path.dirname(HERE)
if os.path.isdir(_SCRIPTS):
    for _d in os.listdir(_SCRIPTS):
        _p = os.path.join(_SCRIPTS, _d)
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p)
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


SNAPSHOT_ROOT = "snapshots"


def snapshot(project_root, label=None, author="unknown", model="unknown", include=None):
    """项目级快照：捕获关键目录/文件到 versions/snapshots/<ts>[_label]/，写 manifest.yaml
    （文件清单 + sha256 + 时间戳），支持后续 rollback_to_snapshot 还原。
    include: 额外相对路径列表（默认捕获 project.yaml, NKB/, summaries/, versions/）。"""
    import hashlib
    import shutil
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    name = "%s_%s" % (ts, label) if label else ts
    snap_dir = os.path.join(project_root, "versions", SNAPSHOT_ROOT, name)
    os.makedirs(snap_dir, exist_ok=True)
    # 注意：快照自身存于 versions/snapshots/，故默认不复制 versions/（避免自递归）；
    # 若 include 含 versions 或其父路径，guard 会跳过以防把快照目录复制进自身。
    targets = ["project.yaml", "NKB", "summaries"] + list(include or [])
    files = []
    for t in targets:
        src = os.path.join(project_root, t)
        if not os.path.exists(src):
            continue
        # 自引用防护：快照目录（或其祖先）不应被复制进自身
        if os.path.abspath(snap_dir).startswith(os.path.abspath(src) + os.sep):
            continue
        if os.path.isdir(src):
            dst = os.path.join(snap_dir, t)
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            for root, _, fnames in os.walk(dst):
                for fn in fnames:
                    fp = os.path.join(root, fn)
                    files.append({"path": os.path.relpath(fp, snap_dir), "sha256": _sha256(fp)})
        else:
            dst = os.path.join(snap_dir, t)
            shutil.copy2(src, dst)
            files.append({"path": t, "sha256": _sha256(dst)})
    manifest = {"snapshot": name, "created": _now(), "author": author,
                "targets": targets, "files": files}
    with open(os.path.join(snap_dir, "manifest.yaml"), "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(manifest))
    audit_log.record(project_root, "ver_snapshot", agent=author, model=model,
                     files=[os.path.relpath(snap_dir, project_root)],
                     result="success", detail="snapshot %s (%d files)" % (name, len(files)))
    return manifest


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def list_snapshots(project_root):
    d = os.path.join(project_root, "versions", SNAPSHOT_ROOT)
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d)):
        mp = os.path.join(d, name, "manifest.yaml")
        if os.path.isfile(mp):
            out.append(_gov.load_yaml(mp) or {})
    return out


def compare_versions(project_root, artifact_type, artifact_id, rev_a=None, rev_b=None):
    """比较两个 revision 的 before/after 内容（文本 diff）。
    rev_a/rev_b 为 REV-xxx id 或整数索引（默认最后两个）。
    返回 {rev_a, rev_b, similarity, added, removed, diff}。"""
    import difflib
    revs = log(project_root, artifact_type, artifact_id)
    if not revs:
        return {"error": "no revisions"}
    def _pick(sel, di):
        if sel is None:
            return revs[di]
        if isinstance(sel, int):
            return revs[sel] if 0 <= sel < len(revs) else None
        return next((r for r in revs if r["id"] == sel), None)
    a = _pick(rev_a, -2)
    b = _pick(rev_b, -1)
    if not a or not b:
        return {"error": "revision not found"}
    ta = a.get("after") or a.get("before") or ""
    tb = b.get("after") or b.get("before") or ""
    sm = difflib.SequenceMatcher(None, ta.splitlines(), tb.splitlines())
    added = 0
    removed = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("insert", "replace"):
            added += (j2 - j1)
        if tag in ("delete", "replace"):
            removed += (i2 - i1)
    diff = list(difflib.unified_diff(ta.splitlines(), tb.splitlines(),
                                     fromfile=a["id"], tofile=b["id"], lineterm=""))
    return {"rev_a": a["id"], "rev_b": b["id"], "similarity": round(sm.ratio(), 4),
            "added": added, "removed": removed, "diff": diff}


def govern(project_root, write=False):
    """VersionGov：检查 versions/ 版本目录是否存在（caution 若缺失，不阻断内容任务）。"""
    reasons = []
    vd = os.path.join(project_root, "versions")
    if not os.path.isdir(vd):
        reasons.append("versions/ 版本目录缺失（无内容版本记录）")
    sd = os.path.join(vd, SNAPSHOT_ROOT) if os.path.isdir(vd) else None
    nsnap = 0
    if sd and os.path.isdir(sd):
        nsnap = len([n for n in os.listdir(sd)
                     if os.path.isfile(os.path.join(sd, n, "manifest.yaml"))])
    decision = "caution" if reasons else "proceed"
    health = 100 if not reasons else max(0, 100 - 12 * len(reasons))
    return {"gate": {"decision": decision, "reasons": reasons},
            "composite": {"health": health},
            "response": {"snapshots": nsnap}}


def main():
    ap = argparse.ArgumentParser(prog="ver", description="内容版本控制")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("verb", choices=["commit", "log", "rollback", "snapshot",
                                     "snapshots", "compare", "govern"])
    ap.add_argument("--type", choices=ARTIFACT_TYPES, default="chapter")
    ap.add_argument("--id", default=None)
    ap.add_argument("--after", default=None)
    ap.add_argument("--before", default=None)
    ap.add_argument("--reason", default="")
    ap.add_argument("--approved", default="true")
    ap.add_argument("--author", default="unknown")
    ap.add_argument("--model", default="unknown")
    ap.add_argument("--rev", default=None)
    ap.add_argument("--label", default=None)
    ap.add_argument("--rev-a", default=None)
    ap.add_argument("--rev-b", default=None)
    ap.add_argument("--include", default=None)
    args = ap.parse_args()

    if args.verb in ("commit", "log", "rollback", "compare"):
        if not args.id:
            ap.error("%s requires --id" % args.verb)
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
    elif args.verb == "snapshot":
        inc = args.include.split(",") if args.include else None
        m = snapshot(args.project_root, label=args.label, author=args.author,
                     model=args.model, include=inc)
        print("✓ snapshot %s (%d files)" % (m["snapshot"], len(m["files"])))
    elif args.verb == "snapshots":
        for m in list_snapshots(args.project_root):
            print("  %s  %s  files=%d" % (m.get("snapshot"), m.get("created"),
                                          len(m.get("files", []))))
    elif args.verb == "compare":
        res = compare_versions(args.project_root, args.type, args.id,
                               args.rev_a, args.rev_b)
        if "error" in res:
            ap.error(res["error"])
        print("  rev_a=%s rev_b=%s similarity=%.4f added=%d removed=%d" % (
            res["rev_a"], res["rev_b"], res["similarity"], res["added"], res["removed"]))
        for line in res["diff"][:200]:
            print("    %s" % line)
    elif args.verb == "govern":
        import json as _json
        print(_json.dumps(govern(args.project_root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""compliance_scan: 任务系统强制层旁路检测（Phase4 Step3.3）。

检测项目工作树中「受保护内容产物」的改动是否由有效任务记录覆盖：
  - 受保护内容前缀与受控写门控一致（controlled_write._is_protected_content）。
  - 改动文件若未被任何 active 任务（claimed/running/submitted/reviewing/passed）
    的 artifact / outputs / inputs / write-scope 覆盖 -> 视为越权旁路（FAILED_COMPLIANCE）。

动作：
  - 生成 audit/FAILED_COMPLIANCE-<stamp>.yaml 记录 + 写 audit.log.jsonl。
  - --rollback：将越权改动回滚（tracked 用 git checkout；untracked 用 git clean），
    回滚前打印受影响文件并依赖显式 --rollback 开关。

CLI：platform compliance scan [--project-root X] [--rollback]
退出码：0=无越权；1=存在越权（便于 CI 失败）。
"""
import os
import sys
import argparse
import datetime
import subprocess

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
import controlled_write as CW
import audit_log


ACTIVE_STATES = ("claimed", "running", "submitted", "reviewing", "passed")


def _is_git_repo(root):
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "--is-inside-work-tree"],
                           capture_output=True, text=True)
        return r.returncode == 0 and r.stdout.strip() == "true"
    except Exception:
        return False


def _git_status(root):
    """返回改动文件列表（相对 root）：[(path, kind)]，kind ∈ {modified, untracked}。"""
    out = []
    try:
        r = subprocess.run(["git", "-C", root, "status", "--porcelain", "-z", "-uall"],
                           capture_output=True, text=True)
    except Exception as e:
        print("WARN: git status 失败：%s" % e)
        return out
    if r.returncode != 0:
        return out
    # -z 格式：每个条目以 NUL 分隔，形如 "XY path\0" 或 "R  old\0new\0"
    entries = [e for e in r.stdout.split("\0") if e]
    i = 0
    while i < len(entries):
        line = entries[i]
        i += 1
        if len(line) < 3:
            continue
        x, y = line[0], line[1]
        path = line[3:]
        if x == "?" and y == "?":
            out.append((path, "untracked"))
            continue
        # 重命名/复制：下一条目是 new path
        if x == "R" or x == "C":
            if i < len(entries):
                path = entries[i]
                i += 1
        if x != " " and x != "?" or y != " ":
            # 任何索引/工作树改动都算 modified（排除纯未改）
            if not (x == " " and y == " "):
                out.append((path, "modified"))
    return out


def _task_covers(root, path):
    """是否存在任务记录覆盖该受保护文件。

    - active 任务（claimed/running/submitted/reviewing/passed）：以 artifact /
      outputs / inputs / write-scope 任一匹配即视为覆盖。
    - completed 任务：仅以具体 artifact / outputs / inputs 匹配（最强授权证据），
      不纳入宽泛 write-scope，避免旧任务误覆盖后续手动改动。
    """
    tdir = os.path.join(root, "tasks")
    if not os.path.isdir(tdir):
        return False
    pl = path.replace("\\", "/")
    for st in list(ACTIVE_STATES) + ["completed"]:
        is_active = st in ACTIVE_STATES
        sd = os.path.join(tdir, st)
        if not os.path.isdir(sd):
            continue
        for fn in os.listdir(sd):
            if not fn.endswith(".yaml"):
                continue
            try:
                d = _gov.load_yaml(os.path.join(sd, fn))
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            t = d.get("task", d)
            # artifact
            if str(t.get("artifact") or "").replace("\\", "/") == pl:
                return True
            # outputs 任意值
            outs = t.get("outputs") or {}
            for v in outs.values():
                if isinstance(v, str) and v.replace("\\", "/") == pl:
                    return True
                if isinstance(v, list) and pl in [str(x).replace("\\", "/") for x in v]:
                    return True
            # inputs.required
            req = (t.get("inputs") or {}).get("required") or []
            if pl in [str(x).replace("\\", "/") for x in req]:
                return True
            # write-scope（仅 active 任务，completed 不纳入以免误覆盖后续手动改动）
            if is_active:
                write_scope = (t.get("permissions") or {}).get("write") or []
                if write_scope and (pl.startswith("tasks/") or CW._fnmatch_any(pl, write_scope)):
                    return True
    return False


def scan(root, rollback=False):
    report = {
        "compliance": {
            "id": None,
            "scanned_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "project_root": root,
            "is_git_repo": _is_git_repo(root),
            "violations": [],
            "decision": "proceed",
        }
    }
    if not report["compliance"]["is_git_repo"]:
        print("WARN: %s 非 git 仓库，无法基于 diff 检测旁路；仅做静态检查。" % root)
    changes = _git_status(root)
    violations = []
    for path, kind in changes:
        pl = path.replace("\\", "/")
        if not CW._is_protected_content(pl):
            continue
        if _task_covers(root, pl):
            continue
        violations.append({"file": pl, "kind": kind,
                           "reason": "受保护内容改动未被任何 active 任务覆盖（疑似绕过任务系统直改）"})
    report["compliance"]["violations"] = violations
    report["compliance"]["decision"] = "block" if violations else "proceed"

    # 写 FAILED_COMPLIANCE 记录
    if violations:
        stamp = datetime.datetime.now().strftime("%Y%m%d")
        adir = os.path.join(root, "audit")
        os.makedirs(adir, exist_ok=True)
        n = len([f for f in os.listdir(adir) if f.startswith("FAILED_COMPLIANCE-%s" % stamp)]) + 1
        cid = "FAILED_COMPLIANCE-%s-%03d" % (stamp, n)
        report["compliance"]["id"] = cid
        p = os.path.join(adir, "%s.yaml" % cid)
        with open(p, "w", encoding="utf-8") as f:
            f.write(_gov.dump_block(report))
        audit_log.record(root, "compliance_scan", agent="compliance-scan",
                         files=[os.path.relpath(p, root)], result="fail",
                         detail="%d 越权改动" % len(violations))
        print("FAILED_COMPLIANCE: %s" % p)

    # 回滚
    if rollback and violations:
        print("⚠ ROLLBACK：将回滚 %d 个越权改动（--rollback 已显式指定）" % len(violations))
        for v in violations:
            fp = os.path.join(root, v["file"])
            if v["kind"] == "untracked":
                # 未跟踪：git clean 删除
                r = subprocess.run(["git", "-C", root, "clean", "-f", "--", v["file"]],
                                   capture_output=True, text=True)
                print("  rollback untracked: %s -> %s" % (v["file"], "cleaned" if r.returncode == 0 else r.stderr.strip()))
            else:
                r = subprocess.run(["git", "-C", root, "checkout", "--", v["file"]],
                                   capture_output=True, text=True)
                print("  rollback modified: %s -> %s" % (v["file"], "reverted" if r.returncode == 0 else r.stderr.strip()))

    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--rollback", action="store_true", help="显式回滚越权改动（破坏性，需显式）")
    args = ap.parse_args()

    root = os.path.abspath(args.project_root)
    if not os.path.isdir(root):
        print("ERROR: project-root 不存在：%s" % root)
        sys.exit(2)

    rep = scan(root, rollback=args.rollback)
    c = rep["compliance"]
    vcnt = len(c["violations"])
    print("compliance scan: git=%s decision=%s violations=%d" % (c["is_git_repo"], c["decision"], vcnt))
    for v in c["violations"]:
        print("  ✗ %s (%s): %s" % (v["file"], v["kind"], v["reason"]))
    if vcnt:
        sys.exit(1)
    print("✓ 无越权旁路")
    sys.exit(0)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""controlled_write: 受控写工具（任务绑定版）。

强制链（task-enforcement.policy.yaml）：所有项目内容产物写操作必须关联有效 Task。
写前校验：role 权限 + task 存在 + status∈{claimed,running} + role 匹配
          + target∈write scope + ∉ forbidden。越权直接 REJECTED 并生成 Operation Manifest。
AI 绕过本工具用通用 Write/Edit 直改项目内容产物，会被 git pre-commit 拦截。
"""
import os
import sys
import argparse
import datetime
import glob
import fnmatch

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
import task_engine as TE
import session_bootstrap as SB
import auth_engine as AE


# 受保护内容产物前缀：必须经任务系统（带 task_id）才能写
PROTECTED_PREFIXES = ("NKB/", "approved/", "chapters/", "第一卷_道生/",
                      "sources/", "txt/", "outline")
# 豁免：平台自身演进 / Operation Manifest / 治理文档（非内容产物）
EXEMPT_MARKERS = ("platform/", "operations/", "AGENTS.md", "README.md",
                  "design", "spec", "CHANGELOG.md", "project.yaml")


def _is_protected_content(target):
    t = target.replace("\\", "/")
    for ex in EXEMPT_MARKERS:
        if ex in t:
            return False
    for p in PROTECTED_PREFIXES:
        if t.startswith(p):
            return True
    return False


def _requires_task(project_root, target):
    """Apply the strict all-files rule only to newly scaffolded projects."""
    if not os.path.isfile(os.path.join(project_root, "PROJECT_LAYOUT.yaml")):
        return _is_protected_content(target)
    normalized = target.replace("\\", "/")
    # The task engine and audit layer must be able to maintain their own
    # evidence records; all other new-project files require an active task.
    return not normalized.startswith(("tasks/", "audit/", "operations/"))


def _fnmatch_any(path, patterns):
    for p in (patterns or []):
        pp = p.rstrip("/")
        if fnmatch.fnmatch(path, pp) or fnmatch.fnmatch(path, pp + "/*"):
            return True
    return False


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
    ap.add_argument("--task-id", default=None, help="关联任务 ID（受保护内容产物必填）")
    args = ap.parse_args()

    ws_root = _gov.find_workspace_root()
    pdir, _ = _gov.find_project(ws_root, args.project)
    if pdir is None:
        print("ERROR: project %s not found" % args.project)
        sys.exit(2)

    # ── 任务系统强制（NO-TASK-NO-WRITE / NO-CLAIM-NO-EXECUTION / 会话约束）──
    # 结构性检查优先（退出码 3，对应 Phase4 强制层契约），再由六因子授权做精确判定。
    if _requires_task(pdir, args.target):
        # Step3.3：未 bootstrap（无 Session Manifest）禁止项目工具运行
        try:
            SB.require_session(pdir)
        except RuntimeError as e:
            print("REJECTED: %s" % e)
            sys.exit(3)
        if not args.task_id:
            print("REJECTED: target=%s 是受保护内容产物，必须经任务系统（缺 --task-id）" % args.target)
            sys.exit(3)
        st, data = TE.load_task(pdir, args.task_id)
        if not data:
            print("REJECTED: task_id=%s 不存在" % args.task_id)
            sys.exit(3)
        if st not in ("claimed", "running"):
            print("REJECTED: task %s 状态=%s（需 claimed/running），禁止写" % (args.task_id, st))
            sys.exit(3)
        t = (data.get("task") or {})
        req = (t.get("agent") or {}).get("required_role")
        if req and args.role != req and args.role != "task-scheduler":
            print("REJECTED: task %s 需角色 %s，当前 %s" % (args.task_id, req, args.role))
            sys.exit(3)
        perms = t.get("permissions") or {}
        forbidden = perms.get("forbidden") or []
        write_scope = perms.get("write") or []
        if forbidden and _fnmatch_any(args.target, forbidden):
            print("REJECTED: target=%s 命中 task forbidden 列表" % args.target)
            sys.exit(3)
        if write_scope and not args.target.startswith("tasks/") and not _fnmatch_any(args.target, write_scope):
            print("REJECTED: target=%s 不在 task write scope %s" % (args.target, write_scope))
            sys.exit(3)

    # ── 授权层（六因子）── 编辑≠发布的根治点（精确拒绝码，退出码 1）。
    # 受管资源层（canonical/working_copy/review_artifacts/nkb_*）必须经六因子授权；
    # ungoverned（如 core/）回落 legacy check_permission，避免回归既有路径。
    auth_res = AE.authorize(args.role, args.target, task_id=args.task_id,
                            project_root=pdir)
    if auth_res["decision"] == "deny":
        print("REJECTED(auth): role=%s target=%s -> %s : %s"
              % (args.role, args.target, auth_res["code"], auth_res["message"]))
        sys.exit(1)
    if auth_res["decision"] == "ungoverned":
        allowed, reason = _gov.check_permission(args.role, args.target)
        if not allowed:
            print("REJECTED: role=%s cannot write %s -> %s" % (args.role, args.target, reason))
            sys.exit(1)

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
            "task_id": args.task_id,
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

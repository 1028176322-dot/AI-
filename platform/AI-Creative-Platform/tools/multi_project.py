#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""multi_project.py — Phase 3-2 多项目管理（Multi-Project）

跨项目注册表 + 隔离等级解析（Global→Genre→Project→Chapter）+ 统一 dispatch。
零依赖：复用同目录 _yaml_lite / _gov；dispatch 协同 model_router。
不做创作，只做注册 / 查询 / 调度解析。
"""
import os
import re
import sys
import json
import argparse
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _yaml_lite
import _gov

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_STATUS_ENUM = ["active", "paused", "archived"]
_LEVELS = ["global", "genre", "project", "chapter"]


def _projects_path(platform_root):
    return os.path.join(platform_root, "registry", "projects.yaml")


def _load(platform_root):
    if not os.path.isfile(_projects_path(platform_root)):
        return None
    try:
        return _yaml_lite.load_file(_projects_path(platform_root))
    except Exception:
        return None


def load_registry(platform_root):
    return _load(platform_root) or {}


def list_projects(platform_root):
    reg = load_registry(platform_root)
    if not isinstance(reg, dict):
        return []
    return reg.get("projects") or []


def get_project(platform_root, project_id):
    for p in list_projects(platform_root):
        if isinstance(p, dict) and p.get("id") == project_id:
            return p
    return None


def _resolve_path(platform_root, rel):
    return os.path.normpath(os.path.join(platform_root, rel or ""))


# ── 注册 ────────────────────────────────────────────────
def register(platform_root, entry, write=False):
    """校验并追加一个项目条目。返回 (ok, errors, entry)。write=True 时回写 registry。"""
    errors = []
    if not isinstance(entry, dict):
        return False, ["entry 必须是 dict"], None
    pid = entry.get("id")
    if not pid:
        errors.append("缺少 id")
    elif not _ID_RE.match(str(pid)):
        errors.append("id 非法（须 ^[a-z0-9][a-z0-9_-]*$）")
    if not entry.get("path"):
        errors.append("缺少 path")
    if not entry.get("type"):
        errors.append("缺少 type")
    status = entry.get("status", "active")
    if status not in _STATUS_ENUM:
        errors.append("status 非法（须 active/paused/archived）")
    if errors:
        return False, errors, None

    reg = _load(platform_root) or {"schema_version": "1.0.0", "projects": []}
    projects = reg.get("projects") or []
    if any((isinstance(p, dict) and p.get("id") == pid) for p in projects):
        return False, ["id 已存在：%s" % pid], None

    clean = {
        "id": pid,
        "name": entry.get("name", pid),
        "path": entry.get("path"),
        "type": entry.get("type"),
        "genre": entry.get("genre", entry.get("type")),
        "status": status,
        "created": entry.get("created") or datetime.date.today().isoformat(),
        "overrides": entry.get("overrides") or {"model_preference": None},
    }
    projects.append(clean)
    reg["projects"] = projects

    if write:
        os.makedirs(os.path.dirname(_projects_path(platform_root)), exist_ok=True)
        with open(_projects_path(platform_root), "w", encoding="utf-8") as f:
            f.write(_gov.dump_block(reg))
    return True, [], clean


# ── 隔离等级解析 ────────────────────────────────────────
def resolve_isolation(platform_root, level, key=None, project_id=None):
    """按四级隔离（Global→Genre→Project→Chapter）解析事实源路径。

    返回 dict：{level, resolved_path, source_project, note}
    resolved_path 为相对 platform_root 的规范路径（事实应存放/已存放处）。
    """
    if level not in _LEVELS:
        return {"level": level, "resolved_path": None,
                "source_project": None, "note": "未知隔离等级"}
    if level == "global":
        return {
            "level": "global",
            "resolved_path": "memory/global",
            "source_project": None,
            "note": "全局经验/公理，跨项目共享（最高优先级一般事实源）",
        }
    if level == "genre":
        # 需要 genre 才能定位类型级模板/经验
        genre = None
        if project_id:
            p = get_project(platform_root, project_id)
            genre = p.get("genre") if p else None
        if not genre:
            return {"level": "genre", "resolved_path": None,
                    "source_project": None, "note": "缺少 genre（需 project_id 推断）"}
        return {
            "level": "genre",
            "resolved_path": "templates/%s" % genre,
            "source_project": None,
            "note": "类型级模板/经验（%s）" % genre,
        }
    if level == "project":
        if not project_id:
            return {"level": "project", "resolved_path": None,
                    "source_project": None, "note": "project 级需要 project_id"}
        p = get_project(platform_root, project_id)
        if not p:
            return {"level": "project", "resolved_path": None,
                    "source_project": project_id, "note": "未注册项目：%s" % project_id}
        return {
            "level": "project",
            "resolved_path": os.path.join(p["path"], "NKB").replace("\\", "/"),
            "source_project": project_id,
            "note": "项目级事实源（NKB / overrides）",
        }
    # chapter
    if not project_id:
        return {"level": "chapter", "resolved_path": None,
                "source_project": None, "note": "chapter 级需要 project_id"}
    p = get_project(platform_root, project_id)
    if not p:
        return {"level": "chapter", "resolved_path": None,
                "source_project": project_id, "note": "未注册项目：%s" % project_id}
    chap = key or "latest"
    return {
        "level": "chapter",
        "resolved_path": os.path.join(p["path"], "txt", chap).replace("\\", "/"),
        "source_project": project_id,
        "note": "章节级产物/上下文（%s）" % chap,
    }


# ── 统一 dispatch（协同 model-router） ──────────────────
def dispatch(platform_root, project_id, role=None, task_type=None,
             capability=None, quality_tier=None, cost_budget=None):
    """解析目标项目，叠加项目 overrides 后协同 model_router 给出模型。

    返回 dict：{project_id, project_path, model_resolution, project_overrides}
    """
    p = get_project(platform_root, project_id)
    if not p:
        return None
    proj_path = _resolve_path(platform_root, p.get("path"))
    overrides = p.get("overrides") or {}
    model_pref = overrides.get("model_preference")

    resolution = None
    try:
        import model_router as _mr
        resolution = _mr.resolve(
            platform_root, role=role, task_type=task_type, capability=capability,
            quality_tier=quality_tier, cost_budget=cost_budget)
    except Exception:
        resolution = None
    return {
        "project_id": project_id,
        "project_path": proj_path,
        "model_resolution": resolution,
        "project_overrides": {"model_preference": model_pref},
    }


# ── doctor 自检 ─────────────────────────────────────────
def govern(platform_root, write=False, proposed_by="unknown"):
    reg = _load(platform_root)
    fatal = []
    caution = []
    if not reg:
        fatal.append("registry/projects.yaml 缺失或不可解析")
    else:
        projects = reg.get("projects") or []
        seen = set()
        for p in projects:
            if not isinstance(p, dict):
                fatal.append("存在非 dict 项目条目")
                continue
            pid = p.get("id")
            if not pid or not _ID_RE.match(str(pid)):
                fatal.append("项目 id 非法或缺失：%s" % pid)
                continue
            if pid in seen:
                fatal.append("重复项目 id：%s" % pid)
            seen.add(pid)
            if not p.get("path"):
                fatal.append("项目 %s 缺少 path" % pid)
            if not p.get("type"):
                fatal.append("项目 %s 缺少 type" % pid)
            st = p.get("status", "active")
            if st not in _STATUS_ENUM:
                fatal.append("项目 %s status 非法：%s" % (pid, st))
            # path 存在性（相对 platform_root）
            pp = _resolve_path(platform_root, p.get("path"))
            if p.get("path") and not os.path.isdir(pp):
                fatal.append("项目 %s 路径不存在：%s" % (pid, p.get("path")))
            else:
                # 软问题：NKB 缺失
                nkb = os.path.join(pp, "NKB")
                if p.get("path") and not os.path.isdir(nkb):
                    caution.append("项目 %s 无 NKB 目录" % pid)
                if st in ("paused", "archived"):
                    caution.append("项目 %s 状态=%s（非活跃）" % (pid, st))

    if fatal:
        decision = "block"
    elif caution:
        decision = "caution"
    else:
        decision = "proceed"
    health = 100 - 40 * len(fatal) - 5 * len(caution)

    report = {
        "meta": {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "component": "multi-project",
            "version": "1.0.0",
            "platform_root": platform_root,
        },
        "request": {"project_id": None, "level": None},
        "response": {"projects": len(projects) if reg else 0},
        "decision": decision,
        "gate": {"decision": decision, "reasons": fatal + caution},
        "composite": {"health": health},
    }
    if write:
        out_dir = os.path.join(platform_root, "analysis", "multi-project")
        os.makedirs(out_dir, exist_ok=True)
        idx = 1
        for fn in os.listdir(out_dir):
            if fn.endswith(".yaml"):
                try:
                    n = int(fn.split("-")[-1].split(".")[0])
                    idx = max(idx, n + 1)
                except Exception:
                    pass
        out_path = os.path.join(out_dir, "MP-%02d.yaml" % idx)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    return report


# ── CLI ─────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(prog="multi_project", description="Phase 3-2 多项目管理")
    sub = ap.add_subparsers(dest="cmd")

    pl = sub.add_parser("list", help="列出已注册项目")
    pl.add_argument("--platform-root", required=True)

    pr = sub.add_parser("register", help="注册新项目（写回 registry/projects.yaml）")
    pr.add_argument("--platform-root", required=True)
    pr.add_argument("--id", required=True)
    pr.add_argument("--name", default=None)
    pr.add_argument("--path", required=True)
    pr.add_argument("--type", required=True)
    pr.add_argument("--genre", default=None)
    pr.add_argument("--status", default="active")
    pr.add_argument("--created", default=None)
    pr.add_argument("--model-preference", default=None)

    pq = sub.add_parser("query", help="隔离等级解析")
    pq.add_argument("--platform-root", required=True)
    pq.add_argument("--level", required=True)
    pq.add_argument("--project", default=None)
    pq.add_argument("--key", default=None)

    pd = sub.add_parser("dispatch", help="统一 dispatch（协同 model-router）")
    pd.add_argument("--platform-root", required=True)
    pd.add_argument("--project", required=True)
    pd.add_argument("--role", default=None)
    pd.add_argument("--task-type", default=None)
    pd.add_argument("--capability", default=None)
    pd.add_argument("--quality-tier", default=None)
    pd.add_argument("--cost-budget", default=None)

    pv = sub.add_parser("validate", help="doctor 自检")
    pv.add_argument("--platform-root", required=True)

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        sys.exit(2)

    if args.cmd == "list":
        ps = list_projects(args.platform_root)
        print(json.dumps(ps, ensure_ascii=False, indent=2))
        sys.exit(0)

    if args.cmd == "register":
        entry = {
            "id": args.id, "name": args.name, "path": args.path,
            "type": args.type, "genre": args.genre, "status": args.status,
            "created": args.created,
            "overrides": {"model_preference": args.model_preference},
        }
        ok, errs, clean = register(args.platform_root, entry, write=True)
        if not ok:
            print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False, indent=2))
            sys.exit(1)
        print(json.dumps({"ok": True, "entry": clean}, ensure_ascii=False, indent=2))
        sys.exit(0)

    if args.cmd == "query":
        r = resolve_isolation(args.platform_root, args.level,
                              key=args.key, project_id=args.project)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        sys.exit(0 if r.get("resolved_path") else 1)

    if args.cmd == "dispatch":
        r = dispatch(args.platform_root, args.project, role=args.role,
                     task_type=args.task_type, capability=args.capability,
                     quality_tier=args.quality_tier, cost_budget=args.cost_budget)
        if r is None:
            print(json.dumps({"error": "未注册项目：%s" % args.project}, ensure_ascii=False))
            sys.exit(1)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        sys.exit(0)

    if args.cmd == "validate":
        rep = govern(args.platform_root, write=False)
        print(json.dumps(rep["gate"], ensure_ascii=False, indent=2))
        sys.exit(1 if rep["gate"]["decision"] == "block" else 0)


if __name__ == "__main__":
    main()

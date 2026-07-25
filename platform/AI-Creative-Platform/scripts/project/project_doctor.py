#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""project_doctor.py — 初始化门禁（Section VI.9）

对（staging 或正式）项目根逐项检查 initialization_gate：
  directory_structure / project_yaml / version_lock / template_dependencies /
  nkb_schema / duplicate_ids / broken_references / memory_isolation /
  runtime_policy / initial_tasks / writable_scopes

返回 results[(name, symbol, detail)] 与 overall_ok。
用法：python project_doctor.py --project-root <dir>
API：  run(proot, platform_root) -> (results, overall_ok)
"""
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _installer_common as C


def _ok(name, b, detail):
    """统一返回 3 元组 (name, symbol, detail)。"""
    return (name, C.PASS if b else C.FAIL, detail)


def run(proot, platform_root):
    results = []

    # project.yaml
    py = os.path.join(proot, "project.yaml")
    if not os.path.isfile(py):
        results.append(("project_yaml", C.FAIL, "project.yaml 缺失"))
        return results, False
    data = C.load_yaml(py) or {}
    proj = data.get("project") or {}
    pid = proj.get("id")
    # genre 可能位于顶层 template.id 或 platform.template.id（installer 现状）
    genre = (data.get("template") or {}).get("id") \
        or (((data.get("platform") or {}).get("template") or {}) or {}).get("id")
    results.append(_ok("project_yaml",
                       bool(pid) and bool(genre),
                       "project.yaml 读入（id=%s, genre=%s）" % (pid, genre)))

    core_m, tpl_m, nkb_m, merr = (C.load_manifests(platform_root, genre)
                                  if genre else (None, None, None, "genre 缺失"))

    # directory_structure
    structure = (core_m.get("structure") or {}) if core_m else {}
    missing_dirs = []
    for e in (structure.get("initialize") or []):
        d = os.path.join(proot, e.get("path"))
        if not os.path.isdir(d):
            missing_dirs.append(e.get("path"))
    results.append(_ok("directory_structure",
                       not missing_dirs,
                       "目录结构完整" if not missing_dirs else "缺目录：%s" % ", ".join(missing_dirs[:5])))

    # version_lock
    lk = os.path.join(proot, "project.lock.yaml")
    lock_ok = os.path.isfile(lk)
    results.append(_ok("version_lock",
                       lock_ok,
                       "project.lock.yaml 存在" if lock_ok else "project.lock.yaml 缺失"))

    # template_dependencies
    if genre and core_m:
        tdir = os.path.join(platform_root, "templates", genre)
        tdep_ok = os.path.isdir(tdir) and os.path.isfile(os.path.join(tdir, "template-manifest.yaml"))
        results.append(_ok("template_dependencies", tdep_ok, "题材模板 %s 存在" % genre))
    else:
        results.append(("template_dependencies", C.FAIL, "genre 缺失"))

    # nkb_schema
    nkb_dir = os.path.join(proot, "NKB")
    if os.path.isdir(nkb_dir):
        comps = [c.get("name") for c in (nkb_m.get("components") or [])] if nkb_m else []
        present = [c for c in comps if os.path.isfile(os.path.join(nkb_dir, "%s.yaml" % c))]
        all_present = all(os.path.isfile(os.path.join(nkb_dir, "%s.yaml" % c)) for c in comps) if comps else False
        results.append(_ok("nkb_schema", all_present,
                           "NKB 组件齐全（%d/%d）" % (len(present), len(comps)) if comps else "NKB 无组件定义"))
    else:
        results.append(("nkb_schema", C.FAIL, "NKB 目录缺失"))

    # duplicate_ids（任务 id 唯一）
    dup = False
    ids = set()
    backlog = os.path.join(proot, "tasks", "backlog")
    if os.path.isdir(backlog):
        for f in os.listdir(backlog):
            if not f.endswith(".yaml"):
                continue
            d = C.load_yaml(os.path.join(backlog, f)) or {}
            t = d.get("task") or {}
            tid = t.get("id")
            if tid in ids:
                dup = True
            ids.add(tid)
    results.append(_ok("duplicate_ids", not dup, "任务 id 无重复（%d 个）" % len(ids)))

    # broken_references：reference 路径相对于「最终项目根」(ws_root/projects/<pid>)，
    # 即便在 staging 阶段也按最终根解析，确保门禁与正式位置一致。
    ws_root = os.path.dirname(os.path.dirname(platform_root))
    intended_root = os.path.join(ws_root, "projects", pid) if pid else proot
    refs = (structure.get("reference") or []) if structure else []
    broken = []
    for r in refs:
        rp = os.path.normpath(os.path.join(intended_root, r.get("path")))
        if not (os.path.isdir(rp) or os.path.isfile(rp)):
            broken.append(r.get("path"))
    results.append(_ok("broken_references", not broken,
                       "引用完整" if not broken else "断引用：%s" % ", ".join(broken[:3])))

    # memory_isolation
    mem = data.get("memory") or {}
    allowed = mem.get("allowed") or []
    forbidden = mem.get("forbidden") or []
    iso_ok = ("global" in allowed) and ("other_projects" in forbidden) and bool(pid)
    results.append(_ok("memory_isolation", iso_ok,
                       "内存隔离声明正确（allowed=%d, forbidden=%d）" % (len(allowed), len(forbidden))))

    # runtime_policy
    rp = os.path.join(proot, "runtime", "policies", "project-policy.yaml")
    results.append(_ok("runtime_policy", os.path.isfile(rp),
                       "runtime/policies 存在" if os.path.isfile(rp) else "runtime/policies 缺失"))

    # initial_tasks
    has_chain = os.path.isdir(backlog) and any(f.startswith("TASK-00") for f in os.listdir(backlog))
    results.append(_ok("initial_tasks", has_chain, "初始化任务链存在" if has_chain else "初始化任务链缺失"))

    # writable_scopes（authority 路径存在）
    auth = data.get("authority") or {}
    auth_ok = all(os.path.isdir(os.path.join(proot, p)) for p in auth.values() if p)
    results.append(_ok("writable_scopes", auth_ok,
                       "authority 作用域目录存在" if auth_ok else "authority 作用域目录缺失"))

    overall = all(s == C.PASS for _, s, _ in results)
    return results, overall


def main():
    ap = argparse.ArgumentParser(description="初始化门禁检查")
    ap.add_argument("--project-root", required=True)
    args = ap.parse_args()
    platform_root = C.find_platform_root()
    results, ok = run(os.path.abspath(args.project_root), platform_root)
    for name, sym, detail in results:
        mark = "✓" if sym == C.PASS else "✗"
        print("  [%s] %-20s %s" % (mark, name, detail))
    print("")
    if ok:
        print("结果：初始化门禁全 PASS")
        sys.exit(0)
    print("结果：存在 FAIL，安装未完成（请检查 staging 后重试或 reconcile）。")
    sys.exit(1)


if __name__ == "__main__":
    main()

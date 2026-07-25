#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_deployment_plan.py — 组合部署清单（Section II/VI.3）

组合：core/project-manifest.yaml（基础结构）
    + templates/<genre>/template-manifest.yaml（题材要求 + seeds + initial_tasks）
    + schemas/nkb/nkb-manifest.yaml（NKB 组件）
    + 用户 spec + resolve 出的 lock
  => Project Deployment Plan（供 render 与 deployment-manifest 使用）

用法：python build_deployment_plan.py --id X --genre xuanhuan
API：  build(spec, lock, platform_root, deploy_id) -> (plan_dict, err)
"""
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _installer_common as C


def derive_pid(title, pid=None):
    if pid:
        return pid
    slug = __import__("re").sub(r"[^a-z0-9]+", "-", str(title).lower()).strip("-")
    return "novel-%s" % slug if slug else "novel"


def build(spec, lock, platform_root, deploy_id):
    proj = spec.get("project") or {}
    tpl = spec.get("template") or {}
    title = proj.get("title") or spec.get("title")
    genre = tpl.get("id") or tpl.get("genre") or spec.get("genre")
    pid = proj.get("id") or derive_pid(title)
    if not genre:
        return None, "缺少 genre"

    core_m, tpl_m, nkb_m, merr = C.load_manifests(platform_root, genre)
    if merr:
        return None, merr

    structure = core_m.get("structure") or {}

    # 目录（initialize）
    directories = [e.get("path") for e in (structure.get("initialize") or [])]

    # 引用（reference，仅记录，不复制）
    references = [e.get("path") for e in (structure.get("reference") or [])]

    # 生成/锁/托管文件清单（用于 deployment-manifest.files）
    files = []
    for e in (structure.get("generate") or []):
        files.append({
            "path": e.get("path"),
            "owner": e.get("owner", "project"),
            "strategy": e.get("strategy", C.STRATEGY_GENERATE),
            "overwrite": e.get("overwrite", "never"),
        })
    # NKB 组件文件（generate_from_schema）
    nkb_comps = [c.get("name") for c in (nkb_m.get("components") or [])]
    for name in nkb_comps:
        files.append({
            "path": "NKB/%s.yaml" % name,
            "owner": "project",
            "strategy": "generate_from_schema",
            "overwrite": "never",
        })
    files.append({
        "path": "NKB/manifest.yaml",
        "owner": "project",
        "strategy": "generate",
        "overwrite": "never",
    })

    # 派生目录（derive）
    derives = [e.get("path") for e in (structure.get("derive") or [])]

    plan = {
        "deployment": {
            "id": deploy_id,
            "installer_version": "1.0.0",
            "generated_at": C.now_iso(),
            "project_id": pid,
            "template": lock.get("resolved", {}).get("template"),
            "core_version": lock.get("resolved", {}).get("core"),
            "nkb_schema": lock.get("resolved", {}).get("nkb_schema"),
        },
        "directories": directories,
        "references": references,
        "derive": derives,
        "files": files,
        "seeds": (tpl_m.get("seeds") or {}),
        "initial_tasks": (tpl_m.get("initial_tasks") or []),
    }
    return plan, None


def main():
    ap = argparse.ArgumentParser(description="组合部署计划")
    ap.add_argument("--spec")
    ap.add_argument("--id")
    ap.add_argument("--title")
    ap.add_argument("--genre", default="xuanhuan")
    ap.add_argument("--deploy-id", default=C.make_deploy_id())
    args = ap.parse_args()
    spec = {"project": {}, "template": {}}
    if args.spec:
        spec = C.load_yaml(args.spec)
    spec.setdefault("project", {})["id"] = args.id or (spec.get("project") or {}).get("id")
    spec.setdefault("project", {})["title"] = args.title or (spec.get("project") or {}).get("title")
    spec.setdefault("template", {})["genre"] = args.genre
    platform_root = C.find_platform_root()
    # 需要 lock：先用 resolve_dependencies 计算
    import resolve_dependencies as RD
    lock, lerr = RD.resolve(spec, platform_root)
    if lerr:
        C.die(lerr, 2)
    plan, err = build(spec, lock, platform_root, args.deploy_id)
    if err:
        C.die(err, 2)
    print(C.dump_block(plan))
    sys.exit(0)


if __name__ == "__main__":
    main()

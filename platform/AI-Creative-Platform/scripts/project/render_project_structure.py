#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_project_structure.py — 在 staging 目录渲染项目骨架（Section VI.3/IV）

只生成“结构 + 部署清单 + 薄 AGENTS.md”，不写业务内容（业务内容由 init_* 模块填充）。
所有文件先落在 runtime/staging/<pid>-<deploy_id>/，不直接写正式项目。

用法：python render_project_structure.py --staging <dir> --id X --genre xuanhuan
API：  render(spec, lock, plan, platform_root, staging) -> (ok, err)
"""
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _installer_common as C


AGENTS_MD = """# 项目执行入口

- 本项目必须通过 `platform session bootstrap` 启动。
- `project.yaml` 是项目启动清单（唯一入口）。
- NKB 是唯一事实源（事实须经规划确认，禁止凭空编造）。
- 禁止直接绕过任务系统修改项目。
- 禁止创建、委派或并行运行子 Agent。
- 多角色由当前 Agent 串行切换。
- 所有修改必须通过 `platform validate`。
"""


def render(spec, lock, plan, platform_root, staging):
    proj = spec.get("project") or {}
    tpl = spec.get("template") or {}
    title = proj.get("title") or spec.get("title")
    genre = tpl.get("id") or tpl.get("genre") or spec.get("genre")
    pid = proj.get("id") or C.derive_pid(title) if hasattr(C, "derive_pid") else (proj.get("id"))

    C.ensure_dir(staging)

    # 1) 目录骨架 + .gitkeep
    for d in (plan.get("directories") or []):
        dd = os.path.join(staging, d)
        C.ensure_dir(dd)
        gk = os.path.join(dd, ".gitkeep")
        if not os.path.exists(gk):
            open(gk, "w", encoding="utf-8").close()

    # 2) 薄 AGENTS.md（managed，随平台版本迁移）
    C.write_text(os.path.join(staging, "AGENTS.md"), AGENTS_MD)

    # 3) deployment-manifest.yaml（owner/project，strategy=generate，overwrite=versioned）
    dm = {
        "deployment": plan.get("deployment", {}),
        "files": plan.get("files", []),
        "references": plan.get("references", []),
        "derive": plan.get("derive", []),
    }
    C.dump_yaml(os.path.join(staging, "deployment-manifest.yaml"), dm)

    return True, None


def main():
    ap = argparse.ArgumentParser(description="渲染 staging 项目骨架")
    ap.add_argument("--staging", required=True)
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
    import resolve_dependencies as RD
    lock, lerr = RD.resolve(spec, platform_root)
    if lerr:
        C.die(lerr, 2)
    import build_deployment_plan as BP
    plan, perr = BP.build(spec, lock, platform_root, args.deploy_id)
    if perr:
        C.die(perr, 2)
    ok, err = render(spec, lock, plan, platform_root, args.staging)
    if not ok:
        C.die(err or "render 失败", 2)
    print("✓ staging 骨架已生成：%s" % args.staging)
    sys.exit(0)


if __name__ == "__main__":
    main()

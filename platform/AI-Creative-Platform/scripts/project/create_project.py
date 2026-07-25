#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""create_project.py — 事务式安装编排器（Section VI 全流程）

流程：
  1. 预检（validate_project_spec）
  2. 解析依赖并锁版本（resolve_dependencies → project.lock.yaml）
  3. 组合部署计划（build_deployment_plan）
  4. 在 runtime/staging/<pid>-<deploy_id>/ 渲染骨架（render_project_structure）
  5. 生成 project.yaml/lock/config（init_project_yaml）
  6. 初始化空 NKB（init_nkb，含 seed 候选）
  7. 初始化内存隔离（init_memory）
  8. 创建初始化任务链（init_tasks）
  9. 生成运行时策略（init_runtime_policy）
  10. 运行初始化门禁（project_doctor）；不通过则保留 staging 并中止
  11. 原子移入 projects/<name>（中途失败不残留残缺项目）
  12. 注册项目（register_project）+ 更新 workspace.yaml
  13. 触发 session bootstrap（--intent project_discovery）
  14. 置 lifecycle: planning

确定性部署：作品卖点/世界观/人物/剧情等语义内容不在此阶段填写，后续由 AI 规划任务生成。

用法：python create_project.py --id novel-daofa --title 道法百年 --genre xuanhuan --language zh-CN
      python create_project.py --spec project-spec.yaml
API：  create(spec, platform_root, ws_root) -> (proot, err)
"""
import os
import sys
import argparse
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _installer_common as C

import validate_project_spec as V
import resolve_dependencies as RD
import build_deployment_plan as BP
import render_project_structure as RS
import init_project_yaml as IPY
import init_nkb as INKB
import init_memory as IM
import init_tasks as IT
import init_runtime_policy as IRP
import project_doctor as PD
import register_project as RP


def create(spec, platform_root, ws_root):
    proj = spec.get("project") or {}
    tpl = spec.get("template") or {}
    title = proj.get("title") or spec.get("title") or "未命名项目"
    genre = tpl.get("id") or tpl.get("genre") or spec.get("genre") or "xuanhuan"
    language = proj.get("language") or spec.get("language") or "zh-CN"
    pid = proj.get("id") or C.derive_pid(title)
    proj_name = spec.get("project_dir") or title

    print("[1/14] 预检")
    ok, errs, warns = V.validate(spec, platform_root, ws_root)
    for w in warns:
        print("  [!] %s" % w)
    if not ok:
        return None, "预检失败：\n    " + "\n    ".join(errs)

    print("[2/14] 解析依赖并锁版本")
    lock, lerr = RD.resolve(spec, platform_root)
    if lerr:
        return None, "依赖解析失败：%s" % lerr

    print("[3/14] 组合部署计划")
    plan, perr = BP.build(spec, lock, platform_root, C.make_deploy_id())
    if perr:
        return None, "部署计划失败：%s" % perr
    deploy_id = plan.get("deployment", {}).get("id", C.make_deploy_id())

    # staging
    staging = C.stage_dir_for(ws_root, pid, deploy_id)
    if os.path.exists(staging):
        import shutil
        shutil.rmtree(staging)
    C.ensure_dir(staging)
    print("[4/14] 渲染 staging 骨架：%s" % staging)
    ok, err = RS.render(spec, lock, plan, platform_root, staging)
    if not ok:
        return None, "渲染失败：%s" % err

    print("[5/14] 生成 project.yaml / lock / config")
    ok, err = IPY.init(spec, lock, staging, platform_root)
    if not ok:
        return None, "init_project_yaml 失败：%s" % err

    print("[6/14] 初始化空 NKB（含 seed 候选）")
    ok, err = INKB.init(spec, staging, platform_root)
    if not ok:
        return None, "init_nkb 失败：%s" % err

    print("[7/14] 初始化内存隔离")
    ok, err = IM.init(spec, staging, platform_root)
    if not ok:
        return None, "init_memory 失败：%s" % err

    print("[8/14] 创建初始化任务链")
    ok, err = IT.init(spec, staging, platform_root)
    if not ok:
        return None, "init_tasks 失败：%s" % err

    print("[9/14] 生成运行时策略")
    ok, err = IRP.init(spec, staging, platform_root)
    if not ok:
        return None, "init_runtime_policy 失败：%s" % err

    print("[10/14] 初始化门禁（project_doctor）")
    results, gate_ok = PD.run(staging, platform_root)
    for name, sym, detail in results:
        print("  [%-4s] %-20s %s" % (sym, name, detail))
    if not gate_ok:
        return None, "初始化门禁未全 PASS；staging 保留于 %s 供检查。" % staging

    proot = os.path.normpath(os.path.join(ws_root, "projects", str(proj_name)))
    print("[11/14] 原子移入：%s" % proot)
    ok, err = C.stage_atomic_move(staging, proot)
    if not ok:
        return None, "原子移入失败：%s" % err

    print("[12/14] 注册项目")
    ok, errs = RP.register(proot, platform_root, genre, title, pid)
    if not ok:
        return None, "注册失败：%s" % "; ".join(errs)

    # lifecycle: planning
    py = os.path.join(proot, "project.yaml")
    data = C.load_yaml(py) or {}
    data.setdefault("project", {})["lifecycle"] = "planning"
    C.dump_yaml(py, data)

    print("[13/14] 触发 session bootstrap（intent=project_discovery）")
    cli = os.path.join(platform_root, "cli", "platform.py")
    try:
        subprocess.run([sys.executable, cli, "session", "bootstrap",
                        "--project", pid, "--intent", "project_discovery"],
                       check=False, capture_output=True, text=True)
        print("  ✓ session bootstrap 已触发")
    except Exception as e:
        print("  [!] session bootstrap 触发失败（可手动运行）：%s" % e)

    print("[14/14] 完成。lifecycle: planning")
    return proot, None


def main():
    ap = argparse.ArgumentParser(description="事务式创建小说项目")
    ap.add_argument("--spec")
    ap.add_argument("--id")
    ap.add_argument("--title")
    ap.add_argument("--genre", default="xuanhuan")
    ap.add_argument("--language", default="zh-CN")
    ap.add_argument("--project-dir", help="项目目录名（默认用 title）")
    ap.add_argument("--workspace", help="workspace 根（默认自动查找）")
    args = ap.parse_args()

    spec = {"project": {}, "template": {}, "writing": {}, "runtime": {}}
    if args.spec:
        spec = C.load_yaml(args.spec)
    spec.setdefault("project", {})
    spec["project"]["id"] = args.id or (spec.get("project") or {}).get("id")
    spec["project"]["title"] = args.title or (spec.get("project") or {}).get("title")
    spec["project"]["language"] = args.language
    spec.setdefault("template", {})
    spec["template"]["genre"] = args.genre
    if args.project_dir:
        spec["project_dir"] = args.project_dir

    if args.workspace:
        ws_root = os.path.abspath(args.workspace)
    else:
        ws_root = C.find_workspace_root()
    platform_root = C.find_platform_root()

    proot, err = create(spec, platform_root, ws_root)
    if err:
        C.die(err, 2)
    print("\n✓ 项目已创建：%s" % proot)
    print("  后续：平台以 project.yaml 为唯一入口；小说语义内容由规划任务（TASK-001..）生成。")
    sys.exit(0)


if __name__ == "__main__":
    main()

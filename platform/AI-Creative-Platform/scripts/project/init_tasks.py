#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""init_tasks.py — 创建初始化任务链（Section VI.6）

不安装完成后直接写第一章，而是创建顺序执行的初始化任务链：
  TASK-001..009（installer 标准，来自 core/project-manifest.yaml init_task_chain）
  + 题材 template-manifest.initial_tasks（接续，去重后追加为 TASK-01X）

任务写入 tasks/backlog/，状态由任务系统文件夹移动驱动。

用法：python init_tasks.py --staging <dir> --id X --genre xuanhuan
API：  init(spec, staging, platform_root) -> (ok, err)
"""
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _installer_common as C


def init(spec, staging, platform_root):
    proj = spec.get("project") or {}
    tpl = spec.get("template") or {}
    title = proj.get("title") or spec.get("title") or "未命名"
    genre = tpl.get("id") or tpl.get("genre") or spec.get("genre") or "xuanhuan"
    pid = proj.get("id") or C.derive_pid(title)

    core_m, tpl_m, nkb_m, merr = C.load_manifests(platform_root, genre)
    if merr:
        return False, merr

    chain = core_m.get("init_task_chain") or []
    tpl_tasks = tpl_m.get("initial_tasks") or []

    # 合并：标准链在前；题材 task 去重（按 key）后追加
    seen_keys = set()
    merged = []
    for t in chain:
        seen_keys.add(t.get("key"))
        merged.append(t)
    for key in tpl_tasks:
        if key in seen_keys:
            continue
        seen_keys.add(key)
        merged.append({"id": None, "key": key, "title": key, "role": "planner"})

    # 重排序号 TASK-001..00N
    backlog = os.path.join(staging, "tasks", "backlog")
    C.ensure_dir(backlog)

    prev_id = None
    for i, t in enumerate(merged, start=1):
        tid = "TASK-%03d" % i
        key = t.get("key")
        ttitle = t.get("title") or key
        role = t.get("role") or "planner"
        # 用 dict + block 发射器生成（绝不写 >-/| 折叠标量，保证 _yaml_lite 可回读）
        task = {
            "id": tid,
            "key": key,
            "title": ttitle,
            "role": role,
            "status": "backlog",
            "created_by": "project_installer",
            "template": "project-design",
            "description": "%s（安装初始化任务，由任务系统顺序调度）" % ttitle,
            "blocked_by": [prev_id] if prev_id else [],
            "next": ["TASK-%03d" % (i + 1)] if i < len(merged) else [],
        }
        C.dump_yaml(os.path.join(backlog, "%s.yaml" % tid), {"task": task})
        prev_id = tid

    return True, None


def main():
    ap = argparse.ArgumentParser(description="创建初始化任务链")
    ap.add_argument("--staging", required=True)
    ap.add_argument("--spec")
    ap.add_argument("--id")
    ap.add_argument("--title")
    ap.add_argument("--genre", default="xuanhuan")
    args = ap.parse_args()
    spec = {"project": {}, "template": {}}
    if args.spec:
        spec = C.load_yaml(args.spec)
    spec.setdefault("project", {})["id"] = args.id or (spec.get("project") or {}).get("id")
    spec.setdefault("project", {})["title"] = args.title or (spec.get("project") or {}).get("title")
    spec.setdefault("template", {})["genre"] = args.genre
    platform_root = C.find_platform_root()
    ok, err = init(spec, args.staging, platform_root)
    if not ok:
        C.die(err or "init_tasks 失败", 2)
    print("✓ 初始化任务链已生成（tasks/backlog/）")
    sys.exit(0)


if __name__ == "__main__":
    main()

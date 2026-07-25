#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""init_memory.py — 初始化内存隔离（Section VI.7）

新项目只允许加载：
  - Global Memory（平台级通用经验）
  - Genre Memory：<genre>
  - Project Memory：<project_id>
明确禁止：其他小说的 NKB / Project Memory / 正文 / 未晋升的项目私有经验。

本模块生成 memory/project/ 的占位结构 + 隔离声明；运行时的实际加载隔离由
core/memory 与 session bootstrap 依据 project.yaml 的 memory.allowed/forbidden 执行。

用法：python init_memory.py --staging <dir> --id X --genre xuanhuan
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

    mp = os.path.join(staging, "memory", "project")
    C.ensure_dir(mp)
    for d in ("decisions", "patterns", "rejected"):
        C.ensure_dir(os.path.join(mp, d))

    readme = (
        "# Project Memory：%s\n\n"
        "隔离策略（由 project.yaml 的 memory.allowed/forbidden 强制）：\n"
        "- 允许加载：global / genre:%s / project:%s\n"
        "- 禁止加载：其他项目的 NKB、Project Memory、正文、未晋升经验\n\n"
        "本目录只保存本项目私有经验与决策，不复制平台/Core/其他项目内容。\n"
    ) % (pid, genre, pid)
    C.write_text(os.path.join(mp, "MEMORY.md"), readme)

    # 各子目录 README（说明用途 + 隔离边界）
    for d in ("decisions", "patterns", "rejected"):
        C.write_text(os.path.join(mp, d, "README.md"),
                     "# memory/project/%s\n\n项目私有（%s）。禁止从其他项目导入。\n" % (d, d))

    return True, None


def main():
    ap = argparse.ArgumentParser(description="初始化内存隔离")
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
        C.die(err or "init_memory 失败", 2)
    print("✓ 内存隔离结构已生成")
    sys.exit(0)


if __name__ == "__main__":
    main()

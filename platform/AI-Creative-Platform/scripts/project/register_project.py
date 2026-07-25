#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""register_project.py — 注册项目到平台（Section VI.10）

写入 registry/projects.yaml + 更新 workspace.yaml 的 projects 列表。
复用 scripts/project/multi_project.register（既有多项目注册，零依赖）。

用法：python register_project.py --project-root <dir> --genre xuanhuan
API：  register(proot, platform_root, genre, title, pid) -> (ok, errs)
"""
import os
import sys
import argparse
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _installer_common as C
import multi_project  # 既有多项目注册


def register(proot, platform_root, genre, title, pid):
    # registry 项：path 相对 platform_root（registry 在 platform 下两级）
    rel_reg = os.path.relpath(proot, platform_root).replace(os.sep, "/")
    # workspace 项：path 相对 ws_root（workspace.yaml 在 workspace 根）
    ws_root = C.find_workspace_root()
    rel_ws = os.path.relpath(proot, ws_root).replace(os.sep, "/")
    if not rel_ws.startswith(".") and not rel_ws.startswith("/"):
        rel_ws = "./" + rel_ws
    entry = {
        "id": pid,
        "name": title,
        "path": rel_reg,
        "type": genre,
        "genre": genre,
        "status": "active",
        "created": datetime.date.today().isoformat(),
    }
    ok, errs, clean = multi_project.register(platform_root, entry, write=True)
    if not ok:
        return False, errs
    # 更新 workspace.yaml 的 projects 列表（追加一行，保留注释）
    _append_to_workspace(ws_root, rel_ws)
    return True, []


def _append_to_workspace(ws_root, rel):
    ws_path = os.path.join(ws_root, "workspace.yaml")
    if not os.path.isfile(ws_path):
        return
    with open(ws_path, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")
    proj_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "projects:":
            proj_idx = i
            break
    if proj_idx is None:
        lines.append("workspace:")
        lines.append("  platform: ./platform/AI-Creative-Platform")
        lines.append("  projects:")
        lines.append("    - %s" % rel)
        with open(ws_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return
    indent = "    "
    last_idx = proj_idx
    for j in range(proj_idx + 1, len(lines)):
        s = lines[j]
        if s.strip().startswith("- "):
            last_idx = j
            indent = s[: len(s) - len(s.lstrip(" "))]
        elif s.strip() == "":
            continue
        else:
            if j > proj_idx + 1:
                break
    # 避免重复
    for j in range(proj_idx + 1, len(lines)):
        if lines[j].strip() == "- %s" % rel:
            return
    lines.insert(last_idx + 1, "%s- %s" % (indent, rel))
    with open(ws_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description="注册项目")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--genre", default="xuanhuan")
    ap.add_argument("--title", default=None)
    ap.add_argument("--id", default=None)
    args = ap.parse_args()
    proot = os.path.abspath(args.project_root)
    platform_root = C.find_platform_root()
    # 读 project.yaml 取 title/id（若未传）
    py = os.path.join(proot, "project.yaml")
    title = args.title
    pid = args.id
    if os.path.isfile(py):
        d = C.load_yaml(py) or {}
        title = title or (d.get("project") or {}).get("title")
        pid = pid or (d.get("project") or {}).get("id")
    title = title or os.path.basename(proot)
    pid = pid or C.derive_pid(title)
    ok, errs = register(proot, platform_root, args.genre, title, pid)
    if not ok:
        C.die("; ".join(errs), 2)
    print("✓ 已注册项目：%s" % proot)
    sys.exit(0)


if __name__ == "__main__":
    main()

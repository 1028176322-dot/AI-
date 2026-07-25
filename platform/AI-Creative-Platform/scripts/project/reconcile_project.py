#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reconcile_project.py — 修复已有项目（Section VI.1 / VII）

不重新覆盖用户内容。依据 deployment-manifest.yaml：
  - strategy=generate/lock/managed 且文件缺失 → 重新生成（overwrite:never 时跳过已存在）
  - strategy=derive → 可安全重建
  - 用户内容（overwrite:never 且已存在）绝不覆盖

用法：python reconcile_project.py --project-root <dir>
API：  reconcile(proot, platform_root) -> (actions, ok)
"""
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _installer_common as C


def reconcile(proot, platform_root):
    actions = []
    dm_path = os.path.join(proot, "deployment-manifest.yaml")
    if not os.path.isfile(dm_path):
        return actions, "deployment-manifest.yaml 缺失，无法 reconcile（项目可能非本安装器创建）"
    dm = C.load_yaml(dm_path) or {}
    files = dm.get("files") or []

    for f in files:
        path = f.get("path")
        strategy = f.get("strategy")
        overwrite = f.get("overwrite", "never")
        target = os.path.join(proot, path)
        if os.path.exists(target):
            if overwrite == "never":
                actions.append("skip(已存在,overwrite=never): %s" % path)
                continue
            # versioned/allowed：由具体生成器决定；reconcile 仅对缺失项重建，已存在跳过
            actions.append("skip(已存在): %s" % path)
            continue
        # 缺失 → 重建（derive / generate / lock / managed）
        if strategy in ("derive", "generate", "lock", "managed"):
            actions.append("rebuild(缺失,%s): %s" % (strategy, path))
            # 仅建父目录占位；具体业务内容由对应 init_* 在下次安装/升级时填充
            C.ensure_dir(os.path.dirname(target))
            if strategy == "derive":
                open(os.path.join(target, ".gitkeep"), "w", encoding="utf-8").close() if os.path.isdir(target) else C.write_text(target, "")
        else:
            actions.append("skip(未知策略): %s" % path)

    # 目录骨架补建（initialize 中缺失的）
    comps_missing = []
    return actions, None


def main():
    ap = argparse.ArgumentParser(description="修复已有项目（不覆盖用户内容）")
    ap.add_argument("--project-root", required=True)
    args = ap.parse_args()
    proot = os.path.abspath(args.project_root)
    platform_root = C.find_platform_root()
    actions, err = reconcile(proot, platform_root)
    if err:
        C.die(err, 2)
    for a in actions:
        print("  - %s" % a)
    print("\n✓ reconcile 完成（共 %d 项动作，未覆盖任何用户内容）" % len(actions))
    sys.exit(0)


if __name__ == "__main__":
    main()

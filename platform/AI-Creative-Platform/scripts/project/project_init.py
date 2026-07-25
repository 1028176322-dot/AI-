#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
project_init.py — 脚手架项目生命周期目录与 status.yaml（P0 入口）

CLI: platform init --project-root <dir> [--title T] [--genre G] [--id ID]
                       [--stage S] [--legacy]

职责：
  - 创建 lifecycle/{idea,initiation,definition,readiness} + .gitkeep
  - 写入 lifecycle/status.yaml（lifecycle_status + legacy 标记）
不替代既有 init-project（init-project 负责 project.yaml/NKB 脚手架）。
"""
import argparse
import os
import sys
import datetime

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


def main():
    ap = argparse.ArgumentParser(description="脚手架项目生命周期目录 + status.yaml")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--title", default="未命名项目")
    ap.add_argument("--genre", default="xuanhuan")
    ap.add_argument("--id", default=None)
    ap.add_argument("--stage", default="idea",
                    help="初始 lifecycle_status（默认 idea）")
    ap.add_argument("--legacy", action="store_true",
                    help="祖父化：直接置 writing + legacy_backfill_required=true")
    args = ap.parse_args()

    root = os.path.abspath(args.project_root)
    if not os.path.isfile(os.path.join(root, "project.yaml")):
        sys.stderr.write("✗ 项目根无 project.yaml：%s\n" % root)
        sys.exit(2)

    for d in ("idea", "initiation", "definition", "readiness"):
        dd = os.path.join(root, "lifecycle", d)
        os.makedirs(dd, exist_ok=True)
        gk = os.path.join(dd, ".gitkeep")
        if not os.path.exists(gk):
            open(gk, "w").close()

    legacy = args.legacy
    status = {
        "lifecycle_status": "writing" if legacy else args.stage,
        "current_stage": "P6" if legacy else "P0",
        "updated_at": datetime.date.today().isoformat(),
        "updated_by": "project_init",
        "legacy_backfill_required": True if legacy else False,
        "notes": ("祖父化项目：已处于写作期，须补回 charter/brief/readiness 制品"
                  if legacy else "由 project_init 脚手架生成"),
    }
    sp = os.path.join(root, "lifecycle", "status.yaml")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(status) + "\n")

    print("✓ lifecycle/ 脚手架完成（%s）" % ("legacy" if legacy else args.stage))
    print("  lifecycle/status.yaml -> lifecycle_status=%s" % status["lifecycle_status"])
    sys.exit(0)


if __name__ == "__main__":
    main()

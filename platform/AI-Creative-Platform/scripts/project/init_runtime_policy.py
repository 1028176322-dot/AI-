#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""init_runtime_policy.py — 生成运行时策略（Section IV runtime/）

runtime/ 内容属于可重建（derive），不是权威事实源：
  - runtime/policies/project-policy.yaml：引用平台策略（by path，不复制）
  - runtime/context/、runtime/task-packets/、runtime/sessions/：运行期产物

用法：python init_runtime_policy.py --staging <dir> --genre xuanhuan
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

    # runtime/policies：引用平台策略（不复制实现）
    pol_dir = os.path.join(staging, "runtime", "policies")
    C.ensure_dir(pol_dir)
    policy = {
        "schema_version": "1.0.0",
        "project_id": pid,
        "strategy": "reference",   # 运行时派生，非权威
        "references": {
            "base_policy": "../../../platform/AI-Creative-Platform/core/policies/compliance.policy.yaml",
            "runtime_policy": "../../../platform/AI-Creative-Platform/core/policies/agent-execution.policy.yaml",
            "project_creation_policy": "../../../platform/AI-Creative-Platform/core/policies/workflow.policy.yaml",
        },
        "agent_mode": "single",
        "note": "本文件仅引用平台策略；升级平台时随平台版本迁移，不复制实体。",
    }
    C.dump_yaml(os.path.join(pol_dir, "project-policy.yaml"), policy)

    # runtime 其他目录占位（运行期产物）
    for d in ("context", "task-packets", "sessions"):
        C.ensure_dir(os.path.join(staging, "runtime", d))

    return True, None


def main():
    ap = argparse.ArgumentParser(description="生成运行时策略")
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
        C.die(err or "init_runtime_policy 失败", 2)
    print("✓ 运行时策略已生成（runtime/policies/）")
    sys.exit(0)


if __name__ == "__main__":
    main()

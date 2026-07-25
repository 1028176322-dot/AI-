#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""resolve_dependencies.py — 解析依赖并锁定版本（Section VI.2）

输入：spec + 三类清单 + registry/versions.yaml + registry/plugins.yaml
输出：project.lock.yaml 内容（dict），不同会话始终使用同一套版本。

用法：python resolve_dependencies.py --id X --genre xuanhuan
API：  resolve(spec, platform_root) -> (lock_dict, err)
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


def resolve(spec, platform_root):
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
    versions = C.load_versions(platform_root)
    if not versions:
        return None, "registry/versions.yaml 不可读"

    plock = C.build_plugin_lock(platform_root, core_m, tpl_m)

    lock = {
        "schema_version": "1.0.0",
        "generated_by": "project_installer",
        "generated_at": C.now_iso(),
        "project_id": pid,
        "resolved": {
            "core": str((versions.get("core") or {}).get("platform", "0")),
            "template": "%s@%s" % (genre, (tpl_m.get("template") or {}).get("version", "?")),
            "nkb_schema": str(nkb_m.get("schema_version", "0")),
            "plugins": plock["plugins"],
            "capabilities": plock["capabilities"],
        },
    }
    return lock, None


def main():
    ap = argparse.ArgumentParser(description="解析依赖并锁定版本")
    ap.add_argument("--spec")
    ap.add_argument("--id")
    ap.add_argument("--title")
    ap.add_argument("--genre", default="xuanhuan")
    args = ap.parse_args()
    spec = {"project": {}, "template": {}}
    if args.spec:
        spec = C.load_yaml(args.spec)
    spec["project"]["id"] = args.id or (spec.get("project") or {}).get("id")
    spec["project"]["title"] = args.title or (spec.get("project") or {}).get("title")
    spec["template"]["genre"] = args.genre
    platform_root = C.find_platform_root()
    lock, err = resolve(spec, platform_root)
    if err:
        C.die(err, 2)
    print(C.dump_block(lock))
    sys.exit(0)


if __name__ == "__main__":
    main()

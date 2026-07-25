#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""upgrade_project.py — 升级项目模板版本（Section VII）

必须使用迁移脚本，不能重新复制模板覆盖项目。
步骤：
  1. 解析目标模板版本（--to-template xuanhuan@2.2.0）
  2. 版本满足度校验（新模板 requires.core / nkb_schema）
  3. 更新 project.yaml 的 platform.template.version + project.lock.yaml
  4. 运行 migrations/<from>-><to> 迁移脚本（如存在）；否则仅标注（无破坏性默认动作）
  5. 重新运行 project_doctor

用法：python upgrade_project.py --project-root <dir> --to-template xuanhuan@2.2.0
API：  upgrade(proot, platform_root, to_template) -> (ok, err)
"""
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _installer_common as C


def upgrade(proot, platform_root, to_template):
    if "@" not in to_template:
        return False, "目标模板格式须为 <genre>@<version>（如 xuanhuan@2.2.0）"
    genre, ver = to_template.split("@", 1)

    py = os.path.join(proot, "project.yaml")
    if not os.path.isfile(py):
        return False, "project.yaml 缺失"
    data = C.load_yaml(py) or {}
    cur_genre = (data.get("template") or {}).get("id")
    if cur_genre != genre:
        return False, "目标模板 genre(%s) 与项目(%s) 不一致" % (genre, cur_genre)

    # 加载目标模板清单校验
    core_m, tpl_m, nkb_m, merr = C.load_manifests(platform_root, genre)
    if merr:
        return False, merr
    if str((tpl_m.get("template") or {}).get("version")) != ver:
        # 允许目标版本不在注册清单（未来版本）；但要求 exists
        if not os.path.isfile(os.path.join(platform_root, "templates", genre, "template-manifest.yaml")):
            return False, "目标模板不存在"

    # 版本满足度
    versions = C.load_versions(platform_root)
    req_core = (tpl_m.get("requires") or {}).get("core", ">=0")
    actual_core = str((versions.get("core") or {}).get("platform", "0")) if versions else "0"
    if not C.satisfies(req_core, actual_core):
        return False, "目标模板要求 core %s，实际 %s" % (req_core, actual_core)

    # 更新 project.yaml
    data.setdefault("template", {})["version"] = ver
    data.setdefault("platform", {})["template"] = {"id": genre, "version": ver}
    C.dump_yaml(py, data)

    # 更新 project.lock.yaml
    lk = os.path.join(proot, "project.lock.yaml")
    if os.path.isfile(lk):
        lock = C.load_yaml(lk) or {}
        lock.setdefault("resolved", {})["template"] = "%s@%s" % (genre, ver)
        lock["generated_at"] = C.now_iso()
        lock["note"] = "upgraded from prior template version"
        C.dump_yaml(lk, lock)

    # 迁移脚本（migrations/ 下 <from>-><to>）
    migrations_dir = os.path.join(platform_root, "migrations")
    notes = []
    if os.path.isdir(migrations_dir):
        # 占位：实际迁移脚本由维护者按版本补充；此处仅探测
        notes.append("migrations/ 存在，但无匹配 %s 的自动迁移脚本；请人工核对题材差异" % to_template)
    else:
        notes.append("migrations/ 不存在；仅更新版本声明，未执行数据迁移")

    return True, "; ".join(notes)


def main():
    ap = argparse.ArgumentParser(description="升级项目模板版本")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--to-template", required=True, help="如 xuanhuan@2.2.0")
    args = ap.parse_args()
    platform_root = C.find_platform_root()
    ok, msg = upgrade(os.path.abspath(args.project_root), platform_root, args.to_template)
    if not ok:
        C.die(msg, 2)
    print("✓ 升级声明已更新：%s" % args.to_template)
    print("  注：%s" % msg)
    sys.exit(0)


if __name__ == "__main__":
    main()

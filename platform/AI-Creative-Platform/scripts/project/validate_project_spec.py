#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_project_spec.py — 安装预检（Section VI.1）

检查项：
  - 必填项完整（id/title/genre/language）
  - 项目 id 合法（^[a-z0-9][a-z0-9_-]*$）
  - 题材模板存在（template-manifest.yaml + profile.yaml）
  - 模板版本兼容（requires.core / requires.nkb_schema vs 实际）
  - 必需 capability 可解析到注册表插件
  - NKB Schema 存在
  - 目标目录不存在（已存在 → 拒绝覆盖，须 reconcile）
  - 项目 id 不与 registry/projects.yaml 重复

用法：python validate_project_spec.py --spec project-spec.yaml
      python validate_project_spec.py --id X --title T --genre xuanhuan --language zh-CN
API：  validate(spec, platform_root, ws_root) -> (ok, errors, warnings)
"""
import os
import re
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _installer_common as C

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _load_spec(args):
    if getattr(args, "spec", None):
        if not os.path.isfile(args.spec):
            return None, "spec 文件不存在：%s" % args.spec
        return C.load_yaml(args.spec), None
    spec = {"project": {}, "template": {}, "writing": {}, "runtime": {}}
    spec["project"]["id"] = getattr(args, "id", None) or "novel-new"
    spec["project"]["title"] = getattr(args, "title", None) or "未命名项目"
    spec["project"]["language"] = getattr(args, "language", None) or "zh-CN"
    tv = getattr(args, "genre", None) or "xuanhuan"
    if "@" in tv:
        gid, gver = tv.split("@", 1)
    else:
        gid, gver = tv, None
    spec["template"]["genre"] = gid
    if gver:
        spec["template"]["version"] = gver
    return spec, None


def derive_pid(title, pid=None):
    if pid:
        return pid
    slug = re.sub(r"[^a-z0-9]+", "-", str(title).lower()).strip("-")
    return "novel-%s" % slug if slug else "novel"


def validate(spec, platform_root, ws_root):
    errors = []
    warnings = []

    proj = spec.get("project") or {}
    tpl = spec.get("template") or {}
    title = proj.get("title") or spec.get("title")
    genre = tpl.get("id") or tpl.get("genre") or spec.get("genre")
    language = proj.get("language") or spec.get("language") or "zh-CN"
    pid = proj.get("id") or derive_pid(title)

    # 必填项
    if not title:
        errors.append("缺少必填项：title")
    if not genre:
        errors.append("缺少必填项：genre/template.id")
    if not language:
        errors.append("缺少必填项：language")

    # id 合法
    if not _ID_RE.match(str(pid)):
        errors.append("项目 id 非法（须 ^[a-z0-9][a-z0-9_-]*$）: %s" % pid)

    if not genre:
        return False, errors, warnings

    # 模板存在
    tpl_dir = os.path.join(platform_root, "templates", genre)
    if not os.path.isdir(tpl_dir):
        errors.append("题材模板不存在：templates/%s" % genre)
        return False, errors, warnings
    if not os.path.isfile(os.path.join(tpl_dir, "template-manifest.yaml")):
        errors.append("题材模板缺 template-manifest.yaml：templates/%s" % genre)
    if not os.path.isfile(os.path.join(tpl_dir, "profile.yaml")):
        errors.append("题材模板缺 profile.yaml：templates/%s" % genre)

    # 加载三类清单 + 版本
    core_m, tpl_m, nkb_m, merr = C.load_manifests(platform_root, genre)
    if merr:
        errors.append(merr)
        return False, errors, warnings
    versions = C.load_versions(platform_root)
    if not versions:
        errors.append("registry/versions.yaml 不可读")
        return False, errors, warnings

    # 版本兼容：core
    req_core = (tpl_m.get("requires") or {}).get("core", ">=0")
    actual_core = str((versions.get("core") or {}).get("platform", "0"))
    if not C.satisfies(req_core, actual_core):
        errors.append("模板要求 core %s，实际 %s" % (req_core, actual_core))

    # 版本兼容：nkb_schema
    req_nkb = (tpl_m.get("requires") or {}).get("nkb_schema", ">=0")
    actual_nkb = str(nkb_m.get("schema_version", "0"))
    if not C.satisfies(req_nkb, actual_nkb):
        errors.append("模板要求 nkb_schema %s，实际 %s" % (req_nkb, actual_nkb))

    # capability 可解析
    cap_map = (core_m.get("capability_plugin_map") or {})
    for cap in (tpl_m.get("capabilities") or []):
        if cap not in cap_map:
            warnings.append("capability 未找到 plugin 映射（将保留键名）：%s" % cap)

    # NKB schema 存在性（load_manifests 已保证）
    if not nkb_m.get("components"):
        errors.append("nkb-manifest 无 components")

    # 目标目录不存在
    proj_name = spec.get("project_dir") or title
    proot = os.path.normpath(os.path.join(ws_root, "projects", str(proj_name)))
    if os.path.exists(proot):
        errors.append("目标项目目录已存在（禁止覆盖，请用 reconcile）：%s" % proot)

    # id 不重复
    reg_path = os.path.join(platform_root, "registry", "projects.yaml")
    if os.path.isfile(reg_path):
        reg = C.load_yaml(reg_path) or {}
        for p in (reg.get("projects") or []):
            if isinstance(p, dict) and p.get("id") == pid:
                errors.append("项目 id 重复（registry/projects.yaml 已注册）：%s" % pid)

    return (len(errors) == 0), errors, warnings


def main():
    ap = argparse.ArgumentParser(description="安装预检")
    ap.add_argument("--spec", help="项目规格 yaml")
    ap.add_argument("--id")
    ap.add_argument("--title")
    ap.add_argument("--genre", default="xuanhuan")
    ap.add_argument("--language", default="zh-CN")
    args = ap.parse_args()
    spec, serr = _load_spec(args)
    if serr:
        C.die(serr, 2)
    platform_root = C.find_platform_root()
    ws_root = C.find_workspace_root()
    ok, errs, warns = validate(spec, platform_root, ws_root)
    for w in warns:
        print("  [!] WARN %s" % w)
    if ok:
        print("✓ 预检通过")
        sys.exit(0)
    for e in errs:
        print("  [✗] FAIL %s" % e)
    sys.exit(1)


if __name__ == "__main__":
    main()

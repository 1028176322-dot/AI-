#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_sources.py — 校验 P3 创作设计源门禁（sources/design + sources/canon）

CLI: platform psrc --project-root <dir> [--src <dir>]

按 document.type 区分必填业务段（见 core/contracts/design-source.schema.yaml）。
status=approved/designed 时若含推测词（可能/也许/预计/...）则 FAIL。
退出码：0=全部 PASS；1=存在 FAIL；2=用法错误。
"""
import argparse
import os
import sys

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

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
SCHEMA_PATH = os.path.join(_gov.find_platform_root(), "core", "contracts", "design-source.schema.yaml")


def _scan_yaml(directory):
    out = []
    for dp, _, fs in os.walk(directory):
        for f in fs:
            if f.endswith((".yaml", ".yml")):
                out.append(os.path.join(dp, f))
    return out


def check_one(path, schema, expected_pid):
    fn = os.path.basename(path)
    data = _gov.load_yaml(path)
    if not isinstance(data, dict):
        return ["%s: 无法解析为映射" % fn]
    issues = []
    doc = data.get("document")
    if not isinstance(doc, dict):
        issues.append("%s: 缺少 document 头" % fn)
        return issues
    for f in ("id", "type", "title", "status", "version", "updated_at", "owner", "project_id"):
        if f not in doc:
            issues.append("%s: document 缺 %s" % (fn, f))
    if "version" in doc and not isinstance(doc["version"], int):
        issues.append("%s: document.version 须为整数" % fn)
    if doc.get("status") not in ("draft", "approved", "deprecated"):
        issues.append("%s: document.status 非法 %r" % (fn, doc.get("status")))
    if expected_pid and doc.get("project_id") != expected_pid:
        issues.append("%s: project_id %r != 期望 %r" % (fn, doc.get("project_id"), expected_pid))

    dtype = doc.get("type")
    tr = (schema or {}).get("type_required") or {}
    spec = tr.get(dtype)
    if spec is None:
        issues.append("%s: document.type=%r 无对应 type_required 规则" % (fn, dtype))
        return issues
    sec = spec.get("section")
    if sec not in data:
        issues.append("%s: 缺段 %s（type=%s）" % (fn, sec, dtype))
        return issues
    body = data[sec]
    if not isinstance(body, dict):
        issues.append("%s: %s 非映射" % (fn, sec))
        return issues
    for f in (spec.get("required_fields") or []):
        if f not in body:
            issues.append("%s: %s 缺字段 %s" % (fn, sec, f))
    for nested, nreq in (spec.get("nested_required") or {}).items():
        if nested not in body:
            issues.append("%s: %s 缺段 %s" % (fn, sec, nested))
        elif not isinstance(body[nested], dict):
            issues.append("%s: %s.%s 非映射" % (fn, sec, nested))
        else:
            for nf in nreq:
                if nf not in body[nested]:
                    issues.append("%s: %s.%s 缺字段 %s" % (fn, sec, nested, nf))
    for fld, allowed in (spec.get("enums") or {}).items():
        if fld in body and body[fld] not in allowed:
            issues.append("%s: %s.%s 非法 %r" % (fn, sec, fld, body[fld]))

    # 推测词门禁（仅 approved/designed）
    patterns = schema.get("forbidden_patterns") or []
    if doc.get("status") in ("approved", "designed") and patterns:
        raw = ""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except Exception:
            pass
        for pat in patterns:
            if pat in raw:
                issues.append("%s: status=%s 含推测词「%s」" % (fn, doc.get("status"), pat))
    return issues


def main():
    ap = argparse.ArgumentParser(description="校验 P3 创作设计源门禁")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--src", default=None, help="覆盖默认 sources/ 目录")
    args = ap.parse_args()

    root = os.path.abspath(args.project_root)
    if not os.path.isdir(root):
        sys.stderr.write("✗ 项目根不存在：%s\n" % root)
        sys.exit(2)
    schema = _gov.load_yaml(SCHEMA_PATH)
    proj = _gov.load_yaml(os.path.join(root, "project.yaml")) or {}
    expected_pid = (proj.get("project") or {}).get("id") or proj.get("id")

    src_root = args.src or os.path.join(root, "sources")
    targets = []
    for sub in ("design", "canon"):
        d = os.path.join(src_root, sub)
        if os.path.isdir(d):
            targets += _scan_yaml(d)

    if not targets:
        print("（sources/design 与 sources/canon 无文件可校验）")
        sys.exit(0)

    total = 0
    for p in targets:
        rel = os.path.relpath(p, root)
        res = check_one(p, schema, expected_pid)
        if not res:
            print("  [%s] %-40s 门禁 PASS" % (PASS, rel))
        else:
            total += len(res)
            for it in res:
                print("  [%s] %-40s %s" % (FAIL, rel, it))
    print("")
    if total:
        print("结果：%d 项 FAIL —— 设计源门禁不通过。" % total)
        sys.exit(1)
    print("结果：全部 PASS。")
    sys.exit(0)


if __name__ == "__main__":
    main()

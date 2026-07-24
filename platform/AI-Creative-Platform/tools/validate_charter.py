#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_charter.py — 校验 P0/P1/P2 生命周期制品契约

CLI: platform charter --project-root <dir> [--file <path>]

校验对象（在 lifecycle/ 下）：
  - idea/IDEA.yaml                 -> idea.schema
  - initiation/PROJECT_CHARTER.yaml-> project-charter.schema
  - initiation/INITIATION_GATE.yaml-> 内建门禁（status/decision 枚举）
  - definition/PROJECT_BRIEF.yaml  -> project-brief.schema (file_sections)
  - definition/AUDIENCE.yaml       -> project-brief.schema
  - definition/POSITIONING.yaml    -> project-brief.schema
  - definition/CONTENT_BOUNDARIES.yaml -> project-brief.schema
  - definition/CREATIVE_STRATEGY.yaml   -> creative-strategy.schema

退出码：0=全部 PASS；1=存在 FAIL；2=用法/环境错误。
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _gov

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
SCHEMA_DIR = os.path.join(_gov.find_platform_root(), "core", "contracts")


def load_schema(name):
    p = os.path.join(SCHEMA_DIR, name + ".schema.yaml")
    if not os.path.isfile(p):
        return None
    return _gov.load_yaml(p)


def _has(data, *keys):
    cur = data
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return False
        cur = cur[k]
    return True


def _check_doc_header(data, issues, label):
    doc = data.get("document") if isinstance(data, dict) else None
    if not isinstance(doc, dict):
        issues.append("%s: 缺少 document 头" % label)
        return
    for f in ("id", "type", "title", "status", "version", "updated_at", "owner", "project_id"):
        if f not in doc:
            issues.append("%s: document 缺字段 %s" % (label, f))
    if "version" in doc and not isinstance(doc["version"], int):
        issues.append("%s: document.version 必须为整数，实为整数？%r" % (label, doc.get("version")))
    if "status" in doc and doc["status"] not in ("draft", "approved", "deprecated"):
        issues.append("%s: document.status 非法 %r" % (label, doc.get("status")))


def _check_section(data, sec, issues, label):
    if sec.get("name") not in data:
        issues.append("%s: 缺顶级段 %s" % (label, sec.get("name")))
        return
    body = data[sec["name"]]
    if not isinstance(body, dict):
        issues.append("%s: 段 %s 不是映射" % (label, sec["name"]))
        return
    for f in (sec.get("required_fields") or []):
        if f not in body:
            issues.append("%s: %s 缺字段 %s" % (label, sec["name"], f))
    for fld, allowed in (sec.get("enums") or {}).items():
        if fld in body and body[fld] not in allowed:
            issues.append("%s: %s.%s 非法 %r（允许 %s）" % (label, sec["name"], fld, body[fld], allowed))
    for nested, nreq in (sec.get("nested_required") or {}).items():
        if nested in body and isinstance(body[nested], dict):
            for nf in nreq:
                if nf not in body[nested]:
                    issues.append("%s: %s.%s 缺字段 %s" % (label, sec["name"], nested, nf))
    for sf, target in (sec.get("sum_fields") or {}).items():
        if sf in body and isinstance(body[sf], dict):
            try:
                s = sum(float(v) for v in body[sf].values())
            except Exception:
                issues.append("%s: %s.%s 含非数值" % (label, sec["name"], sf))
                s = None
            if s is not None and abs(s - target) > 0.02:
                issues.append("%s: %s.%s 各项之和 %.4f 偏离 %.2f" % (label, sec["name"], sf, s, target))


def _check_forbidden(raw, schema, data, issues, label):
    patterns = schema.get("forbidden_patterns") or []
    if not patterns:
        return
    status = (data.get("document") or {}).get("status") if isinstance(data, dict) else None
    if status not in ("approved", "designed"):
        return
    for pat in patterns:
        if pat in raw:
            issues.append("%s: 状态=%s 但含推测词「%s」" % (label, status, pat))


def check_file(path, expected_pid):
    fn = os.path.basename(path)
    data = _gov.load_yaml(path)
    if not isinstance(data, dict):
        return [("%s: 无法解析为映射" % fn, FAIL)]
    raw = ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception:
        pass
    issues = []
    label = fn

    if fn == "PROJECT_CHARTER.yaml":
        schema = load_schema("project-charter")
        if schema:
            _check_doc_header(data, issues, label)
            for sec in (schema.get("top_level_sections") or []):
                _check_section(data, sec, issues, label)
    elif fn in ("PROJECT_BRIEF.yaml", "AUDIENCE.yaml", "POSITIONING.yaml", "CONTENT_BOUNDARIES.yaml"):
        schema = load_schema("project-brief")
        if schema:
            _check_doc_header(data, issues, label)
            fs = (schema.get("file_sections") or {}).get(fn)
            if fs:
                if fs["section"] not in data:
                    issues.append("%s: 缺段 %s" % (label, fs["section"]))
                else:
                    body = data[fs["section"]]
                    if isinstance(body, dict):
                        for f in fs.get("required_fields", []):
                            if f not in body:
                                issues.append("%s: %s 缺字段 %s" % (label, fs["section"], f))
                    else:
                        issues.append("%s: %s 非映射" % (label, fs["section"]))
            else:
                issues.append("%s: 无对应 file_sections 规则" % label)
    elif fn == "CREATIVE_STRATEGY.yaml":
        schema = load_schema("creative-strategy")
        if schema:
            _check_doc_header(data, issues, label)
            for sec in (schema.get("top_level_sections") or []):
                _check_section(data, sec, issues, label)
    elif fn == "INITIATION_GATE.yaml":
        g = data.get("initiation_gate")
        if not isinstance(g, dict):
            issues.append("%s: 缺 initiation_gate" % label)
        else:
            if g.get("status") not in ("pass", "blocked"):
                issues.append("%s: initiation_gate.status 非法 %r" % (label, g.get("status")))
            if g.get("decision") not in ("approved", "rejected"):
                issues.append("%s: initiation_gate.decision 非法 %r" % (label, g.get("decision")))
    elif os.path.dirname(path).endswith("idea") or fn == "IDEA.yaml":
        schema = load_schema("idea")
        if schema:
            for sec in (schema.get("top_level_sections") or []):
                _check_section(data, sec, issues, label)
    else:
        return None  # 不归本工具校验

    if expected_pid and isinstance(data.get("document"), dict):
        if data["document"].get("project_id") != expected_pid:
            issues.append("%s: document.project_id %r != 期望 %r"
                          % (label, data["document"].get("project_id"), expected_pid))
    return issues


def main():
    ap = argparse.ArgumentParser(description="校验 P0/P1/P2 生命周期制品契约")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--file", default=None, help="仅校验单个文件（覆盖默认扫描）")
    args = ap.parse_args()

    root = os.path.abspath(args.project_root)
    if not os.path.isdir(root):
        sys.stderr.write("✗ 项目根不存在：%s\n" % root)
        sys.exit(2)
    proj = _gov.load_yaml(os.path.join(root, "project.yaml")) or {}
    expected_pid = (proj.get("project") or {}).get("id") or proj.get("id")

    targets = []
    if args.file:
        targets = [os.path.abspath(args.file)]
    else:
        for sub in ("idea", "initiation", "definition"):
            d = os.path.join(root, "lifecycle", sub)
            if os.path.isdir(d):
                for fn in sorted(os.listdir(d)):
                    if fn.endswith((".yaml", ".yml")):
                        targets.append(os.path.join(d, fn))

    if not targets:
        print("（无 lifecycle 制品可校验）")
        sys.exit(0)

    total_issues = 0
    for p in targets:
        res = check_file(p, expected_pid)
        if res is None:
            continue
        fn = os.path.basename(p)
        if not res:
            print("  [%s] %-28s 契约 PASS" % (PASS, fn))
        else:
            total_issues += len(res)
            for it in res:
                print("  [%s] %-28s %s" % (FAIL, fn, it))

    print("")
    if total_issues:
        print("结果：%d 项 FAIL —— 契约不通过。" % total_issues)
        sys.exit(1)
    print("结果：全部 PASS。")
    sys.exit(0)


if __name__ == "__main__":
    main()

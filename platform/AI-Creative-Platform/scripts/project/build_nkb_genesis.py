#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_nkb_genesis.py — 从已通过门禁的 sources 构建 NKB 第一版权威快照

CLI: platform genesis --project-root <dir>

流程（P4）：
  1. 校验 sources/design + sources/canon（复用 validate_sources 门禁）
  2. 按 document.type 映射 NKB 组件，提取初始记录（含 source 元数据）
  3. 写 NKB/<Component>.yaml（records 追加，去重）
  4. 写 NKB/manifest.yaml（snapshot=NKB-GENESIS-001, status=migration, authoritative=pending）

退出码：0=成功；1=门禁失败或提取失败；2=环境错误。
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
import validate_sources as VS

PASS, FAIL = "PASS", "FAIL"
TYPE_TO_COMP = {
    "character": "Characters",
    "canon_rule": "Canon",
    "world": "Canon",
    "item": "Assets",
    "foreshadow": "Foreshadow",
    "location": "Graph",
    "faction": "Graph",
    "conflict": "Graph",
    "arc": "Graph",
    "ability": "Graph",
}
COMP_FILES = {c: c + ".yaml" for c in [
    "Canon", "Characters", "Timeline", "WorldState", "Events",
    "Foreshadow", "Assets", "Terminology", "StoryState", "ReaderState", "Graph"]}
COMP_FILES["Derived"] = "Derived.yaml"


def _scan(directory):
    out = []
    if not os.path.isdir(directory):
        return out
    for dp, _, fs in os.walk(directory):
        for f in fs:
            if f.endswith((".yaml", ".yml")):
                out.append(os.path.join(dp, f))
    return out


def _append_record(nkb_dir, pid, comp, rec):
    fn = COMP_FILES[comp]
    path = os.path.join(nkb_dir, fn)
    if os.path.isfile(path):
        d = _gov.load_yaml(path) or {}
    else:
        d = {}
    d.setdefault("schema_version", "1.2.0")
    d.setdefault("project_id", pid)
    recs = d.get("records") or []
    replaced = False
    for i, r in enumerate(recs):
        if isinstance(r, dict) and r.get("id") == rec["id"]:
            recs[i] = rec
            replaced = True
            break
    if not replaced:
        recs.append(rec)
    d["records"] = recs
    with open(path, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(d) + "\n")


def main():
    ap = argparse.ArgumentParser(description="从 sources 构建 NKB-GENESIS-001")
    ap.add_argument("--project-root", required=True)
    args = ap.parse_args()

    root = os.path.abspath(args.project_root)
    if not os.path.isdir(root):
        sys.stderr.write("✗ 项目根不存在：%s\n" % root)
        sys.exit(2)
    nkb_dir = os.path.join(root, "NKB")
    os.makedirs(nkb_dir, exist_ok=True)
    proj = _gov.load_yaml(os.path.join(root, "project.yaml")) or {}
    pid = (proj.get("project") or {}).get("id") or proj.get("id")

    schema = _gov.load_yaml(VS.SCHEMA_PATH)
    targets = _scan(os.path.join(root, "sources", "design")) + _scan(os.path.join(root, "sources", "canon"))

    # 1. 门禁
    issues_all = []
    for p in targets:
        res = VS.check_one(p, schema, pid)
        if res:
            rel = os.path.relpath(p, root)
            for it in res:
                issues_all.append((rel, it))
    if issues_all:
        print("✗ Genesis 中止：设计源门禁未通过")
        for rel, it in issues_all:
            print("  [%s] %-40s %s" % (FAIL, rel, it))
        sys.exit(1)

    # 2-3. 提取
    today = datetime.date.today().isoformat()
    counts = {}
    for p in targets:
        data = _gov.load_yaml(p)
        doc = data.get("document", {})
        dtype = doc.get("type")
        comp = TYPE_TO_COMP.get(dtype)
        if not comp:
            continue
        secname = (schema.get("type_required") or {}).get(dtype, {}).get("section")
        body = data.get(secname, {}) if secname else data
        rel = os.path.relpath(p, root)
        rec = {
            "id": doc.get("id"),
            "name": body.get("canonical_name") or body.get("name"),
            "kind": dtype,
            "source": {
                "source_type": "design_source",
                "source_file": rel,
                "source_version": doc.get("version"),
                "extracted_at": today,
                "extracted_by": "build_nkb_genesis",
                "approval_status": "pending",
            },
            "body": body,
        }
        _append_record(nkb_dir, pid, comp, rec)
        counts[comp] = counts.get(comp, 0) + 1

    # 4. manifest
    manifest = {
        "nkb": {
            "project_id": pid,
            "schema_version": "1.2.0",
            "snapshot_id": "NKB-GENESIS-001",
            "status": "migration",
            "authoritative": "pending",
            "last_event": "",
            "last_approved_chapter": "",
            "story_time": "story_start",
            "generated_at": today,
        },
        "components": {c: {"file": COMP_FILES[c], "version": counts.get(c, 0)}
                       for c in COMP_FILES},
        "source_roots": [
            "../sources/canon", "../sources/design",
            "../sources/outline", "../sources/governance"],
        "integrity": {
            "unresolved_conflicts": 0,
            "pending_candidates": 0,
            "broken_references": 0,
        },
    }
    with open(os.path.join(nkb_dir, "manifest.yaml"), "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(manifest) + "\n")

    print("✓ NKB Genesis 完成：snapshot=NKB-GENESIS-001, status=migration, authoritative=pending")
    for c in COMP_FILES:
        if counts.get(c):
            print("    %-12s %d 条" % (c, counts[c]))
    if not counts:
        print("  （无 design/canon 文件被提取；请先完成 P3 设计源）")
    sys.exit(0)


if __name__ == "__main__":
    main()

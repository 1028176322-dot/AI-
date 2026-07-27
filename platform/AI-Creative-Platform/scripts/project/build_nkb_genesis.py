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
import shutil
import sys
import datetime
import tempfile

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
import nkb_validator

PASS, FAIL = "PASS", "FAIL"
TYPE_TO_COMP = {
    "character": "Characters",
    "canon_rule": "Canon",
    "world": "Canon",
    "item": "Assets",
    "foreshadow": "Foreshadow",
    "location": "Locations",
    "faction": "Organizations",
    "organization": "Organizations",
    "conflict": "StoryState",
    "arc": "StoryState",
    "ability": "Canon",
    "terminology": "Terminology",
    "world_state": "WorldState",
    "reader_state": "ReaderState",
    "timeline": "Timeline",
    "event": "Events",
    "graph": "Graph",
}
COMP_FILES = {c: c + ".yaml" for c in [
    "Canon", "Characters", "Locations", "Organizations", "Timeline",
    "WorldState", "Events", "Foreshadow", "Assets", "Terminology",
    "StoryState", "ReaderState", "Graph"]}
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
    d.setdefault("schema_version", "1.3.0")
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


def _normalize_record(dtype, rec):
    """Project an approved design source into the canonical 1.3 record shape."""
    rec = dict(rec)
    if dtype in ("canon_rule", "world", "ability"):
        rec.setdefault("category", {
            "canon_rule": "rule",
            "world": "world",
            "ability": "ability",
        }[dtype])
        if not any(rec.get(key) not in (None, "") for key in (
                "name", "statement", "detail")):
            rec["detail"] = dict(rec)
    elif dtype == "item":
        rec.setdefault("state", rec.get("status", "initial"))
        rec.setdefault("abilities", [])
        rec.setdefault("limitations", [])
    elif dtype in ("conflict", "arc"):
        rec.setdefault("state", rec.get("status", "planned"))
        rec.setdefault(
            "active_conflicts", [rec.get("id")] if dtype == "conflict" else [])
        rec.setdefault(
            "unresolved_questions",
            [rec.get("description")] if rec.get("description") else [])
        rec.setdefault("next_constraints", [])
    return rec


def main():
    ap = argparse.ArgumentParser(description="从 sources 构建 NKB-GENESIS-001")
    ap.add_argument("--project-root", required=True)
    args = ap.parse_args()

    root = os.path.abspath(args.project_root)
    if not os.path.isdir(root):
        sys.stderr.write("[BLOCK] 项目根不存在：%s\n" % root)
        sys.exit(2)
    canonical_nkb_dir = os.path.join(root, "NKB")
    proj = _gov.load_yaml(os.path.join(root, "project.yaml")) or {}
    pid = (proj.get("project") or {}).get("id") or proj.get("id")
    if os.path.isfile(os.path.join(root, "PROJECT_LAYOUT.yaml")):
        approval_path = os.path.join(
            root, "lifecycle", "design", "DESIGN_APPROVAL.yaml")
        approval = _gov.load_yaml(approval_path) if os.path.isfile(
            approval_path) else {}
        approval_body = (approval or {}).get("design_approval") or {}
        if (approval_body.get("decision") != "pass"
                or approval_body.get("genesis_allowed") is not True):
            print("[BLOCK] Genesis 中止：strict 新项目缺少通过的 DESIGN_APPROVAL")
            print("  先运行 platform design gate --project-root <dir>")
            sys.exit(1)

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
        print("[BLOCK] Genesis 中止：设计源门禁未通过")
        for rel, it in issues_all:
            print("  [%s] %-40s %s" % (FAIL, rel, it))
        sys.exit(1)

    runtime_dir = os.path.join(root, "runtime")
    os.makedirs(runtime_dir, exist_ok=True)
    staging_root = tempfile.mkdtemp(
        prefix="nkb-genesis-", dir=runtime_dir)
    nkb_dir = os.path.join(staging_root, "NKB")
    os.makedirs(nkb_dir, exist_ok=True)
    shutil.copy2(
        os.path.join(root, "project.yaml"),
        os.path.join(staging_root, "project.yaml"))
    with open(os.path.join(staging_root, "PROJECT_LAYOUT.yaml"),
              "w", encoding="utf-8") as stream:
        stream.write("version: 2.0.0\nstrict: true\n")
    for source_path in targets:
        relative = os.path.relpath(source_path, root)
        staged_source = os.path.join(staging_root, relative)
        os.makedirs(os.path.dirname(staged_source), exist_ok=True)
        shutil.copy2(source_path, staged_source)
    for component in COMP_FILES:
        _gov.dump_yaml(os.path.join(nkb_dir, COMP_FILES[component]), {
            "schema_version": "1.3.0",
            "project_id": pid,
            "records": [],
        })

    # 2-3. 提取
    today = datetime.date.today().isoformat()
    counts = {}
    for p in targets:
        data = _gov.load_yaml(p)
        doc = data.get("document", {})
        dtype = doc.get("type")
        if doc.get("status") != "approved":
            continue
        comp = TYPE_TO_COMP.get(dtype)
        if not comp:
            continue
        secname = (schema.get("type_required") or {}).get(dtype, {}).get("section")
        body = data.get(secname, {}) if secname else data
        rel = os.path.relpath(p, root)
        rec = dict(body) if isinstance(body, dict) else {}
        for field in (
                "identity", "personality", "speech", "abilities",
                "relationships", "secrets", "knowledge_state", "metadata"):
            if field in data and field not in rec:
                rec[field] = data[field]
        rec["id"] = doc.get("id")
        rec["name"] = (
            rec.get("canonical_name") or rec.get("name") or doc.get("title"))
        rec.setdefault("type", dtype)
        rec["source"] = {
                "source_type": "design_source",
                "source_file": rel,
                "source_anchor": secname or dtype,
                "source_version": doc.get("version"),
                "extracted_at": today,
                "extracted_by": "build_nkb_genesis",
                "approval_status": "approved",
            }
        rec["fact_status"] = {
                "designed": True, "occurred": False,
                "revealed_to_reader": False,
                "known_by_characters": [],
            }
        rec = _normalize_record(dtype, rec)
        _append_record(nkb_dir, pid, comp, rec)
        counts[comp] = counts.get(comp, 0) + 1

    # 4. manifest
    manifest = {
        "nkb": {
            "project_id": pid,
            "schema_version": "1.3.0",
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

    validation = nkb_validator.validate_project(staging_root)
    report_path = os.path.join(staging_root, "validation-report.yaml")
    _gov.dump_yaml(report_path, validation)
    if validation["gate"]["decision"] == "block":
        print("[BLOCK] Genesis 中止：canonical NKB 校验未通过")
        for finding in validation.get("findings", []):
            if finding.get("severity") == "fail":
                print("  [%s] %s %s" % (
                    FAIL, finding.get("code"), finding.get("detail")))
        print("  暂存证据：%s" % staging_root)
        sys.exit(1)

    os.makedirs(canonical_nkb_dir, exist_ok=True)
    for filename in list(COMP_FILES.values()) + ["manifest.yaml"]:
        os.replace(
            os.path.join(nkb_dir, filename),
            os.path.join(canonical_nkb_dir, filename))
    shutil.rmtree(staging_root, ignore_errors=True)

    print("[PASS] NKB Genesis 完成：snapshot=NKB-GENESIS-001, status=migration, authoritative=pending")
    for c in COMP_FILES:
        if counts.get(c):
            print("    %-12s %d 条" % (c, counts[c]))
    if not counts:
        print("  （无 design/canon 文件被提取；请先完成 P3 设计源）")
    sys.exit(0)


if __name__ == "__main__":
    main()

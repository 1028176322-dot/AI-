#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
readiness_gate.py — 项目开写验收（P5）+ 编排器 Pre-flight

CLI:
  platform ready --project-root <dir>                 # 六维检查，写报告
  platform ready --project-root <dir> --approve        # 验收通过并置 ready_for_writing
  platform ready --project-root <dir> --preflight      # 编排器前置检查（JSON）

六维（A-F）见 core/project-lifecycle/开写准备度规范.md。
--preflight 返回：
  {"result":"READY", ...}                       exit 0
  {"result":"BLOCKED_PROJECT_NOT_READY","missing":[...]}  exit 1
Legacy 项目（lifecycle_status=writing & legacy_backfill_required=true）直接放行（祖父化）。
"""
import argparse
import os
import sys
import datetime
import json

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
import nkb_validator
import validate_charter as VC
import validate_sources as VS
import outline_governance

PASS, FAIL, WARN = "pass", "fail", "warn"


def _scan(directory):
    out = []
    if not os.path.isdir(directory):
        return out
    for dp, _, fs in os.walk(directory):
        for f in fs:
            if f.endswith((".yaml", ".yml")):
                out.append(os.path.join(dp, f))
    return out


def _load(p):
    if os.path.isfile(p):
        return _gov.load_yaml(p)
    return None


def _design_docs(root, document_type):
    result = []
    for source_root in (
            os.path.join(root, "sources", "design"),
            os.path.join(root, "sources", "canon")):
        if not os.path.isdir(source_root):
            continue
        for path in _scan(source_root):
            data = _load(path) or {}
            document = data.get("document") or {}
            if (document.get("type") == document_type
                    and document.get("status") == "approved"):
                result.append(data)
    return result


def _dim_project(root, pid):
    miss = []
    if os.path.isfile(os.path.join(root, "PROJECT_LAYOUT.yaml")):
        design_approval = _load(os.path.join(
            root, "lifecycle", "design", "DESIGN_APPROVAL.yaml")) or {}
        approval = design_approval.get("design_approval") or {}
        if (approval.get("decision") != "pass"
                or approval.get("genesis_allowed") is not True):
            miss.append("design.approval")
    charter = os.path.join(root, "lifecycle", "initiation", "PROJECT_CHARTER.yaml")
    if not os.path.isfile(charter):
        miss.append("charter")
    else:
        if VC.check_file(charter, pid):
            miss.append("charter.valid")
        cd = _load(charter) or {}
        if not (cd.get("scope") and cd["scope"].get("included")):
            miss.append("charter.scope")
        gate = os.path.join(root, "lifecycle", "initiation", "INITIATION_GATE.yaml")
        if os.path.isfile(gate):
            g = (_load(gate) or {}).get("initiation_gate", {})
            if g.get("status") != "pass":
                miss.append("charter.gate_pass")
    brief = os.path.join(root, "lifecycle", "definition", "PROJECT_BRIEF.yaml")
    if not os.path.isfile(brief):
        miss.append("brief")
    else:
        if VC.check_file(brief, pid):
            miss.append("brief.valid")
    if not os.path.isfile(os.path.join(root, "lifecycle", "definition", "AUDIENCE.yaml")):
        miss.append("audience")
    return miss


def _dim_story(root, pid):
    miss = []
    charter = _load(os.path.join(root, "lifecycle", "initiation", "PROJECT_CHARTER.yaml")) or {}
    if not (charter.get("concept") or {}).get("one_sentence_premise"):
        miss.append("story.premise")
    story_docs = _design_docs(root, "story_core")
    story = (story_docs[0].get("story") or {}) if story_docs else {}
    sdir = os.path.join(root, "sources", "design", "story")
    names = [os.path.basename(p) for p in _scan(sdir)]
    if not story.get("central_conflict") and "CENTRAL_CONFLICT.yaml" not in names:
        miss.append("story.central_conflict")
    if not story.get("story_promise") and "STORY_PROMISE.yaml" not in names:
        miss.append("story.promise")
    if not story.get("ending_direction") and "ENDING_DESIGN.yaml" not in names:
        miss.append("story.ending")
    chars = _scan(os.path.join(root, "sources", "design", "characters"))
    any_goal = False
    for c in chars:
        cb = (_load(c) or {}).get("character", {})
        if cb.get("goal") or cb.get("goals"):
            any_goal = True
            break
    if not any_goal:
        miss.append("story.protagonist_goal")
    return miss


def _dim_world(root):
    miss = []
    canon = os.path.join(root, "sources", "canon")
    if (not os.path.isfile(os.path.join(canon, "world.yaml"))
            and not _design_docs(root, "world")):
        miss.append("world.core")
    canon_rules = _design_docs(root, "canon_rule")
    if (not os.path.isfile(os.path.join(canon, "immutable-rules.yaml"))
            and not canon_rules):
        miss.append("world.immutable_rules")
    if (not os.path.isfile(os.path.join(canon, "power-system.yaml"))
            and not _design_docs(root, "ability")):
        miss.append("world.power_limits")
    if not _scan(os.path.join(root, "sources", "design", "locations")):
        miss.append("world.initial_locations")
    return miss


def _dim_characters(root):
    miss = []
    chars = _scan(os.path.join(root, "sources", "design", "characters"))
    if not chars:
        miss.append("characters.protagonist")
        return miss
    any_ooc = any((
        (_load(c) or {}).get("character", {}).get("forbidden_behaviors")
        or (((_load(c) or {}).get("character", {}).get("personality") or {})
            .get("forbidden_behaviors"))
        for c in chars))
    if not any_ooc:
        miss.append("characters.ooc_boundaries")
    if len(chars) < 2:
        miss.append("characters.core_cast")
    any_rel = any(((_load(c) or {}).get("character", {}).get("relationships"))
                  for c in chars)
    if not any_rel:
        miss.append("characters.initial_relationships")
    return miss


def _dim_planning(root):
    miss = []
    if os.path.isfile(os.path.join(root, "PROJECT_LAYOUT.yaml")):
        report = outline_governance.validate_project(
            root, write=False, require_approved=True)
        body = report["outline_validation"]
        if body["gate"]["decision"] != "proceed":
            miss.append("planning.outline_governance")
            miss.extend([
                "planning.%s" % item
                for item in body["gate"]["reasons"][:10]
            ])
        return miss
    out = os.path.join(root, "sources", "outline")
    if not _scan(os.path.join(out, "series")) and not os.path.isfile(os.path.join(out, "series.yaml")):
        miss.append("planning.series_direction")
    if not _scan(os.path.join(out, "volumes")):
        miss.append("planning.first_volume_outline")
    chaps = _scan(os.path.join(out, "chapters"))
    chaps += _scan(os.path.join(root, "sources", "manuscripts", "volume-01"))
    if not chaps:
        miss.append("planning.chapters_planned")
    if len(chaps) < 3:
        miss.append("planning.first_three_detailed")
    if len(chaps) < 10:
        miss.append("planning.first_ten_chapters")
    return miss


def _dim_nkb(root, pid):
    miss = []
    manifest = _load(os.path.join(root, "NKB", "manifest.yaml"))
    if not (manifest and (manifest.get("nkb") or {}).get("snapshot_id", "").startswith("NKB-GENESIS")):
        miss.append("nkb.genesis_completed")
        return miss
    nb = manifest["nkb"]
    if nb.get("schema_version") != "1.3.0":
        miss.append("nkb.schema_valid")
    integ = manifest.get("integrity", {})
    if integ.get("unresolved_conflicts", 0) != 0:
        miss.append("nkb.unresolved_conflicts")
    if integ.get("broken_references", 0) != 0:
        miss.append("nkb.broken_references")
    if not os.path.isfile(os.path.join(root, "NKB", "Terminology.yaml")):
        miss.append("nkb.terminology")
    rs = _load(os.path.join(root, "NKB", "ReaderState.yaml"))
    if not (rs and rs.get("records")):
        miss.append("nkb.reader_state_initialized")
    for component in (
            "Canon", "Characters", "Locations", "StoryState",
            "ReaderState", "Terminology"):
        data = _load(os.path.join(root, "NKB", "%s.yaml" % component))
        if not (data and data.get("records")):
            miss.append("nkb.%s_initialized" % component.lower())
    validation = nkb_validator.validate_project(root)
    if validation["gate"]["decision"] == "block":
        miss.append("nkb.canonical_validation")
    return miss


def evaluate(root, pid):
    return {
        "A": _dim_project(root, pid),
        "B": _dim_story(root, pid),
        "C": _dim_world(root),
        "D": _dim_characters(root),
        "E": _dim_planning(root),
        "F": _dim_nkb(root, pid),
    }


def main():
    ap = argparse.ArgumentParser(description="项目开写验收 + 编排器 pre-flight")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--preflight", action="store_true", help="仅做编排器前置检查（JSON 输出）")
    ap.add_argument("--approve", action="store_true", help="验收通过后置 lifecycle_status=ready_for_writing")
    args = ap.parse_args()

    root = os.path.abspath(args.project_root)
    if not os.path.isdir(root):
        sys.stderr.write("✗ 项目根不存在：%s\n" % root)
        sys.exit(2)
    proj = _gov.load_yaml(os.path.join(root, "project.yaml")) or {}
    pid = (proj.get("project") or {}).get("id") or proj.get("id")

    status_path = os.path.join(root, "lifecycle", "status.yaml")
    status = _load(status_path) or {}
    cur = status.get("lifecycle_status", "unknown")
    legacy = bool(status.get("legacy_backfill_required"))

    dims = evaluate(root, pid)
    overall_fail = any(dims[k] for k in dims)
    missing = [m for k in dims for m in dims[k]]

    if args.preflight:
        if cur == "ready_for_writing":
            print(json.dumps({"result": "READY", "lifecycle_status": cur}, ensure_ascii=False))
            sys.exit(0)
        if legacy and cur == "writing":
            print(json.dumps({"result": "READY", "lifecycle_status": cur,
                              "note": "legacy grandfathered", "legacy_backfill_required": True},
                             ensure_ascii=False))
            sys.exit(0)
        print(json.dumps({"result": "BLOCKED_PROJECT_NOT_READY",
                          "current_status": cur, "missing": missing}, ensure_ascii=False))
        sys.exit(1)

    # 完整报告
    today = datetime.date.today().isoformat()
    report = {
        "readiness_report": {
            "checked_at": today,
            "dimensions": {k: (FAIL if dims[k] else PASS) for k in dims},
            "missing": missing,
            "overall": (FAIL if (overall_fail and not legacy) else PASS),
        }
    }
    if legacy:
        report["readiness_report"]["note"] = "legacy 项目：祖父化放行，但须补回 charter/brief/readiness 制品"
    with open(os.path.join(root, "lifecycle", "readiness", "READINESS_REPORT.yaml"), "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(report) + "\n")

    # 打印
    for k in dims:
        res = FAIL if dims[k] else PASS
        detail = "" if not dims[k] else " 缺失: " + ", ".join(dims[k])
        print("  [%s] 维度 %s%s" % (res.upper(), k, detail))
    print("")
    if overall_fail and not legacy:
        print("结果：FAIL —— 未达开写条件。")
        if args.approve:
            print("✗ 验收未通过，拒绝 --approve。")
            sys.exit(1)
        sys.exit(1)

    # 通过（或非 legacy 放行）
    snap = (_load(os.path.join(root, "NKB", "manifest.yaml")) or {}).get("nkb", {}).get("snapshot_id", "")
    approval = {
        "readiness_gate": {
            "status": PASS,
            "approved_by": ("user" if args.approve else "pending"),
            "approved_at": (today if args.approve else ""),
            "entry_point": "CH-001",
            "nkb_snapshot": snap,
        }
    }
    with open(os.path.join(root, "lifecycle", "readiness", "READINESS_APPROVAL.yaml"), "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(approval) + "\n")

    if args.approve:
        status["lifecycle_status"] = "ready_for_writing"
        status["current_stage"] = "P6"
        status["updated_at"] = today
        status["updated_by"] = "readiness_gate"
        with open(status_path, "w", encoding="utf-8") as f:
            f.write(_gov.dump_block(status) + "\n")
        print("✓ 验收通过，lifecycle_status 已置 ready_for_writing。")
    else:
        print("结果：PASS —— 已达开写条件（加 --approve 正式放行）。")
    sys.exit(0)


if __name__ == "__main__":
    main()

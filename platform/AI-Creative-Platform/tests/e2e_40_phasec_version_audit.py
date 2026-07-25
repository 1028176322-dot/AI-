#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""e2e_40_phasec_version_audit.py — Phase C 验收（PC-2）：
  - version_commit.snapshot / list_snapshots（项目级快照 + manifest）
  - version_commit.compare_versions（两 revision 文本 diff）
  - audit_report.audit_report（聚合 audit.log.jsonl）
  - doctor 接线（VersionGov + AuditGov 存在于 platform_cli）
脚本只做确定性校验，不替 AI 下质量结论。
"""
import os
import sys
import json
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
PLAT = os.path.dirname(HERE)
TOOLS = os.path.join(PLAT, "tools")
for _p in (PLAT, TOOLS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import version_commit as vc
import audit_report as ar

PASS_CNT = 0
FAIL_CNT = 0


def check(name, cond, detail=""):
    global PASS_CNT, FAIL_CNT
    if cond:
        PASS_CNT += 1
        print("  [PASS] %s" % name)
    else:
        FAIL_CNT += 1
        print("  [FAIL] %s%s" % (name, (" — " + detail) if detail else ""))


def _seed_project(proot):
    os.makedirs(os.path.join(proot, "NKB"))
    with open(os.path.join(proot, "NKB", "Characters.yaml"), "w", encoding="utf-8") as f:
        f.write("schema_version: 1.2.0\nproject_id: novel-x\nrecords: []\n")
    with open(os.path.join(proot, "project.yaml"), "w", encoding="utf-8") as f:
        f.write("project:\n  id: novel-x\n  name: X\n  type: xuanhuan\npaths:\n  nkb: ./NKB\n")


# ── 1. snapshot ────────────────────────────────────────────
def test_snapshot():
    tmp = tempfile.mkdtemp(prefix="e2e40s_")
    try:
        proot = os.path.join(tmp, "proj")
        _seed_project(proot)
        m = vc.snapshot(proot, label="t1", author="tester")
        check("snapshot 返回 manifest", isinstance(m, dict) and "snapshot" in m, str(m))
        check("snapshot 含 files>0", len(m.get("files", [])) > 0, str(len(m.get("files", []))))
        snap_dir = os.path.join(proot, "versions", "snapshots", m["snapshot"])
        check("快照目录存在", os.path.isdir(snap_dir))
        check("manifest.yaml 存在", os.path.isfile(os.path.join(snap_dir, "manifest.yaml")))
        check("NKB 被复制", os.path.isfile(os.path.join(snap_dir, "NKB", "Characters.yaml")))
        snaps = vc.list_snapshots(proot)
        check("list_snapshots 含该快照", len(snaps) == 1 and snaps[0]["snapshot"] == m["snapshot"])
        # include 额外路径
        os.makedirs(os.path.join(proot, "extra"))
        with open(os.path.join(proot, "extra", "x.txt"), "w", encoding="utf-8") as f:
            f.write("hi")
        m2 = vc.snapshot(proot, label="t2", include=["extra"])
        inc_files = [f["path"] for f in m2.get("files", [])]
        check("include 捕获 extra", any(p.startswith("extra") for p in inc_files), str(inc_files))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── 2. compare_versions ────────────────────────────────────
def test_compare():
    tmp = tempfile.mkdtemp(prefix="e2e40c_")
    try:
        proot = os.path.join(tmp, "proj")
        os.makedirs(proot)
        # 注：version_commit 既有实现将 after/before 存为原始文本，多行内容会在 reload 时报错
        # （既有缺陷，非 PC-2 引入）；此处用 YAML 安全的单行内容验证 compare_versions 逻辑。
        vc.commit(proot, "chapter", "CH1", after="alpha beta gamma", author="t")
        vc.commit(proot, "chapter", "CH1", after="alpha BETA gamma delta", author="t")
        res = vc.compare_versions(proot, "chapter", "CH1")
        check("compare 无 error", "error" not in res, str(res))
        check("compare similarity<1", res.get("similarity", 1) < 1, str(res.get("similarity")))
        check("compare added>0", res.get("added", 0) > 0, str(res.get("added")))
        check("compare removed>0", res.get("removed", 0) > 0, str(res.get("removed")))
        check("compare diff 非空", len(res.get("diff", [])) > 0)
        # 指定 rev（按 id）比较
        res2 = vc.compare_versions(proot, "chapter", "CH1", rev_a=0, rev_b=1)
        check("compare 指定索引可用", "error" not in res2)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── 3. audit_report ───────────────────────────────────────
def test_audit():
    tmp = tempfile.mkdtemp(prefix="e2e40a_")
    try:
        proot = os.path.join(tmp, "proj")
        os.makedirs(os.path.join(proot, "audit"))
        recs = [
            {"op_id": "OP-000001", "ts": "2026-07-25T10:00:00", "action": "cwrite", "role": "writer", "agent": "a1"},
            {"op_id": "OP-000002", "ts": "2026-07-25T11:00:00", "action": "ver_commit", "role": "system", "agent": "a1"},
            {"op_id": "OP-000003", "ts": "2026-07-25T12:00:00", "action": "cwrite", "role": "writer", "agent": "a2"},
        ]
        with open(os.path.join(proot, "audit", "audit.log.jsonl"), "w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        rep = ar.audit_report(proot)
        check("audit total=3", rep["total"] == 3, str(rep["total"]))
        check("audit by_action", rep["by_action"].get("cwrite") == 2 and rep["by_action"].get("ver_commit") == 1, str(rep["by_action"]))
        check("audit by_role", rep["by_role"].get("writer") == 2, str(rep["by_role"]))
        check("audit by_agent", rep["by_agent"].get("a1") == 2 and rep["by_agent"].get("a2") == 1, str(rep["by_agent"]))
        check("audit recent 长度", len(rep["recent"]) == 3)
        gov = ar.govern(proot)
        check("AuditGov proceed", gov["gate"]["decision"] == "proceed", gov["gate"]["decision"])
        # 缺失日志 → caution
        empty = os.path.join(tmp, "empty")
        os.makedirs(empty)
        check("AuditGov 缺失→caution", ar.govern(empty)["gate"]["decision"] == "caution")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── 4. doctor 接线（源码级）─────────────────────────────────
def test_wiring():
    cli_path = os.path.join(TOOLS, "platform_cli.py")
    src = open(cli_path, encoding="utf-8").read()
    check("doctor 含 VersionGov 块", "VersionGov" in src)
    check("doctor 含 AuditGov 块", "AuditGov" in src)
    check("ver 委托 version_commit", '"ver": "version_commit"' in src)
    check("audit 委托 audit_report", '"audit": "audit_report"' in src)


if __name__ == "__main__":
    test_snapshot()
    test_compare()
    test_audit()
    test_wiring()
    print("\n=== e2e_40 结果：%d/%d PASS ===" % (PASS_CNT, PASS_CNT + FAIL_CNT))
    sys.exit(1 if FAIL_CNT else 0)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os as _os, sys as _sys
_PLAT2 = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PLAT2 not in _sys.path:
    _sys.path.insert(0, _PLAT2)
_SCR2 = _os.path.join(_PLAT2, "scripts")
if _os.path.isdir(_SCR2):
    for _d in _os.listdir(_SCR2):
        _p = _os.path.join(_SCR2, _d)
        if _os.path.isdir(_p) and _p not in _sys.path:
            _sys.path.insert(0, _p)
if _os.path.join(_PLAT2, "cli") not in _sys.path:
    _sys.path.insert(0, _os.path.join(_PLAT2, "cli"))
"""e2e_39_phasec_init_doctor.py — Phase C 验收：
  - apply-template 题材注入（profile.defaults → gates/capabilities 注入 + 平台基线回落）
  - ProjectGov 基线健康块（project_health.govern：proceed/caution/block）
  - doctor 接线（ProjectGov 块 + _run_gov 执行器存在于 platform_cli）
脚本只做确定性校验，不替 AI 下质量结论。
"""
import os
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
PLAT = os.path.dirname(HERE)
TOOLS = os.path.join(PLAT, "tools")
for _p in (PLAT, TOOLS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import _yaml_lite
import project_template as pt
import project_health as ph

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


# ── 1. apply-template 题材注入 ──────────────────────────────
def test_injection():
    tmp = tempfile.mkdtemp(prefix="e2e39_")
    try:
        # Case A：profile 提供 defaults（覆盖部分 gates + 自定义 capabilities 列表）
        proot = os.path.join(tmp, "proj")
        os.makedirs(proot)
        profile = {
            "display_name": "测试题材",
            "description": "unit-test genre",
            "defaults": {
                "gates": {"editor_score": 70, "reader_index": 55},
                "capabilities": [
                    "capability.narrative.default@2.0.0",
                    "capability.battle.xuanhuan@2.1.0",
                ],
            },
        }
        pt._write_project_yaml(proot, "novel-test", "测试项目", "testgenre", "1.3.0", profile)
        data = _yaml_lite.load_file(os.path.join(proot, "project.yaml"))
        gates = data.get("gates") or {}
        caps = data.get("capabilities") or {}
        check("注入 gates.editor_score=70", gates.get("editor_score") == 70, str(gates))
        check("注入 gates.reader_index=55", gates.get("reader_index") == 55)
        check("基线回落 max_loop=5", gates.get("max_loop") == 5)
        check("基线回落 consistency_index=0.95", gates.get("consistency_index") == 0.95)
        check("注入 capabilities 含 2 项", len(caps) == 2 and "narrative" in caps and "battle" in caps, str(caps))
        check("注入 capabilities 值正确", caps.get("battle") == "capability.battle.xuanhuan@2.1.0")
        raw = open(os.path.join(proot, "project.yaml"), encoding="utf-8").read()
        check("project.yaml 含题材注释", "display_name: 测试题材" in raw and "description: unit-test genre" in raw)

        # Case B：profile=None → 全平台基线
        proot2 = os.path.join(tmp, "proj2")
        os.makedirs(proot2)
        pt._write_project_yaml(proot2, "novel-def", "默认项目", "xuanhuan", "1.3.0", None)
        data2 = _yaml_lite.load_file(os.path.join(proot2, "project.yaml"))
        g2 = data2.get("gates") or {}
        c2 = data2.get("capabilities") or {}
        check("基线 editor_score=80", g2.get("editor_score") == 80)
        check("基线 6 项 capabilities", len(c2) == 6, str(len(c2)))
        check("基线路径 nkb 存在键", "nkb" in (data2.get("paths") or {}))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── 2. ProjectGov 基线自检 ─────────────────────────────────
GOOD = (
    "project:\n  id: novel-x\n  name: X\n  type: xuanhuan\n  status: active\n"
    "requires:\n  platform: \">=2.1.0\"\n  nkb_schema: \">=1.2.0\"\n  contracts: \">=1.0.0\"\n"
    "  templates:\n    xuanhuan: \">=1.3.0\"\n"
    "paths:\n  nkb: ./NKB\n  outline: ./outline.md\n  chapters: ./txt\n"
    "  artifacts: ./artifacts\n  overrides: ./overrides\n  memory: ./memory/project\n"
    "gates:\n  editor_score: 80\n  consistency_index: 0.95\n  reader_index: 60\n"
    "  payment_intent: 60\n  max_loop: 5\n"
)


def _write_proj(proot, yaml_text):
    os.makedirs(proot, exist_ok=True)
    with open(os.path.join(proot, "project.yaml"), "w", encoding="utf-8") as f:
        f.write(yaml_text)


def test_project_health():
    tmp = tempfile.mkdtemp(prefix="e2e39h_")
    try:
        good = os.path.join(tmp, "good")
        for p in ["NKB", "outline.md", "txt", "artifacts", "overrides", "memory/project"]:
            full = os.path.join(good, p)
            if p.endswith(".md"):
                open(full, "w", encoding="utf-8").close()
            else:
                os.makedirs(full, exist_ok=True)
        _write_proj(good, GOOD)
        r = ph.govern(good)
        check("ProjectGov 良好→proceed", r["gate"]["decision"] == "proceed", r["gate"]["decision"])
        check("ProjectGov 良好→health 100", r["composite"]["health"] == 100)
        check("ProjectGov 良好→summary ok", r["response"]["summary"] == "ok")

        bad = os.path.join(tmp, "bad")
        bad_yaml = GOOD.replace("  payment_intent: 60\n", "").replace("  nkb: ./NKB\n", "  nkb: ./NOPE\n")
        _write_proj(bad, bad_yaml)
        rb = ph.govern(bad)
        check("ProjectGov 软问题→caution", rb["gate"]["decision"] == "caution", rb["gate"]["decision"])
        check("ProjectGov caution 记录 bad_gates", "payment_intent" in (rb["response"]["bad_gates"] or []))
        check("ProjectGov caution 记录 missing_paths", "nkb" in (rb["response"]["missing_paths"] or []))

        blk = os.path.join(tmp, "blk")
        _write_proj(blk, "requires:\n  platform: \">=2.1.0\"\npaths:\n  nkb: ./NKB\n")
        rk = ph.govern(blk)
        check("ProjectGov 缺必需键→block", rk["gate"]["decision"] == "block", rk["gate"]["decision"])
        check("ProjectGov block→health<100", isinstance(rk["composite"]["health"], int) and rk["composite"]["health"] < 100, str(rk["composite"]["health"]))

        miss = os.path.join(tmp, "miss")
        os.makedirs(miss)
        rm = ph.govern(miss)
        check("ProjectGov 缺 project.yaml→block", rm["gate"]["decision"] == "block")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── 3. doctor 接线（源码级）─────────────────────────────────
def test_wiring():
    cli_path = os.path.join(_PLAT2, "cli", "platform.py")
    src = open(cli_path, encoding="utf-8").read()
    check("doctor 含 ProjectGov 块", "ProjectGov" in src)
    check("doctor 含 _run_gov 执行器", "_run_gov" in src)
    check("ProjectGov 调用 project_health.govern", "project_health" in src)


if __name__ == "__main__":
    test_injection()
    test_project_health()
    test_wiring()
    print("\n=== e2e_39 结果：%d/%d PASS ===" % (PASS_CNT, PASS_CNT + FAIL_CNT))
    sys.exit(1 if FAIL_CNT else 0)

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
"""e2e_41_phasec_status_derive.py — Phase C 验收（PC-3）：
  - status_derive.derive：从任务系统 + NKB 派生项目状态（不手填）
  - 任务计数 / 章节前沿 / failed 阻塞检测 / NKB 组件计数 / 伏笔未回收
  - status_derive.govern：StatusGov 健康块（block/caution/proceed）
  - doctor 接线（StatusGov 存在于 platform_cli）+ status_update derive 动词
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

import status_derive as sd

PASS_CNT = 0
FAIL_CNT = 0


def check(name, cond, detail=""):
    global PASS_CNT, FAIL_CNT
    if cond:
        PASS_CNT += 1
        print("  [PASS] %s" % name)
    else:
        FAIL_CNT += 1
        print("  [FAIL] %s  %s" % (name, detail))


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _mk_project(tmp):
    """构建一个最小项目：project.yaml + NKB（Characters + Foreshadow）+ tasks。"""
    proot = os.path.join(tmp, "proj")
    _write(os.path.join(proot, "project.yaml"),
           "project:\n  id: novel-dsf\n  name: 道法百年\n  type: novel\n")
    # NKB
    _write(os.path.join(proot, "NKB", "Characters.yaml"),
           "schema_version: 1.2.0\nproject_id: novel-dsf\nrecords:\n"
           "  - id: CHR-001\n    name: 肖凡\n"
           "  - id: CHR-002\n    name: 无为子\n")
    _write(os.path.join(proot, "NKB", "Foreshadow.yaml"),
           "schema_version: 1.2.0\nproject_id: novel-dsf\nrecords:\n"
           "  - id: FB-001\n    name: a\n    status: 未回收\n"
           "  - id: FB-002\n    name: b\n    status: 已回收\n"
           "  - id: FB-003\n    name: c\n    status: resolved\n")
    # tasks：completed 章节审查 / running 章节写作 / failed
    _write(os.path.join(proot, "tasks", "completed", "TASK-REV-CH10.yaml"),
           "task:\n  id: TASK-REV-CH10\n  status: completed\n"
           "  type: chapter_review\n  title: 第一卷 Ch10 审查\n")
    _write(os.path.join(proot, "tasks", "running", "TASK-WR-CH21.yaml"),
           "task:\n  id: TASK-WR-CH21\n  status: running\n"
           "  type: chapter_write\n  title: 第一卷 Ch21-40 写作\n")
    _write(os.path.join(proot, "tasks", "failed", "TASK-BAD.yaml"),
           "task:\n  id: TASK-BAD\n  status: failed\n"
           "  type: chapter_write\n  title: 第一卷 Ch50 写作\n")
    return proot


def test_derive():
    tmp = tempfile.mkdtemp()
    try:
        proot = _mk_project(tmp)
        res = sd.derive(proot, write=True)
        # 任务计数
        by_state = res["tasks"]["by_state"]
        check("tasks total", res["tasks"]["total"] == 3, str(res["tasks"]))
        check("by_state completed", by_state.get("completed") == 1, str(by_state))
        check("by_state running", by_state.get("running") == 1, str(by_state))
        check("by_state failed", by_state.get("failed") == 1, str(by_state))
        check("active_types 含 chapter_write",
              "chapter_write" in res["tasks"]["active_types"], str(res["tasks"]["active_types"]))
        # 章节前沿（max 覆盖所有任务，含 failed 的 Ch50）
        check("current_chapter_frontier=50",
              res["progress"]["current_chapter_frontier"] == 50,
              str(res["progress"]["current_chapter_frontier"]))
        # 阻塞
        check("blocked=True", res["blocked"]["is_blocked"] is True, str(res["blocked"]))
        check("failed_tasks 记录", "TASK-BAD" in res["blocked"]["failed_tasks"], str(res["blocked"]))
        # 同类型、同标题的后续完成任务会关闭历史失败，不永久阻塞项目。
        _write(os.path.join(proot, "tasks", "completed", "TASK-BAD-REPLACEMENT.yaml"),
               "task:\n  id: TASK-BAD-REPLACEMENT\n  status: completed\n"
               "  type: chapter_write\n  title: 第一卷 Ch50 写作\n"
               "  created: 2026-07-27T10:00:00\n")
        res_resolved = sd.derive(proot, write=False)
        check("后续完成任务解除历史失败阻塞",
              res_resolved["blocked"]["is_blocked"] is False,
              str(res_resolved["blocked"]))
        # NKB
        check("nkb present", res["nkb"]["present"] is True)
        check("NKB Characters=2", res["nkb"]["component_counts"].get("Characters") == 2,
              str(res["nkb"]["component_counts"]))
        check("open_foreshadows=1", res["nkb"]["open_foreshadows"] == 1, str(res["nkb"]))
        check("total_foreshadows=3", res["nkb"]["total_foreshadows"] == 3, str(res["nkb"]))
        # 落盘
        derived = os.path.join(proot, "project", "status.derived.yaml")
        check("派生文件已落盘", os.path.isfile(derived))
        # 不覆盖手填 status.yaml
        _write(os.path.join(proot, "project", "status.yaml"),
               "current:\n  chapter:\n    current: 99\n")
        res2 = sd.derive(proot, write=True)
        check("手填 status.yaml 未被覆盖",
              open(os.path.join(proot, "project", "status.yaml"), encoding="utf-8").read().count("99") == 1)
        check("drift 检测（手填 99 vs 派生 40）",
              any("不一致" in d for d in res2.get("drift", [])), str(res2.get("drift")))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_govern():
    tmp = tempfile.mkdtemp()
    try:
        proot = _mk_project(tmp)
        sd.derive(proot, write=True)
        # 含 failed → caution
        g = sd.govern(proot)
        check("Govern caution（失败任务）", g["gate"]["decision"] == "caution",
              g["gate"]["decision"])
        check("Govern health<100", g["composite"]["health"] < 100, str(g["composite"]))

        # 无 failed + 已派生 → proceed
        clean = os.path.join(tmp, "clean")
        os.makedirs(os.path.join(clean, "NKB"))
        _write(os.path.join(clean, "project.yaml"), "project:\n  id: x\n")
        _write(os.path.join(clean, "NKB", "Characters.yaml"),
               "schema_version: 1.2.0\nrecords:\n  - id: A\n")
        sd.derive(clean, write=True)
        gc = sd.govern(clean)
        check("Govern proceed（干净项目）", gc["gate"]["decision"] == "proceed",
              gc["gate"]["decision"])

        # 缺 project.yaml → block
        no_py = os.path.join(tmp, "nopy")
        os.makedirs(no_py)
        gb = sd.govern(no_py)
        check("Govern block（缺 project.yaml）", gb["gate"]["decision"] == "block",
              gb["gate"]["decision"])

        # 缺 NKB → block
        no_nkb = os.path.join(tmp, "nonkb")
        _write(os.path.join(no_nkb, "project.yaml"), "project:\n  id: x\n")
        gn = sd.govern(no_nkb)
        check("Govern block（缺 NKB）", gn["gate"]["decision"] == "block",
              gn["gate"]["decision"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_wiring():
    cli_path = os.path.join(_PLAT2, "cli", "platform.py")
    src = open(cli_path, encoding="utf-8").read()
    check("doctor 含 StatusGov 块", "StatusGov" in src)
    check("doctor 含 status_derive 调用", '"status_derive").govern' in src or "status_derive" in src)
    su_path = os.path.join(_PLAT2, "scripts", "tasks", "status_update.py")
    su = open(su_path, encoding="utf-8").read()
    check("status_update 接入 derive/unblock 动词",
          '"derive"' in su and '"unblock"' in su and "status_derive" in su)


if __name__ == "__main__":
    test_derive()
    test_govern()
    test_wiring()
    print("\n=== e2e_41 结果：%d/%d PASS ===" % (PASS_CNT, PASS_CNT + FAIL_CNT))
    sys.exit(1 if FAIL_CNT else 0)

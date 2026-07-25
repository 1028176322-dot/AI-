#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""e2e_42_phasec_report_builder.py — Phase C 验收（PC-4）：
  - report_builder 五类报告：project-status / chapter-quality / open-foreshadow / task-progress / nkb-health
  - 缺失数据源降级（不崩溃）
  - report_builder.govern：ReportGov 健康块（caution/proceed）
  - doctor 接线（ReportGov 存在于 platform_cli）+ platform report 委托
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

import report_builder as rb
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
    proot = os.path.join(tmp, "proj")
    _write(os.path.join(proot, "project.yaml"),
           "project:\n  id: novel-dsf\n  name: 道法百年\n  type: novel\n")
    _write(os.path.join(proot, "NKB", "Foreshadow.yaml"),
           "schema_version: 1.2.0\nproject_id: novel-dsf\nrecords:\n"
           "  - id: FB-001\n    name: a\n    status: 未回收\n    buried_at: 卷一\n    deadline_chapter: 850\n    recycle_plan: 卷五\n"
           "  - id: FB-002\n    name: b\n    status: 已回收\n")
    _write(os.path.join(proot, "NKB", "Characters.yaml"),
           "schema_version: 1.2.0\nrecords:\n  - id: CHR-001\n    name: 肖凡\n")
    _write(os.path.join(proot, "NKB", "Derived.yaml"),
           "schema_version: 1.2.0\nrecords:\n")
    _write(os.path.join(proot, "tasks", "completed", "TASK-REV-CH10.yaml"),
           "task:\n  id: TASK-REV-CH10\n  status: completed\n"
           "  type: chapter_review\n  title: 第一卷 Ch10 审查\n")
    # 质量 + 读者评分数据（schema 对齐真实产物：target 为顶层键）
    _write(os.path.join(proot, "analysis", "quality", "QUAL-chapter-10-01.yaml"),
           "target:\n  target_id: 10\ncomposite:\n  value: 88.5\n"
           "gate:\n  decision: proceed\n")
    _write(os.path.join(proot, "analysis", "reader", "READ-chapter-10-01.yaml"),
           "target:\n  target_id: 10\nreader_index: 65.0\npi: 72.0\n"
           "fatal: false\ngate:\n  decision: proceed\n")
    return proot


def test_reports():
    tmp = tempfile.mkdtemp()
    try:
        proot = _mk_project(tmp)
        # project-status
        md = rb.report_project_status(proot)
        check("project-status 含派生状态", "项目派生状态报告" in md and "任务系统" in md, md[:50])
        # chapter-quality
        mq = rb.report_chapter_quality(proot)
        check("chapter-quality 含章10", "10" in mq and "88.5" in mq, mq[:80])
        check("chapter-quality 含 RI", "65.0" in mq, mq[:80])
        # open-foreshadow
        mf = rb.report_open_foreshadow(proot)
        check("open-foreshadow 含 FB-001", "FB-001" in mf, mf[:80])
        check("open-foreshadow 不含已回收 FB-002", "FB-002" not in mf, mf[:80])
        check("open-foreshadow 计数=1", "未回收" in mf and "1" in mf and "总计" in mf and "2" in mf, mf[:80])
        # task-progress
        mt = rb.report_task_progress(proot)
        check("task-progress 含 completed", "completed" in mt and "1" in mt, mt[:80])
        # nkb-health
        mn = rb.report_nkb_health(proot)
        check("nkb-health 标记空组件 Derived", "Derived" in mn and "待填充" in mn, mn[:80])
        # all
        mall = rb.render_all(proot)
        check("all 含全部五类标题",
              all(h in mall for h in ["项目派生状态报告", "章节质量", "未回收伏笔", "任务系统推进", "NKB 组件健康"]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_degrade():
    tmp = tempfile.mkdtemp()
    try:
        # 无 analysis/quality + 无 reader → chapter-quality 降级不崩溃
        proot = os.path.join(tmp, "nomin")
        os.makedirs(os.path.join(proot, "NKB"))
        _write(os.path.join(proot, "project.yaml"), "project:\n  id: x\n")
        _write(os.path.join(proot, "NKB", "Characters.yaml"), "records:\n  - id: A\n")
        mq = rb.report_chapter_quality(proot)
        check("chapter-quality 缺失数据降级提示", "暂无评分数据" in mq, mq[:80])
        # 无 NKB → open-foreshadow / nkb-health 降级
        nonkb = os.path.join(tmp, "nonkb")
        _write(os.path.join(nonkb, "project.yaml"), "project:\n  id: x\n")
        check("open-foreshadow 无 NKB 降级", "缺失" in rb.report_open_foreshadow(nonkb))
        check("nkb-health 无 NKB 降级", "缺失" in rb.report_nkb_health(nonkb))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_govern():
    tmp = tempfile.mkdtemp()
    try:
        proot = os.path.join(tmp, "ok")
        os.makedirs(os.path.join(proot, "NKB"))
        _write(os.path.join(proot, "project.yaml"), "project:\n  id: x\n")
        _write(os.path.join(proot, "NKB", "Characters.yaml"), "records:\n  - id: A\n")
        g = rb.govern(proot)
        check("Govern proceed（NKB 存在）", g["gate"]["decision"] == "proceed", g["gate"]["decision"])
        nonkb = os.path.join(tmp, "nonkb")
        _write(os.path.join(nonkb, "project.yaml"), "project:\n  id: x\n")
        gn = rb.govern(nonkb)
        check("Govern caution（NKB 缺失）", gn["gate"]["decision"] == "caution", gn["gate"]["decision"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_wiring():
    cli_path = os.path.join(TOOLS, "platform_cli.py")
    src = open(cli_path, encoding="utf-8").read()
    check("doctor 含 ReportGov 块", "ReportGov" in src)
    check("report 委托 report_builder", '"report": "report_builder"' in src)
    check("report 子命令注册", 'sub.add_parser("report"' in src or "add_parser(\"report\"" in src)


if __name__ == "__main__":
    test_reports()
    test_degrade()
    test_govern()
    test_wiring()
    print("\n=== e2e_42 结果：%d/%d PASS ===" % (PASS_CNT, PASS_CNT + FAIL_CNT))
    sys.exit(1 if FAIL_CNT else 0)

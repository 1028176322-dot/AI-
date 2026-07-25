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
"""e2e_43_phasec_terminology.py — Phase C 验收（PC-5）：
  - terminology_check：load_terms 全量读取 NKB Terminology.yaml 的 forbidden 字段
  - scan_file / scan_project：命中禁用同义（事实，不判误用）
  - validators._collect_terminology 字段映射修正（forbidden）
  - govern：TermGov 健康块（block=缺失/无记录，proceed=正常）
  - doctor 接线（TermGov 存在于 platform_cli）+ platform terminology 委托 + 子命令注册
  - 真实项目接入验证（全量扫描 txt/ 树）
脚本只做确定性校验，不替 AI 下语义结论。
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

import terminology_check as tc
import validators as va

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
    _write(os.path.join(proot, "project.yaml"), "project:\n  id: novel-dsf\n  name: 道法百年\n  type: novel\n")
    _write(os.path.join(proot, "NKB", "Terminology.yaml"),
           "schema_version: 1.2.0\nrecords:\n"
           "  - id: TER-001\n    name: 大晟\n    standard: 大晟\n    forbidden: [大晟王朝, 本朝]\n    note: x\n"
           "  - id: TER-002\n    name: 清虚观\n    standard: 清虚观\n    forbidden: [清虚门, 清虚山]\n    note: y\n"
           "  - id: TER-003\n    name: 炼体十八式\n    standard: 炼体十八式\n    forbidden: []\n")
    # 章节正文：含一处禁用同义「大晟王朝」，一处正确「大晟」
    _write(os.path.join(proot, "txt", "第一卷_道生", "第001章_遗弃.txt"),
           "大晟王朝建立已久。\n肖凡入清虚门学艺。\n他修习的是大晟正统功法。\n")
    return proot


def test_load_terms():
    tmp = tempfile.mkdtemp()
    try:
        proot = _mk_project(tmp)
        terms = tc.load_terms(proot)
        # TER-001(2) + TER-002(2) + TER-003(0) = 4
        check("load_terms 全量 forbidden=4", len(terms) == 4, str(len(terms)))
        toks = {t["token"] for t in terms}
        check("load_terms 含 大晟王朝/本朝/清虚门/清虚山",
              {"大晟王朝", "本朝", "清虚门", "清虚山"} <= toks, str(toks))
        check("load_terms 空 forbidden 不入表", "炼体十八式" not in toks, str(toks))
        # canonical 正确
        c = {t["token"]: t["canonical"] for t in terms}
        check("load_terms canonical 映射", c.get("大晟王朝") == "大晟" and c.get("清虚门") == "清虚观", str(c))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_scan():
    tmp = tempfile.mkdtemp()
    try:
        proot = _mk_project(tmp)
        terms = tc.load_terms(proot)
        ch = os.path.join(proot, "txt", "第一卷_道生", "第001章_遗弃.txt")
        hits = tc.scan_file(ch, terms)
        # 第1行「大晟王朝」命中；「清虚门」命中；「大晟」(标准词)不命中；空 forbidden 不计
        check("scan_file 命中 2 处", len(hits) == 2, str(hits))
        found = {h["found"] for h in hits}
        check("scan_file 命中词正确", found == {"大晟王朝", "清虚门"}, str(found))
        lines = {h["line"] for h in hits}
        check("scan_file 行号正确", lines == {1, 2}, str(lines))
        # 全稿件扫描
        proj = tc.scan_project(proot, terms)
        check("scan_project 覆盖 1 文件", len(proj) == 1, str(proj.keys()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_validators_mapping():
    tmp = tempfile.mkdtemp()
    try:
        proot = _mk_project(tmp)
        terms = va._collect_terminology(proot)
        check("validators._collect_terminology 读 forbidden=4", len(terms) == 4, str(len(terms)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_govern():
    tmp = tempfile.mkdtemp()
    try:
        proot = _mk_project(tmp)
        g = tc.govern(proot)
        check("Govern proceed（Terminology 存在）", g["gate"]["decision"] == "proceed", g["gate"]["decision"])
        check("Govern response 含 records/forbidden",
              g["response"]["records"] == 3 and g["response"]["forbidden"] == 4, str(g["response"]))
        # 缺失 Terminology
        nonkb = os.path.join(tmp, "nonkb")
        _write(os.path.join(nonkb, "project.yaml"), "project:\n  id: x\n")
        gn = tc.govern(nonkb)
        check("Govern block（Terminology 缺失）", gn["gate"]["decision"] == "block", gn["gate"]["decision"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_wiring():
    cli_path = os.path.join(_PLAT2, "cli", "platform.py")
    src = open(cli_path, encoding="utf-8").read()
    check("doctor 含 TermGov 块", "TermGov" in src)
    check("terminology 委托 terminology_check", '"terminology": "terminology_check"' in src)
    check("terminology 子命令注册", 'sub.add_parser("terminology"' in src)


def test_real_project():
    proot = os.path.join(os.path.dirname(PLAT), "..", "projects", "道法百年")
    proot = os.path.abspath(proot)
    if os.path.isdir(proot):
        terms = tc.load_terms(proot)
        check("真实项目 load_terms > 0", len(terms) > 0, str(len(terms)))
        proj = tc.scan_project(proot, terms)
        check("真实项目 scan_project 运行不崩溃", isinstance(proj, dict), str(type(proj)))
    else:
        check("真实项目存在", False, proot)


if __name__ == "__main__":
    test_load_terms()
    test_scan()
    test_validators_mapping()
    test_govern()
    test_wiring()
    test_real_project()
    print("\n=== e2e_43 结果：%d/%d PASS ===" % (PASS_CNT, PASS_CNT + FAIL_CNT))
    sys.exit(1 if FAIL_CNT else 0)

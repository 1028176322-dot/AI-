#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""terminology_check.py — Phase C PC-5：术语全量词表检查（接入 NKB Terminology）

设计原则（与 Phase A/B/C 一致）：
  - 脚本只做确定性工作：把 NKB/Terminology.yaml 的「标准词 + 禁用同义(forbidden)」全量取出，
    对目标文本/整部稿件逐行扫描，列出命中（禁用同义 → 应改为标准词）。
  - 不替 AI 下语义结论：命中只给事实（行号/命中词/标准词），是否真为误用由 AI 判断。
  - 全量覆盖：scan --project-root 扫描项目内全部 .txt 章节（txt/ 树），不限于单文件。
  - TermGov 健康块（doctor 接入）：block=NKB/Terminology.yaml 缺失或无记录；proceed=正常。

契约（统一 Gov 标准）：{gate:{decision,reasons}, composite:{health}, response:{}}
"""
import os
import sys
import json
import argparse

try:
    import _gov
except Exception:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _gov


def _load_yaml_safe(path):
    try:
        return _gov.load_yaml(path)
    except Exception:
        return None


def load_terms(proot):
    """从 NKB/Terminology.yaml 取出全量禁用同义词表。
    返回 [{token, canonical, note}]；token 为禁用同义字符串，canonical 为标准词(name)。"""
    path = os.path.join(proot, "NKB", "Terminology.yaml")
    if not os.path.isfile(path):
        return []
    d = _load_yaml_safe(path)
    if not isinstance(d, dict):
        return []
    out = []
    for r in (d.get("records") or []):
        if not isinstance(r, dict):
            continue
        forb = r.get("forbidden")
        if forb is None:
            # 兼容历史字段名
            forb = r.get("deprecated") or r.get("aliases")
        if isinstance(forb, str):
            forb = [forb]
        if not isinstance(forb, list):
            forb = []
        canonical = r.get("name") or r.get("standard") or ""
        note = r.get("note") or ""
        for tok in forb:
            if tok:
                out.append({"token": str(tok), "canonical": str(canonical), "note": str(note)})
    return out


def scan_text(text, terms):
    """逐行扫描文本，返回命中 [{line, found, canonical}]。"""
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        for t in terms:
            if t["token"] and t["token"] in line:
                hits.append({"line": i, "found": t["token"], "canonical": t["canonical"]})
    return hits


def scan_file(path, terms):
    if not os.path.isfile(path):
        return None
    text = None
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=enc) as fh:
                text = fh.read()
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8", "ignore")
    return scan_text(text, terms)


def _iter_txt(proot):
    """遍历项目内全部 .txt 章节（排除分析/版本/治理目录），返回绝对路径列表。"""
    skip = ("analysis", "versions", ".git", "__pycache__")
    out = []
    for dirpath, dirnames, fns in os.walk(proot):
        if any(seg in dirpath.split(os.sep) for seg in skip):
            continue
        for fn in fns:
            if fn.endswith(".txt"):
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def scan_project(proot, terms):
    """全量扫描：返回 {相对路径: [hits]}。"""
    results = {}
    for p in _iter_txt(proot):
        h = scan_file(p, terms)
        if h:
            results[os.path.relpath(p, proot)] = h
    return results


def govern(proot):
    """TermGov 健康块。"""
    reasons = []
    path = os.path.join(proot, "NKB", "Terminology.yaml")
    if not os.path.isfile(path):
        return {"gate": {"decision": "block", "reasons": ["NKB/Terminology.yaml 缺失"]},
                "composite": {"health": 0}, "response": {}}
    d = _load_yaml_safe(path)
    recs = (d or {}).get("records") or []
    terms = load_terms(proot)
    if not recs:
        return {"gate": {"decision": "block", "reasons": ["Terminology 无记录"]},
                "composite": {"health": 0}, "response": {}}
    reasons.append("Terminology 表存在：%d 记录 / %d 禁用同义" % (len(recs), len(terms)))
    return {"gate": {"decision": "proceed", "reasons": reasons},
            "composite": {"health": 100},
            "response": {"records": len(recs), "forbidden": len(terms)}}


def _render_markdown(proot, terms, single=None, project=None):
    out = []
    out.append("# 术语一致性检查报告（NKB Terminology 全量词表）")
    out.append("")
    out.append("- **项目根**：%s" % proot)
    out.append("- **禁用同义词条数**：%d" % len(terms))
    if single is not None:
        out.append("- **检查模式**：单文件")
        out.append("")
        if not single:
            out.append("（未发现禁用同义命中）")
        else:
            out.append("| 行 | 命中禁用同义 | 应改为标准词 |")
            out.append("| --- | --- | --- |")
            for h in single:
                out.append("| %d | %s | %s |" % (h["line"], h["found"], h["canonical"]))
    if project is not None:
        out.append("- **检查模式**：全稿件（%d 个文件命中）" % len(project))
        out.append("")
        if not project:
            out.append("（全部章节未发现禁用同义命中）")
        else:
            for rel, hits in project.items():
                out.append("## %s（%d 处）" % (rel, len(hits)))
                out.append("| 行 | 命中禁用同义 | 应改为标准词 |")
                out.append("| --- | --- | --- |")
                for h in hits:
                    out.append("| %d | %s | %s |" % (h["line"], h["found"], h["canonical"]))
                out.append("")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(prog="terminology_check", description="术语全量词表检查（Phase C PC-5）")
    ap.add_argument("verb", choices=["scan", "govern"], help="scan=扫描单文件/全稿件；govern=TermGov 健康块")
    ap.add_argument("--project-root", default=None)
    ap.add_argument("--file", default=None, help="单文件扫描（与 --project-root 互斥）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    if args.verb == "scan":
        if args.file and args.project_root:
            print("✗ scan 不能同时指定 --file 与 --project-root", file=sys.stderr)
            sys.exit(2)
        if args.project_root:
            terms = load_terms(args.project_root)
            proj = scan_project(args.project_root, terms)
            if args.json:
                print(json.dumps(proj, ensure_ascii=False, indent=2))
            else:
                print(_render_markdown(args.project_root, terms, project=proj))
        elif args.file:
            proot_guess = os.path.dirname(os.path.dirname(os.path.abspath(args.file)))
            terms = load_terms(proot_guess)
            hits = scan_file(args.file, terms)
            if args.json:
                print(json.dumps(hits or [], ensure_ascii=False, indent=2))
            else:
                print(_render_markdown(proot_guess, terms, single=hits or []))
        else:
            print("✗ scan 需 --file 或 --project-root", file=sys.stderr)
            sys.exit(2)
    elif args.verb == "govern":
        if not args.project_root:
            print("✗ govern 需 --project-root", file=sys.stderr)
            sys.exit(2)
        g = govern(args.project_root)
        print(json.dumps(g, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

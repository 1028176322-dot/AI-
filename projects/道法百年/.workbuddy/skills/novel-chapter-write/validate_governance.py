#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_governance.py — 《道士也玩火力覆盖》治理一致性交叉校验
隶属 novel-chapter-write 四阶段流程（建议在 阶段一 前 / 提交前跑，防治理漂移）。

设计目的：把"治理文档之间是否自洽"从人工发现升级为机械比对，覆盖 P0 暴露的
「进度三处声明各说各话」「机械校验引用版本漂移」两类问题。

校验项（FAIL=不一致须人工修；WARN=提示性）：
  G1 进度·磁盘 vs AUTHORITY_INDEX「进度 current」行
  G2 进度·磁盘 vs PROJECT_RULES.md §2「第 1-X 章」
  G3 进度·磁盘 vs 写作规则.md「已完成章节」进度行
  G4 五张治理索引(伏笔/角色/设定/认知/人设)均存在且非空
  G5 机械校验引用一致性：SKILL.md 与 AI写作自动化流程.md 均含 C1–C22 口径
  G6 单点规范源：AI写作自动化流程.md 被列为唯一规范源（写作规则.md 引它）

用法：python validate_governance.py [仓库根]
返回：0=全通过，1=有 FAIL，2=参数/IO 错误
"""
import os, re, sys


def _repo_root(explicit=None):
    """脚本位于 <repo>/.workbuddy/skills/novel-chapter-write/validate_governance.py，
    上溯 3 级定位仓库根；支持显式传入。"""
    if explicit:
        return os.path.abspath(explicit)
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _count_disk_chapters(vol_dir):
    if not os.path.isdir(vol_dir):
        return -1, "目录不存在: %s" % vol_dir
    n = 0
    for fn in os.listdir(vol_dir):
        if re.match(r'第\d+章_.*\.md$', fn):
            n += 1
    return n, ""


def _extract(pattern, text, default=-1):
    m = re.search(pattern, text)
    if not m:
        return default
    return int(m.group(1))


def main(repo):
    gov = os.path.join(repo, "docs", "governance")
    vol = os.path.join(repo, "第一卷_道生")
    fails, warns, oks = [], [], []

    # ---- G1/G2/G3 进度三方一致性 ----
    disk_n, err = _count_disk_chapters(vol)
    if disk_n < 0:
        fails.append(("G0 磁盘扫描", err))
    else:
        oks.append("G0 磁盘章节扫描：%d 章" % disk_n)

    auth_path = os.path.join(gov, "AUTHORITY_INDEX.md")
    proj_path = os.path.join(repo, "PROJECT_RULES.md")
    rule_path = os.path.join(repo, "写作规则.md")

    if os.path.isfile(auth_path):
        auth = _read(auth_path)
        a_n = _extract(r'进度 current[^\n]*?第\s*(\d+)\s*章', auth)
        if a_n < 0:
            warns.append(("G1 进度·AUTHORITY_INDEX", "未匹配到「进度 current」行的章数，请人工核对"))
        elif disk_n >= 0 and a_n != disk_n:
            fails.append(("G1 进度·AUTHORITY_INDEX", "声明第 %d 章 ≠ 磁盘 %d 章" % (a_n, disk_n)))
        else:
            oks.append("G1 进度·AUTHORITY_INDEX：第 %d 章（与磁盘一致）" % a_n)
    else:
        fails.append(("G1 进度·AUTHORITY_INDEX", "文件缺失"))

    if os.path.isfile(proj_path):
        proj = _read(proj_path)
        p_n = _extract(r'第\s*1-\s*(\d+)\s*章', proj)
        if p_n < 0:
            warns.append(("G2 进度·PROJECT_RULES", "未匹配到 §2 的「第 1-X 章」章数，请人工核对"))
        elif disk_n >= 0 and p_n != disk_n:
            fails.append(("G2 进度·PROJECT_RULES", "声明第 1-%d 章 ≠ 磁盘 %d 章" % (p_n, disk_n)))
        else:
            oks.append("G2 进度·PROJECT_RULES：第 1-%d 章（与磁盘一致）" % p_n)
    else:
        fails.append(("G2 进度·PROJECT_RULES", "文件缺失"))

    if os.path.isfile(rule_path):
        rule = _read(rule_path)
        r_n = _extract(r'共\s*(\d+)\s*章', rule)
        if r_n < 0:
            r_n = _extract(r'第\s*(\d+)\s*章', rule)
        if r_n < 0:
            warns.append(("G3 进度·写作规则", "未匹配到进度行章数，请人工核对"))
        elif disk_n >= 0 and r_n != disk_n:
            fails.append(("G3 进度·写作规则", "声明第 %d 章 ≠ 磁盘 %d 章" % (r_n, disk_n)))
        else:
            oks.append("G3 进度·写作规则：第 %d 章（与磁盘一致）" % r_n)
    else:
        fails.append(("G3 进度·写作规则", "文件缺失"))

    # ---- G4 五张治理索引存在非空 ----
    idx_files = ["IDX_FORESHADOW.md", "IDX_CHARACTER.md", "IDX_SETTING.md",
                 "IDX_COGNITION.md", "IDX_PERSONA.md"]
    for fn in idx_files:
        p = os.path.join(gov, fn)
        if not os.path.isfile(p):
            fails.append(("G4 治理索引缺失", fn))
        elif os.path.getsize(p) < 100:
            fails.append(("G4 治理索引空", "%s 仅 %d 字节" % (fn, os.path.getsize(p))))
        else:
            oks.append("G4 治理索引：%s 存在(%d字节)" % (fn, os.path.getsize(p)))

    # ---- G5 机械校验引用一致性 C1–C22 ----
    skill_path = os.path.join(repo, ".workbuddy", "skills", "novel-chapter-write", "SKILL.md")
    flow_path = os.path.join(repo, "AI写作自动化流程.md")
    for label, p in (("SKILL.md", skill_path), ("AI写作自动化流程.md", flow_path)):
        if not os.path.isfile(p):
            warns.append(("G5 机械校验引用", "%s 缺失" % label))
            continue
        txt = _read(p)
        has_c22 = ("C1–C22" in txt) or ("C1-C22" in txt)
        if has_c22:
            oks.append("G5 机械校验引用：%s 含 C1–C22 口径" % label)
        else:
            fails.append(("G5 机械校验引用", "%s 未含 C1–C22 口径（疑似残留旧版 C1–C17 以下）" % label))

    # ---- G6 单点规范源声明 ----
    if os.path.isfile(rule_path):
        if "以《AI写作自动化流程.md》为准" in _read(rule_path):
            oks.append("G6 单点规范源：写作规则.md 已声明以 AI写作自动化流程.md 为准")
        else:
            warns.append(("G6 单点规范源", "写作规则.md 未声明以 AI写作自动化流程.md 为准"))

    # ---- 报告 ----
    print("=" * 64)
    print("治理一致性交叉校验：%s" % repo)
    print("=" * 64)
    for o in oks:
        print("  [OK]   %s" % o)
    for name, msg in warns:
        print("  [WARN] %s：%s" % (name, msg))
    for name, msg in fails:
        print("  [FAIL] %s：%s" % (name, msg))
    print("=" * 64)
    if fails:
        print("结论：[FAIL] 发现 %d 处不一致，须人工修正后重检" % len(fails))
        return 1
    if warns:
        print("结论：[OK] 硬校验通过；%d 处 WARN（提示性，不阻断）" % len(warns))
    else:
        print("结论：[OK] 治理一致性全通过")
    return 0


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(main(_repo_root(root)))

# -*- coding: utf-8 -*-
"""确定性段落拆分：将过长段落(>130字)在句/分句边界拆分为 40-130 字短段落，
保留全部正文内容、标题、分隔线、章末钩子、字数。目标对齐 REF-PARAGRAPH-CONTRAST。
仅移动段落断点，绝不增删文字。"""
import os, re, glob, statistics, sys

MAX_SOFT = 100  # 段落软上限
SENT = re.compile(r"(?<=[。！？；])")
CLAUSE = re.compile(r"(?<=[，、：])")

KEEP = ("#", "（本章完）")


def is_prose(line):
    s = line.strip()
    if not s:
        return False
    if s.startswith("#"):
        return False
    if s in ("---", "（本章完）"):
        return False
    return True


def split_long(para):
    """把一段可能很长的文字拆成 <=MAX_SOFT 的若干段落。"""
    sentences = [s for s in SENT.split(para) if s.strip()]
    if not sentences:
        return [para] if para.strip() else []
    paras = []
    cur = ""
    for s in sentences:
        if not cur:
            cur = s
        elif len(cur) + len(s) <= MAX_SOFT:
            cur += s
        else:
            paras.append(cur)
            cur = s
    if cur:
        paras.append(cur)
    # 处理仍超长的段落（长句或少量长句）
    final = []
    for p in paras:
        if len(p) <= MAX_SOFT:
            final.append(p)
            continue
        subs = [x for x in CLAUSE.split(p) if x.strip()]
        cur = ""
        for ss in subs:
            if not cur:
                cur = ss
            elif len(cur) + len(ss) <= MAX_SOFT:
                cur += ss
            else:
                final.append(cur)
                cur = ss
        if cur:
            final.append(cur)
    return [p for p in final if p.strip()]


def transform(text):
    out_lines = []
    for line in text.splitlines():
        if is_prose(line):
            for p in split_long(line.strip()):
                out_lines.append(p)
        else:
            out_lines.append(line)
    return "\n".join(out_lines)


def main():
    files = sorted(glob.glob("chapters/drafts/第一卷_道生/第*.md") +
                   glob.glob("chapters/drafts/第二卷_京华/第*.md"))
    changed = 0
    before = []
    after = []
    for f in files:
        t = open(f, encoding="utf-8").read()
        med_before = statistics.median([len(p) for p in (l.strip() for l in t.splitlines()) if p and not p.startswith("#") and p != "---" and p != "（本章完）"])
        new = transform(t)
        med_after = statistics.median([len(p) for p in (l.strip() for l in new.splitlines()) if p and not p.startswith("#") and p != "---" and p != "（本章完）"])
        if new != t:
            open(f, "w", encoding="utf-8").write(new)
            changed += 1
        before.append(med_before)
        after.append(med_after)
    print("处理文件:", len(files), " 有改动:", changed)
    print("段落中位 改前均值 %.0f → 改后均值 %.0f" % (statistics.mean(before), statistics.mean(after)))
    print("段落中位 改前最大 %.0f → 改后最大 %.0f" % (max(before), max(after)))


if __name__ == "__main__":
    main()

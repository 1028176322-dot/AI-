# -*- coding: utf-8 -*-
"""规范化 3 本新增参考书（GB18030 → UTF-8，行尾归一，章节标记去缩进到行首）。

平台 _chapters 正则： (?m)^(?:#{1,6}\s*)?第[0-9零一二三四五六七八九十百千万两]+章[^\n]*$
—— 第 前无 \s*，故章节标记必须位于行首(col 0) 才会被识别为分章。

规则：
  - 纯标记 ` 第X章`(无后缀)        → 去缩进输出 `第X章`(col 0) = 真实分章
  - 括号后缀 `第X章(本章免费)`      → 保留原缩进(不输出 col 0)，避免误切（唐寅特有重复标记）
  - 标题后缀 `第X章 奇怪的孤儿院`   → 去缩进输出 `第X章 标题`(col 0) = 真实分章
  - 楔子                          → 第零章(col 0)
  - 其余行                         → 原样保留（含正文缩进）

先归档原始 GB18030 到 _archive/，再覆盖 inbox 为规范化 UTF-8 副本。
"""
import os
import re
import shutil

ROOT = r"E:/AI-Workspace/projects/道法百年"
INBOX = os.path.join(ROOT, "sources/references/inbox")
ARCHIVE = os.path.join(ROOT, "sources/references/_archive")

NUM = r"[0-9零一二三四五六七八九十百千万两]"
RE_MARK = re.compile(r"^第(" + NUM + r"+)章(.*)$")
RE_WEDGE = re.compile(r"^楔子\s*$")


def normalize_text(txt):
    txt = txt.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for line in txt.split("\n"):
        s = line.strip()
        m = RE_MARK.match(s)
        if m:
            num = m.group(1)
            rest = m.group(2).strip()
            if rest == "":                      # 纯标记
                out.append("第%s章" % num)
            elif (rest.startswith("(") and rest.endswith(")")) or \
                 (rest.startswith("（") and rest.endswith("）")):  # 括号后缀=重复标记
                out.append(line)                # 保留原缩进 → 不作为分章
            else:                               # 真实标题标记
                out.append("第%s章%s" % (num, rest))
        elif RE_WEDGE.match(s):
            out.append("第零章")
        else:
            out.append(line)
    return "\n".join(out)


def main():
    files = ["唐寅在异界.txt",
             "我开的真是孤儿院，不是杀手堂.txt",
             "镇北王.txt"]
    os.makedirs(ARCHIVE, exist_ok=True)
    for fn in files:
        src = os.path.join(INBOX, fn)
        if not os.path.isfile(src):
            print("SKIP (not found):", fn)
            continue
        raw = open(src, "rb").read()
        # 编码探测
        enc = None
        for cand in ("utf-8", "gb18030", "gbk"):
            try:
                raw.decode(cand)
                enc = cand
                break
            except Exception:
                pass
        if enc is None:
            enc = "gb18030"
        txt = raw.decode(enc, errors="replace")

        # 归档原始（仅当 _archive 尚无该名）
        arch_path = os.path.join(ARCHIVE, fn)
        if not os.path.isfile(arch_path):
            shutil.copyfile(src, arch_path)
            print("archived raw ->", os.path.relpath(arch_path, ROOT))

        norm = normalize_text(txt)
        with open(src, "w", encoding="utf-8", newline="") as f:
            f.write(norm)
        # 统计规范化后章数
        chap = len(re.findall(r"(?m)^第" + NUM + r"+章", norm))
        wedge0 = len(re.findall(r"(?m)^第零章", norm))
        print("normalized %s (enc=%s): chapters=%d (+第零章=%d)" %
              (fn, enc, chap, wedge0))


if __name__ == "__main__":
    main()

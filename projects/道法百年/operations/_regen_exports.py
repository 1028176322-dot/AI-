# -*- coding: utf-8 -*-
"""清债#223 + 统一发布层：以 canonical 工作稿 chapters/drafts/ 为权威，
重新生成两份派生副本：
- txt/<卷>/第N章_xxx.txt  : 干净散文（去 markdown 标题/分隔线/（本章完）），内容= drafts 散文
- operations/published/<卷>/第N章_xxx.md : 扁平镜像，内容=drafts .md 原文（去掉 第X章_xxx.md/r2.md 嵌套怪结构）
"""
import os, re, shutil

ROOT = "E:/AI-Workspace/projects/道法百年"
DRAFTS = os.path.join(ROOT, "chapters/drafts")
TXT = os.path.join(ROOT, "txt")
PUB = os.path.join(ROOT, "operations/published")
CHAPTER_RE = re.compile(r"^第[0-9]+章.*\.md$")

def clean_prose(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    prose = [l for l in lines if not l.startswith("#") and l != "---"]
    body = "\n".join(prose)
    body = re.sub(r"[\n\r]*（本章完）\s*$", "", body).strip()
    return body if body else text

total = 0
for vol in ["第一卷_道生", "第二卷_京华"]:
    vd = os.path.join(DRAFTS, vol)
    # --- txt ---
    tv = os.path.join(TXT, vol)
    os.makedirs(tv, exist_ok=True)
    # --- published: 清掉旧嵌套结构，重建扁平 ---
    pv = os.path.join(PUB, vol)
    if os.path.isdir(pv):
        shutil.rmtree(pv)
    os.makedirs(pv, exist_ok=True)
    for name in sorted(os.listdir(vd)):
        if not CHAPTER_RE.match(name):
            continue
        src = os.path.join(vd, name)
        text = open(src, encoding="utf-8").read()
        base = name[:-3]  # 去 .md
        # txt：干净散文
        with open(os.path.join(tv, base + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(clean_prose(text) + "\n")
        # published：扁平镜像 drafts 原文
        with open(os.path.join(pv, base + ".md"), "w", encoding="utf-8") as fh:
            fh.write(text)
        total += 1
print("已重生派生副本：", total, "章 (txt + published 均同步自 drafts)")

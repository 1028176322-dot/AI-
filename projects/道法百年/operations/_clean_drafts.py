# -*- coding: utf-8 -*-
"""清理 chapters/drafts/<卷> 下的非章节文件(F7: 正文/评审产物混放)。
仅保留 第N章*.md 真实章节；其余(评分卡/批注/读者视角/大纲/设定)移出。
- 设定_*.md -> sources/design/ (世界设定)
- 其余评审产物 -> artifacts/reviews/<卷>/
"""
import os, re, shutil

ROOT = "E:/AI-Workspace/projects/道法百年"
DRAFTS = os.path.join(ROOT, "chapters/drafts")
DESIGN = os.path.join(ROOT, "sources/design")
REVIEWS = os.path.join(ROOT, "artifacts/reviews")

CHAPTER_RE = re.compile(r"^第[0-9]+章.*\.md$")

moved = 0
for vol in ["第一卷_道生", "第二卷_京华"]:
    vdir = os.path.join(DRAFTS, vol)
    if not os.path.isdir(vdir):
        print("skip missing vol:", vol)
        continue
    rev_dst = os.path.join(REVIEWS, vol)
    os.makedirs(rev_dst, exist_ok=True)
    for name in os.listdir(vdir):
        if CHAPTER_RE.match(name):
            continue  # 真实章节，保留
        src = os.path.join(vdir, name)
        # 设定类 -> sources/design
        if name.startswith("设定_"):
            dst = os.path.join(DESIGN, name)
        else:
            dst = os.path.join(rev_dst, name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        moved += 1
        print("moved:", vol, "->", os.path.relpath(dst, ROOT))

print("\n总计移出非章节文件:", moved)
# 校验：每个卷目录下应只剩 第N章*.md
for vol in ["第一卷_道生", "第二卷_京华"]:
    vdir = os.path.join(DRAFTS, vol)
    left = [n for n in os.listdir(vdir) if not CHAPTER_RE.match(n)]
    chapters = [n for n in os.listdir(vdir) if CHAPTER_RE.match(n)]
    print(f"{vol}: 剩余非章节={len(left)} 章节={len(chapters)}")
    if left:
        print("  残留:", left)

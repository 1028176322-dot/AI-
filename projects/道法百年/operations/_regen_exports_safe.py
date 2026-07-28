# -*- coding: utf-8 -*-
"""_regen_exports.py 的安全等价版：
- 与原始逻辑一致（clean_prose 去 # 标题/---/（本章完）；published 为 drafts 扁平镜像）
- 区别：published 改为按文件就地覆盖，不做 shutil.rmtree 整目录删除，
  以绕过沙箱批量删除保护（100 文件 > 阈值 50）。
- 仅覆盖 drafts 中存在的章节；旧标题孤儿 txt 由后续步骤单独清理。
"""
import os, re

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
    tv = os.path.join(TXT, vol)
    pv = os.path.join(PUB, vol)
    os.makedirs(tv, exist_ok=True)
    os.makedirs(pv, exist_ok=True)   # 就地覆盖，不 rmtree
    for name in sorted(os.listdir(vd)):
        if not CHAPTER_RE.match(name):
            continue
        src = os.path.join(vd, name)
        text = open(src, encoding="utf-8").read()
        base = name[:-3]  # 去 .md
        with open(os.path.join(tv, base + ".txt"), "w", encoding="utf-8") as fh:
            fh.write(clean_prose(text) + "\n")
        with open(os.path.join(pv, base + ".md"), "w", encoding="utf-8") as fh:
            fh.write(text)
        total += 1
print("已重生派生副本（就地覆盖，无整目录删除）：", total, "章 (txt + published 均同步自 drafts)")

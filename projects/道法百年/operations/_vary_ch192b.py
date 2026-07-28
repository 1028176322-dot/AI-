# -*- coding: utf-8 -*-
import re, io

PATH = r"E:/AI-Workspace/projects/道法百年/chapters/drafts/第二卷_京华/第192章_以技破武六.md"

def measure(t):
    body = re.sub(r"[\n\r]*（本章完）\s*$", "", t).strip()
    grams = re.findall(r"[一-鿿]{4}", body)
    tot = len(grams)
    c = {}
    for g in grams:
        c[g] = c.get(g, 0) + 1
    rep = sum(v - 1 for v in c.values() if v > 1)
    red = rep / tot if tot else 0
    cjk = len(re.findall(r"[一-鿿]", body))
    return red, tot, rep, cjk, c

with io.open(PATH, encoding="utf-8-sig") as f:
    raw = f.read()

red0, tot0, rep0, cjk0, c0 = measure(raw)
print("START red=%.4f tot=%d rep=%d cjk=%d" % (red0, tot0, rep0, cjk0))

# 二轮：破残余×2结构套语（不碰 以技破武/金身化罡 硬下限）
pairs = [
    ("先遣的武有逻辑，却敌不过身罡的厚，厚了", "先遣的武有逻辑，却敌不过身罡之厚，厚了"),
    ("火器这道关，他记牢", "火器这重关，他记牢"),
    ("是他从回回死斗里走出来的", "是他从回回死斗里闯出来的"),
]

fails = []
for old, new in pairs:
    n = raw.count(old)
    if n != 1:
        fails.append("NON-UNIQUE(n=%d): %s" % (n, old[:40]))
if fails:
    for x in fails:
        print("  " + x)
    print("ABORT: %d anchors not unique." % len(fails))
    raise SystemExit(1)

out = raw
for old, new in pairs:
    out = out.replace(old, new, 1)

red1, tot1, rep1, cjk1, c1 = measure(out)
print("END   red=%.4f tot=%d rep=%d cjk=%d" % (red1, tot1, rep1, cjk1))
top = sorted(((v, k) for k, v in c1.items() if v > 1), reverse=True)[:16]
print("TOP:", ", ".join("%s×%d" % (k, v) for v, k in top))
with io.open(PATH, "w", encoding="utf-8-sig") as f:
    f.write(out)
print("WRITTEN")

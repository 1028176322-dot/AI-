# -*- coding: utf-8 -*-
import re, io

PATH = r"E:/AI-Workspace/projects/道法百年/chapters/drafts/第二卷_京华/第188章_四皇子萧俊安.md"

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

# 仅变换专名后接的虚词/代词(的→之/那/本, 这→此/那, 安→定/稳)，专名三皇子/四皇子本体不动
pairs = [
    # 三皇子的(×5) 变 3 处，保留 L15/L62 的"破三皇子的楔"
    ("三皇子的局便更破", "三皇子这局便更破"),
    ("三皇子的局便破了相", "三皇子之局便破了相"),
    ("三皇子的局便孤", "三皇子本局便孤"),
    # 四皇子这(×4) L13/L15 同句不同前缀，分别变；保留 L28/L56
    ("敌有谋亦有武的理，他记着：四皇子这头，原也有被卷的逻辑",
     "敌有谋亦有武的理，他记着：四皇子此头，原也有被卷的逻辑"),
    ("肖凡暗里另有一层思量：四皇子这头，原也有被卷的逻辑",
     "肖凡暗里另有一层思量：四皇子那头，原也有被卷的逻辑"),
    # 这四皇子(×4) 变 L70/L77；保留 L62/L72
    ("这四皇子的安，看着像宫闱闲笔", "此四皇子的安，看着像宫闱闲笔"),
    ("这四皇子的安，像是宫闱里的一笔", "那四皇子的安，像是宫闱里的一笔"),
    # 四皇子安(×3) 变 L12/L59；保留 L75
    ("四皇子安，则大皇子那头的压力便分了", "四皇子定，则大皇子那头的压力便分了"),
    ("四皇子安，皇子线乃立", "四皇子稳，皇子线乃立"),
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
top = sorted(((v, k) for k, v in c1.items() if v > 1), reverse=True)[:14]
print("TOP:", ", ".join("%s×%d" % (k, v) for v, k in top))
with io.open(PATH, "w", encoding="utf-8-sig") as f:
    f.write(out)
print("WRITTEN")

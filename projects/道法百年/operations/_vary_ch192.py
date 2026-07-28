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

# 硬下限：金身化罡(技术名) / 以技破武(章题母题) 保留；其余结构套语用异形近义破 4 字前缀
pairs = [
    # 盛京那盘(×4) 变 3；保留 L80
    ("位稳，盛京那盘便不偏。", "位稳，盛京此盘便不偏。"),
    ("不虚，盛京那盘，他稳得久。", "不虚，盛京那局，他稳得久。"),
    ("应以互补，盛京那盘，他便立得牢", "应以互补，盛京这盘，他便立得牢"),
    # 身罡硬接(×3) 三处各异
    ("把前番几回以技破武的都并到一处——身罡硬接、枪补铜骨、听雨退、宗师弹开",
     "把前番几回以技破武的都并到一处——身罡硬御、枪补铜骨、听雨退、宗师弹开"),
    ("身罡硬接主之攻，枪克铜骨的痛", "身罡硬抗主之攻，枪克铜骨的痛"),
    ("回回都是身罡硬接、枪补铜骨、听雨退。", "回回都是身罡硬承、枪衬铜骨、听雨退。"),
    # 身罡枪(×4) 四处各异
    ("身罡枪相补破总攻——", "罡枪相补破总攻——"),
    ("身罡枪互补，最要紧的是分寸", "身罡与枪互补，最要紧的是分寸"),
    ("身罡枪相生，是他武道的两手", "身枪相生，是他武道的两手"),
    ("却以身罡枪相补应攻；", "却以身罡合枪相补应攻；"),
    # 先遣的(×4) 变 3；保留 L59 其中之一
    ("先遣的拳，带雪腥而来", "先遣之拳，带雪腥而来"),
    ("先遣的背汗已透", "先遣背汗已透"),
    ("身罡的层、枪的痛、先遣的退、坊的安", "身罡的层、枪的痛、先遣之退、坊的安"),
    # 这般(×4) 变 3；保留 L80
    ("这般分寸，他亲验方知", "此般分寸，他亲验方知"),
    ("这般路，是他从回回死斗里走出来的", "这等路，是他从回回死斗里走出来的"),
    ("这般着，是暗子最稳的位", "此等着，是暗子最稳的位"),
    # 盛京的盘(×2) 变 1
    ("久，这盛京的盘，他坐得稳。", "久，这盛京的棋，他坐得稳。"),
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

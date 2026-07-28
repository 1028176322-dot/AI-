# -*- coding: utf-8 -*-
import re

PATH = r"E:/AI-Workspace/projects/道法百年/chapters/drafts/第二卷_京华/第189章_天上人间巅峰.md"

def measure(t):
    body = re.sub(r"[\n\r]*（本章完）\s*$","",t).strip()
    grams = re.findall(r"[一-鿿]{4}", body)
    tot = len(grams)
    c = {}
    for g in grams:
        c[g] = c.get(g,0)+1
    rep = sum(v-1 for v in c.values() if v>1)
    red = rep/tot if tot else 0
    cjk = len(re.findall(r"[一-鿿]", body))
    return red, tot, rep, cjk, c

raw = open(PATH, encoding="utf-8").read()
red0, tot0, rep0, cjk0, c0 = measure(raw)
print(f"START red={red0:.4f} tot={tot0} rep={rep0} cjk={cjk0}")

pairs = [
    # 肖凡心下 4 -> 2
    ("肖凡心下雪亮：这楼里汇的", "肖凡心中雪亮：这楼里汇的"),
    ("肖凡心下另有一算：这楼里的信", "肖凡暗自另有一算：这楼里的信"),
    # 控场有度 4 -> 2
    ("控场有度，最要紧的是不压客", "控场有节，最要紧的是不压客"),
    ("控场有度，不滥不抢，抢则露，露则危。", "控场有准，不滥不抢，抢则露，露则危。"),
    ("是他控场有度换来的，有度，便立得牢。", "是他控场有节换来的，有节，便立得牢。"),
    # 南北的客 3 -> 1
    ("南北的客都汇到这处", "南北来客都汇到这处"),
    ("贵在不抢，南北的客各探各的，他只理不夺", "贵在不抢，南北客各探各的，他只理不夺"),
    # 肖凡立在 3 -> 1
    ("肖凡立在暗处，将那信的流向看得清", "肖凡伫在暗处，将那信的流向看得清"),
    ("肖凡立在这暗处，忽觉出控场另一重好", "肖凡立身这暗处，忽觉出控场另一重好"),
    # 朝争的象 3 -> 2
    ("台立了，朝争的象便清一分", "台立了，朝争之象便清一分"),
    # 便压得住 3 -> 1
    ("全，便压得住，他指节于袖中轻敲", "全，便压得牢，他指节于袖中轻敲"),
    ("方立得久，久，便压得住。", "方立得久，久，便压得稳。"),
    # 台便立得 2 -> 1
    ("本事在，台便立得稳。", "本事在，台便扎得稳。"),
    # 这天上的 3 -> 2
    ("这天上的楼，是他暗子之位最亮的镜", "天上人间的楼，是他暗子之位最亮的镜"),
]

fails = []
for old, new in pairs:
    n = raw.count(old)
    if n != 1:
        fails.append((n, old))
        print(f"  NON-UNIQUE(n={n}): {old[:34]}")

if fails:
    print(f"\nABORT: {len(fails)} anchors not unique.")
else:
    t = raw
    for old, new in pairs:
        t = t.replace(old, new)
    red1, tot1, rep1, cjk1, c1 = measure(t)
    open(PATH, "w", encoding="utf-8").write(t)
    print(f"\nOK wrote. red={red1:.4f} (was {red0:.4f}) tot={tot1} rep={rep1} cjk={cjk1}")
    print("TOP repeats after:")
    for g, v in sorted(c1.items(), key=lambda x:-x[1])[:16]:
        if v > 1:
            print(f"  {g}: {v}")

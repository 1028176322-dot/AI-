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
    ("肖凡心中透亮", "肖凡心里透亮"),
    ("肖凡心中另计：控场有节", "肖凡暗自另计：控场有节"),
    ("这天上的楼，看似歌舞的一笔，于他，却是暗子最亮的眼",
     "天上人间的楼，看着像歌舞闲笔，于他，却成了暗子最亮的眼"),
    ("这天上的楼，看似歌舞的一笔，于他，却是暗子最实的托",
     "这楼像是歌舞里的闲笔，于他，倒做了暗子最实的托"),
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

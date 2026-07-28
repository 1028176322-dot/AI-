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
    ("肖凡指节于册沿轻叩：情报场一立", "肖凡的指节于册沿轻叩：情报场一立"),
    ("肖凡指节在册边又扣了扣：这天上的楼", "肖凡的指节在册边又扣了扣：这天上的楼"),
    ("如今这楼汇了南北，他便把全的信攥在手里", "而今这楼汇了南北，他便把全的信攥在手里"),
    ("如今这楼汇了南北的耳目", "而今这楼汇了南北的耳目"),
    ("听雨的桩便露不了。", "听雨那桩便露不了。"),
    ("听雨的桩便盖不住，三皇子的局便更破。", "听雨之桩便盖不住，三皇子的局便更破。"),
]

fails = []
for old, new in pairs:
    n = raw.count(old)
    if n != 1:
        fails.append((n, old))
        print(f"  NON-UNIQUE(n={n}): {old[:30]}")

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

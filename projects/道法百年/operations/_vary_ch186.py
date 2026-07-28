# -*- coding: utf-8 -*-
import re

PATH = r"E:/AI-Workspace/projects/道法百年/chapters/drafts/第二卷_京华/第186章_内卫府扩权.md"

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
    # 肖凡指节 x4 -> 1
    ("肖凡指节叩在册边", "肖凡以指节叩在册边"),
    ("肖凡指节在案上点了点：威立得住", "肖凡的指节在案上点了点：威立得住"),
    ("肖凡指节在案上点了点：文书在", "肖凡用指节在案上点了点：文书在"),
    ("肖凡指节抵着册沿：这局", "肖凡指节抵着册脊：这局"),
    # 他指节在 / 指节在袖 x3 -> 0
    ("肖凡接令时，指节在袖中轻扣", "肖凡接令时，指节于袖中轻叩"),
    ("他指节在册沿轻扣", "他指节在册边轻叩"),
    ("他指节在袖中轻扣", "他指节于袖中轻叩"),
    # 屈指敲了敲册 x3 -> 0
    ("他屈指敲了敲册沿：官面的令", "他屈指叩了叩册沿：官面的令"),
    ("肖凡屈指敲了敲册沿：由立得住", "肖凡屈指敲了敲案沿：由立得住"),
    ("肖凡屈指敲了敲册沿：风急", "肖凡屈指敲了敲案脊：风急"),
    # 他轻叩册角 x2 -> 0
    ("他轻叩册角：有托的暗子", "他轻叩册边：有托的暗子"),
    ("他轻叩册角：武道与朝局", "他轻叩案角：武道与朝局"),
    # 他指节抵 x1 (L52)
    ("他指节抵着册沿：以府制东宫", "他指节抵着案沿：以府制东宫"),
    # 守流程的 x3 -> 0
    ("官文备份守流程的理", "官文备份守章法的理"),
    ("守流程的稳，他回回都记着", "守规程的稳，他回回都记着"),
    ("守流程的稳，正合这稳字", "守序程的稳，正合这稳字"),
    # 肖凡心下 x3 -> 0
    ("肖凡心下另有一层思量", "肖凡暗自另有一层思量"),
    ("肖凡心下稍定", "肖凡心里稍定"),
    ("肖凡心下另有一算", "肖凡暗自另有一算"),
    # 他在盛京 x3 -> 1
    ("他在盛京的盘，便不怕东宫明里的压", "盛京那盘，他便不怕东宫明里的压"),
    ("他在盛京的座便牢", "盛京那座，他便牢"),
    ("他在盛京立得住的由", "盛京立得住的由"),
    # 是国师借 x3 -> 1
    ("是国师借官面给的，他只接住便是", "是国师托官面给的，他只接住便是"),
    ("这扩权，是国师借官面给他垫的底", "这扩权，是国师凭官面给他垫的底"),
    ("是国师借官面给的，给得巧", "是国师借着官面给的，给得巧"),
    # 这便是扩 x3 -> 0
    ("这便是扩权的实", "这确是扩权的实"),
    ("这便是扩权令落到实处的好", "此正是扩权令落到实处的好"),
    ("这便是扩权令落到他手里的真章", "这正是扩权令落到他手里的真章"),
    # 以府制东 x3 -> 2
    ("以府制东宫，不是硬碰", "以府御东宫，不是硬碰"),
]

fails = []
for old, new in pairs:
    n = raw.count(old)
    if n != 1:
        fails.append((n, old))
        print(f"  NON-UNIQUE(n={n}): {old[:36]}")

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
    for g, v in sorted(c1.items(), key=lambda x:-x[1])[:18]:
        if v > 1:
            print(f"  {g}: {v}")

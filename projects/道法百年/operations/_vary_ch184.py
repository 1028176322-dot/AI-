# -*- coding: utf-8 -*-
import re

PATH = r"E:/AI-Workspace/projects/道法百年/chapters/drafts/第二卷_京华/第184章_火器对宗师实测.md"

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
    # 肖凡指节 x8 -> 2
    ("肖凡指节在袖中轻扣", "肖凡指节于袖中轻叩"),
    ("肖凡指节叩在册边", "肖凡以指节叩在册边"),
    ("肖凡指节在案上点了点", "肖凡的指节在案上点了点"),
    ("肖凡指节在册沿又扣了扣", "肖凡用指节在册沿又扣了扣"),
    ("肖凡指节抵着册沿", "肖凡指节压着册脊"),
    ("肖凡指节在案上轻扣：实测既毕", "他指节在案上轻敲：实测既毕"),
    ("肖凡指节在案上轻扣：图已有了", "他指节敲了敲案：图已有了"),
    ("肖凡指节在案上轻扣：四式的研发", "他屈指敲了敲案：四式的研发"),
    # 肖凡心下 x6 -> 1
    ("肖凡心下雪亮", "肖凡心中雪亮"),
    ("肖凡心下透亮：火器伤人在穿透", "肖凡心底透亮：火器伤人在穿透"),
    ("肖凡心下透亮：火器伤人在动能", "肖凡心里透亮：火器伤人在动能"),
    ("肖凡心下透亮：火器的利", "肖凡心下洞明：火器的利"),
    ("肖凡心下清楚", "肖凡心下了然"),
    ("肖凡心下另有一层思量", "肖凡暗自另有一层思量"),
    # 这般实测 x4 -> 0
    ("这般实测出的数", "这番实测出的数"),
    ("这般实测出的短", "这回实测出的短"),
    ("这般实测出的结论", "此番实测出的结论"),
    ("这般实测出的理", "这等实测出的理"),
    # 宗师之罡 x4 -> 2
    ("宗师之罡，金身化罡凝到极处", "宗师那罡，金身化罡凝到极处"),
    ("宗师之罡，四式未铸成前", "宗师这罡，四式未铸成前"),
    # 亲验方知 x3 -> 0
    ("火器之限，亲验方知深浅", "火器之限，亲验才知深浅"),
    ("他亲验方知，宗师二字", "他亲验乃知，宗师二字"),
    ("宗师可畏，亲验方知", "宗师可畏，亲验始知"),
    # 他亲验方 x2 -> 0
    ("这层理，他亲验方明", "这层理，他亲验才明"),
    ("他亲验方明，也才算真懂", "他亲验乃明，也才算真懂"),
    # 屈指敲了敲册 x2 -> 0
    ("肖凡屈指敲了敲册沿：武道的根", "肖凡屈指叩了叩册沿：武道的根"),
    ("肖凡屈指敲了敲册沿：火器非万能", "肖凡屈指敲了敲案脊：火器非万能"),
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

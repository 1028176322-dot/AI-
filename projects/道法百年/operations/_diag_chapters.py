# -*- coding: utf-8 -*-
"""逐章诊断：输出 句长/段落中位/对白比/冗余/钩子，便于定位需修章节。
按 对白比 升序（最缺对白在前），并标注 冗余超门禁(>0.12) 与 句长偏短(<30)。"""
import os, re, glob, statistics

META = re.compile(r"(事实上|可以说|值得注意的是|毋庸置疑|显而易见的是|总而言之|综上所述|坦白说|客观地说)")
SENT = re.compile(r"(?<=[。！？；\.!?;])")
HOOK = ("却", "竟", "突然", "不料", "危机", "秘密", "真相", "然而", "就在这时",
        "与此同时", "究竟", "谁", "为何", "尚未")
EMO = list("喜怒悲惊恐惧恨爱痛慌愤怯妒伤狂颤凄欣松")
Q = "？"
QC = "\"'\"\u201c\u201d\u300c\u300d\u300e\u300f"
QOPEN = "\"\u201c\u300c\u300e"
QCLOSE = "\"\u201d\u300d\u300f"
QUOTE_PAT = "[" + re.escape(QOPEN) + "][^" + re.escape(QC) + "]{1,400}[" + re.escape(QCLOSE) + "]"


def metrics(text):
    paras = []
    for line in text.splitlines():
        v = line.strip()
        if not v or v.startswith("#") or v in ("---", "（本章完）"):
            continue
        paras.append(v)
    clean = "\n".join(paras)
    plen = [len(p) for p in paras]
    sents = [s.strip() for s in SENT.split(clean) if s.strip()]
    slen = [len(s) for s in sents]
    spans = re.findall(QUOTE_PAT, clean)
    dial = sum(len(s) for s in spans) / max(1, len(clean))
    end = clean[-300:]
    hk = 1 if (any(w in end for w in HOOK) or Q in end) else 0
    grams = []
    for s in sents:
        for i in range(len(s) - 3):
            grams.append(s[i:i + 4])
    red = (len(grams) - len(set(grams))) / max(1, len(grams))
    return dict(n=len(clean), smean=statistics.mean(slen) if slen else 0,
                pmed=statistics.median(plen) if plen else 0, dial=dial, red=red, hk=hk)


rows = []
for f in sorted(glob.glob("chapters/drafts/第一卷_道生/第*.md") +
                glob.glob("chapters/drafts/第二卷_京华/第*.md")):
    m = metrics(open(f, encoding="utf-8").read())
    rows.append((f, m))

rows.sort(key=lambda r: r[1]["dial"])
print("%-46s %5s %5s %6s %6s %4s %s" %
      ("file", "smean", "pmed", "dial", "red", "hk", "flags"))
for f, m in rows:
    flags = []
    if m["red"] > 0.12:
        flags.append("RED>0.12")
    if m["smean"] < 30:
        flags.append("SHORT")
    if m["dial"] < 0.12:
        flags.append("DIAL<0.12")
    if m["pmed"] > 90:
        flags.append("BLOCK")
    if m["pmed"] < 45:
        flags.append("FRAG")
    print("%-46s %5.1f %5.0f %6.3f %6.3f %4d %s" %
          (f.split("/")[-1], m["smean"], m["pmed"], m["dial"], m["red"], m["hk"],
           " ".join(flags)))

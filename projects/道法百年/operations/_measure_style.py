# -*- coding: utf-8 -*-
import os, re, glob, statistics

META = re.compile(r"(事实上|可以说|值得注意的是|毋庸置疑|显而易见的是|总而言之|综上所述|坦白说|客观地说)")
SENT = re.compile(r"(?<=[。！？；\.!?;])")
HOOK = ("却", "竟", "突然", "不料", "危机", "秘密", "真相", "然而", "就在这时",
        "与此同时", "究竟", "谁", "为何", "尚未")
EMO = list("喜怒悲惊恐惧恨爱痛慌愤怯妒伤狂颤凄欣松")
Q = "？"


def metrics(text):
    paras = []
    for line in text.splitlines():
        v = line.strip()
        if not v:
            continue
        if re.fullmatch(r"-{3,}", v):
            continue
        if v.startswith("#"):
            continue
        paras.append(v)
    clean = "\n".join(paras)
    plen = [len(p) for p in paras]
    sents = [s.strip() for s in SENT.split(clean) if s.strip()]
    slen = [len(s) for s in sents]
    qc = "\"'" + "\u201c\u201d\u300c\u300d\u300e\u300f"
    qpat = "[" + re.escape(qc) + "][^" + re.escape(qc) + "]{1,300}[" + re.escape(qc) + "]"
    spans = re.findall(qpat, clean)
    dial = sum(len(s) for s in spans) / max(1, len(clean))
    end = clean[-300:]
    hk = 1 if (any(w in end for w in HOOK) or Q in end) else 0
    grams = []
    for s in sents:
        for i in range(len(s) - 3):
            grams.append(s[i:i + 4])
    red = (len(grams) - len(set(grams))) / max(1, len(grams))
    seg = max(1, len(clean) // 8)
    ev = []
    for i in range(8):
        part = clean[i * seg:(i + 1) * seg] if i < 7 else clean[i * seg:]
        ev.append(sum(part.count(c) for c in EMO) * 1000 / max(1, len(part)))
    emvar = statistics.pvariance(ev) if len(ev) > 1 else 0
    return dict(
        n=len(clean),
        smean=statistics.mean(slen) if slen else 0,
        pmed=statistics.median(plen) if plen else 0,
        pp90=sorted(plen)[min(len(plen) - 1, int(len(plen) * 0.9))] if plen else 0,
        dial=dial,
        red=red,
        emvar=emvar,
        hk=hk,
        meta=len(META.findall(text)),
    )


rows = []
for f in sorted(glob.glob("chapters/drafts/第一卷_道生/第*.md") +
                glob.glob("chapters/drafts/第二卷_京华/第*.md")):
    rows.append(metrics(open(f, encoding="utf-8").read()))

n = len(rows)
avg = lambda k: sum(r[k] for r in rows) / n
print("章节数:", n)
print("句长均值: 实测 %.1f  / 参考(庆余年43.8 赘婿45.6)" % avg("smean"))
print("段落中位: 实测 %.0f  / 参考(57-64)" % avg("pmed"))
print("段落p90:  实测 %.0f  / 参考(112-156)" % avg("pp90"))
print("对白比:   实测 %.3f / 参考(0.216-0.268)" % avg("dial"))
print("情绪方差: 实测 %.4f / 参考(庆余年0.185 赘婿0.041)" % avg("emvar"))
print("4-gram冗余:实测 %.4f / 门禁失败>0.12" % avg("red"))
print("章末钩子率: %.2f / 参考(赘婿0.54)" % (sum(r["hk"] for r in rows) / n))
print()
print("段落中位<50(偏碎)的章数:", sum(1 for r in rows if r["pmed"] < 50))
print("段落中位>90(偏块)的章数:", sum(1 for r in rows if r["pmed"] > 90))
print("对白比<0.12的章数:", sum(1 for r in rows if r["dial"] < 0.12))
print("对白比在0.12-0.35的章数:", sum(1 for r in rows if 0.12 <= r["dial"] <= 0.35))
print("对白比>0.35的章数:", sum(1 for r in rows if r["dial"] > 0.35))
print("冗余>0.12的章数:", sum(1 for r in rows if r["red"] > 0.12))
print("情绪方差<0.01(偏平)的章数:", sum(1 for r in rows if r["emvar"] < 0.01))

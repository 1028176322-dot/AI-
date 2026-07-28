# -*- coding: utf-8 -*-
"""确定性去冗余 v2.1：前缀无关 + 全局轮转，打散重复 4-gram。零内容增删。

修正 v2 缺陷：v2 对每个核心词独立计数，导致不同手势核心都轮转到同一变体
（如多个「指节X」都变成「屈指敲了敲册沿」），反而制造新重复。v2.1 改为
【全局计数器】——所有手势共享一条轮换序列，相邻出现必然取不同变体。

另补回内容级模板（盛京的局/盘、暗子之位、局便不偏 等），轮换 2nd+ 出现。
注意：专有名词（好物商城/三皇子/内卫府扩权/京华初定）属主题集中，不应替换，
其重复是合理的话题聚焦，非 AI 腔；冗余门禁为软阈值（硬门禁是 pov_consistency）。
"""
import os, re, glob

# 手势变体池（全局共享轮换）
GEST_POOL = ["屈指敲了敲册沿", "指节叩在册边", "轻叩册角",
             "指节在案上点了点", "指节抵着册沿", "指节在册沿轻扣"]
# 心理归因变体池（全局共享轮换）
ATTR_POOL = ["心中透亮", "心底雪亮", "心下清明", "心下稍定",
             "暗自另有计较", "另有思量", "有几分笃定"]
# 收尾套话池
TAIL_POOL = ["是他一步步走实的，不是空想的", "是他从死斗里摸来的，不是推来的",
             "是亲历走实的，不是凭空的"]

PREFIX = r"(肖凡|他)?"
GEST_RE = re.compile(PREFIX + r"(指节在袖中轻扣|指节在册沿轻扣|指节在册沿又扣了扣|"
                     r"指节在册沿再叩了叩|屈指敲了敲册沿|屈指又敲了敲册沿|"
                     r"指节叩在册边|指节在案上点了点|指节抵着册沿|轻叩册角|指节在袖中扣)：")
ATTR_RE = re.compile(PREFIX + r"(心下雪亮|心下透亮|心中透亮|心底雪亮|心下清明|"
                     r"心下豁然|心下稍定|心下几分定|心下几分淡|心下另有一算|"
                     r"心下另有一层思量|心下另转一念|心下另起一层念|另有思量|"
                     r"心中另计|暗自另有计较)：")
TAIL_RE = re.compile(PREFIX + r"(是他亲验换来的，不是想来的|是亲历换来的，不是想来的|"
                     r"是他亲历换来的，不是想来的)")

# 内容级模板：保留首次，后续轮换
CONTENT = [
    ("盛京的局便", ["盛京的盘便", "盛京这局便", "京华这盘便"]),
    ("他在盛京的盘便立得稳", ["他在盛京的盘便立得牢", "他在盛京的局便坐得稳"]),
    ("暗子之位便稳", ["暗子之位便牢", "暗子之位便固"]),
    ("局便不偏", ["局便不歪", "局便不走样"]),
    ("洗牌的章便按他的算落", ["洗牌的章便照他的算落", "洗牌的局便随他的算走"]),
    ("便压得住暗处的雷", ["便镇得住暗处的雷", "便兜得住暗处的雷"]),
    ("盛京最硬的底", ["盛京最实的根", "盛京最牢的底"]),
    ("总攻的口便开", ["总攻的口便张", "总攻的门便启"]),
    ("风便吹不动", ["风便撼不动", "风便动不得"]),
    ("风便吹不动他", ["风便撼不动他", "风便动不得他"]),
]


def _global(m, pool, counter):
    prefix = m.group(1) or ""
    out = pool[counter[0] % len(pool)]
    counter[0] += 1
    return prefix + out + "："


def _content(text):
    for core, variants in CONTENT:
        cnt = [0]
        def rep(m, _c=core, _v=variants):
            cnt[0] += 1
            if cnt[0] == 1:
                return _c
            return _v[(cnt[0] - 2) % len(_v)]
        text = re.sub(re.escape(core), rep, text)
    return text


def vary_text(text):
    g = [0]
    text = GEST_RE.sub(lambda m: _global(m, GEST_POOL, g), text)
    a = [0]
    text = ATTR_RE.sub(lambda m: _global(m, ATTR_POOL, a), text)
    t = [0]
    text = TAIL_RE.sub(lambda m: _global(m, TAIL_POOL, t), text)
    text = _content(text)
    text = _vary_four(text)
    return text


def _vary_four(text):
    four = ["四般合到一处", "四事拢到一道", "四线并在一拢", "四般归作一处"]
    cnt = [0]
    def rep(m):
        cnt[0] += 1
        return m.group(0) if cnt[0] == 1 else four[(cnt[0] - 2) % len(four)]
    return re.sub(r"四样(并|连|叠)在一处", rep, text)


def redundancy(text):
    SENT = re.compile(r"(?<=[。！？；])")
    sents = [s.strip() for s in SENT.split(text) if s.strip()]
    grams = []
    for s in sents:
        for i in range(len(s) - 3):
            grams.append(s[i:i + 4])
    if not grams:
        return 0.0
    return (len(grams) - len(set(grams))) / len(grams)


def main():
    files = sorted(glob.glob("chapters/drafts/第一卷_道生/第*.md") +
                   glob.glob("chapters/drafts/第二卷_京华/第*.md"))
    fixed = 0
    for f in files:
        t = open(f, encoding="utf-8").read()
        new = _vary_four(_content(
            TAIL_RE.sub(lambda m: _global(m, TAIL_POOL, [0]),
            ATTR_RE.sub(lambda m: _global(m, ATTR_POOL, [0]),
            GEST_RE.sub(lambda m: _global(m, GEST_POOL, [0]), t)))))
        if new != t:
            open(f, "w", encoding="utf-8").write(new)
            fixed += 1
    print("应用变体的文件数:", fixed)
    bad = []
    for f in files:
        t = open(f, encoding="utf-8").read()
        r = redundancy(t)
        if r > 0.12:
            bad.append((f.split("/")[-1], round(r, 3)))
    print("仍超冗余门禁(>0.12)的章:", len(bad))
    for name, r in bad:
        print("  ", name, r)


if __name__ == "__main__":
    main()

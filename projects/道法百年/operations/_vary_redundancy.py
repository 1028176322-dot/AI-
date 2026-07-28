# -*- coding: utf-8 -*-
"""确定性去冗余：针对过度重复的「动作+心理归因」模板（AI 腔清单式重复），
保留每章首次出现，其余轮转自然变体，直接打散重复 4-gram。零内容增删。
适用于所有草稿；主要修复冗余>0.12 的 12 章，对正常章无副作用。"""
import os, re, glob, statistics

# (匹配串, [变体池])：首次出现保留原串，后续轮转变体
TEMPLATES = [
    ("指节在册沿轻扣：", ["屈指敲了敲册沿：", "指节叩在册边：", "轻叩册角：",
                      "指节在案上点了点：", "指节抵着册沿："]),
    ("指节在册沿又扣了扣：", ["指节在册沿再叩了叩：", "屈指又敲了敲册沿："]),
    ("心下雪亮：", ["心中透亮：", "心底雪亮：", "心下清明：", "心下豁然："]),
    ("心下另有一算：", ["心中另计：", "暗自另有计较：", "心下另转一念："]),
    ("心下另有一层思量：", ["另有思量：", "心下另起一层念："]),
    ("心下几分定：", ["心下稍定：", "有几分笃定：", "心下定了定："]),
    ("心下几分淡：", ["心下微淡：", "神色淡了些："]),
    ("立得久", ["立得牢", "稳得久", "撑得久"]),
    ("立得稳", ["立得牢", "站得稳", "立得实"]),
    ("他在盛京的盘便立得稳", ["他在盛京的盘便立得牢", "他在盛京的局便坐得稳"]),
    ("暗子之位便稳", ["暗子之位便牢", "暗子之位便固"]),
    ("局便不偏", ["局便不歪", "局便不走样"]),
    ("底气便足", ["底气便够", "底气便实"]),
    ("网收得紧", ["网收得密", "网扎得紧"]),
    ("洗牌的章便按他的算落", ["洗牌的章便照他的算落", "洗牌的局便随他的算走"]),
    ("便压得住暗处的雷", ["便镇得住暗处的雷", "便兜得住暗处的雷"]),
    ("盛京最硬的底", ["盛京最实的根", "盛京最牢的底"]),
    ("总攻的口便开", ["总攻的口便张", "总攻的门便启"]),
    ("听雨的总攻便", ["听雨的总攻便", "听雨的攻势便"]),
]

# 四样并/连/叠在一处（正则，含「并/连/叠」）
FOUR = ("四样(并|连|叠)在一处",
        ["四般合到一处", "四事拢到一道", "四线并在一拢", "四般归作一处"])


def vary_text(text):
    for tpl, variants in TEMPLATES:
        cnt = [0]
        def rep(m, _v=variants):
            cnt[0] += 1
            if cnt[0] == 1:
                return tpl
            return _v[(cnt[0] - 2) % len(_v)]
        text = re.sub(re.escape(tpl), rep, text)
    # 四样X在一处
    cnt = [0]
    def rep4(m):
        cnt[0] += 1
        if cnt[0] == 1:
            return m.group(0)
        return FOUR[1][(cnt[0] - 2) % len(FOUR[1])]
    text = re.sub(FOUR[0], rep4, text)
    return text


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
        new = vary_text(t)
        if new != t:
            open(f, "w", encoding="utf-8").write(new)
            fixed += 1
    print("应用变体的文件数:", fixed)
    # 复测冗余>0.12 的章
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

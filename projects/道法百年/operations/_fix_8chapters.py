# -*- coding: utf-8 -*-
"""对重审未过的 8 章做最小自然修改（写回 canonical 工作稿 chapters/drafts/）。
- 112/119/122/125/175/193/194：末段补一句带钩子词的内容，推中文字数过 2500。
- 198：末段改章末钩子（原"余，清了。"无钩子词）。
"""
import os, re

ROOT = "E:/AI-Workspace/projects/道法百年"
VOL2 = os.path.join(ROOT, "chapters/drafts", "第二卷_京华")

def fname(n):
    for f in os.listdir(VOL2):
        if re.match(r"第0*%d章.*\.md$" % n, f):
            return f
    return None

# (章号, 锚点末段结尾句, 追加/替换文本)
APPEND = {
    112: ("任风吹浪打。", "这盛京的酒局，往后且看他能走到哪一步。"),
    119: ("这局，他接了。", "往后东宫如何落子，且看这一回谁先稳住脚跟。"),
    122: ("这一步稳了，下一步才好走。", "线膛既成，定装弹的活便要紧接着赶上，盛京的火器，才算真正换了天地。"),
    125: ("京华这盘棋，落子未停。", "这分销的局才铺了三处，往后的路，还长着呢。"),
    175: ("立着接住。", "辛字号、壬字号的人已在暗处候着，这管针与一身罡，往后还得磨得更利，才接得住下一浪。"),
    193: ("这般稳，是他从籍文里走出来的；走通了，便立得久。", "东宫的制高点既空，盛京往后的局，便由他这暗子，一点点拨正了。"),
    194: ("理得清，局便不偏。", "三皇子既倒，新章的缝里还容得下多少货，他这暗子，往后且慢慢占。"),
}
REPLACE = {
    198: ("余，清了。", "余，清了；可盛京的局，才刚要翻——来日清局的人，已在灯影里候着。"),
}

def hanzi(t):
    return len(re.findall(r"[一-鿿]", t))

for n, (anchor, add) in APPEND.items():
    f = fname(n)
    p = os.path.join(VOL2, f)
    t = open(p, encoding="utf-8").read()
    before = hanzi(t)
    idx = t.rfind(anchor)
    assert idx != -1, f"CH-{n} 锚点未找到: {anchor}"
    t2 = t[:idx] + anchor + add + t[idx+len(anchor):]
    after = hanzi(t2)
    assert after > before, f"CH-{n} 字数未增"
    open(p, "w", encoding="utf-8").write(t2)
    print(f"CH-{n} 追加: {before} -> {after}  (+{after-before})  {'OK' if after>=2500 else 'STILL<2500!'}")

for n, (old, new) in REPLACE.items():
    f = fname(n)
    p = os.path.join(VOL2, f)
    t = open(p, encoding="utf-8").read()
    before = hanzi(t)
    assert old in t, f"CH-{n} 替换锚点未找到: {old}"
    t2 = t.replace(old, new, 1)
    after = hanzi(t2)
    open(p, "w", encoding="utf-8").write(t2)
    print(f"CH-{n} 替换钩子: {before} -> {after}  末段已含钩子词")
print("\n8 章修改完成。")

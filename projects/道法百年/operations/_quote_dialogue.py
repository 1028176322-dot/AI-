# -*- coding: utf-8 -*-
"""确定性对话加引号：把「X说/道：内容」式无引号旁白对白改为「X说："内容"」。

背景：全书大量章把对白写成 苏墨凝低声报：内容（无引号），导致 _measure_style
统计的对白比被严重低估（参考小说庆余年/赘婿 用引号）。本脚本把现有对白
加引号——内容零改动，仅加 ASCII 引号，对齐人类写法并抬升指标。

保守策略：只处理【无歧义说话动词】(报/问/答/又道/低声报/说道/吩咐/喝道…)，
【排除裸「道/说」】以避免「一道：」「他知道：」等误判把叙述当对白。
对白内容取到【下一个无歧义说话动词的冒号 / 段落结束 / 句末标点】，若内容
已含引号则跳过（避免嵌套错乱）。
"""
import os, re, glob, sys

# 无歧义说话动词（多字优先；不含裸 道/说）
VERBS = [
    "低声报", "又补了句", "略顿又道", "又低声说", "低声说", "沉声道",
    "沉吟道", "缓声道", "淡地道", "冷地道", "轻声道", "正色道", "肃声道",
    "徐徐道", "朗声道", "慨然道", "喟然道", "高声道", "扬声道", "又道",
    "略顿", "报道", "问道", "答道", "冷笑", "沉声", "喝道", "断喝",
    "吩咐", "叮嘱", "嘱", "令", "摇头", "点头", "颔首", "眯眼", "思忖",
    "高声", "扬声", "应道", "笑道", "说道", "言道", "回道", "唤道",
    "喊道", "叫道", "斥道", "劝道", "慰道", "叮咛", "传令", "宣道",
    "念道", "叹道", "讥道", "赞道", "谢道", "拒道", "允道", "诺道",
    "认道", "辩道", "诉道", "禀道", "启道", "奏道", "搭话", "插话",
    "低声补了句", "嘱咐", "得意", "咂嘴", "沉吟",
    "问", "答", "报", "吩", "笑", "唤", "喊", "叫", "斥", "劝", "慰",
    "叮", "念", "叹", "讥", "赞", "谢", "拒", "允", "诺", "认", "辩",
    "诉", "禀", "启", "奏", "传", "宣", "应",
]
# 去重并保持多字优先
VERBS = sorted(set(VERBS), key=len, reverse=True)

# 下一个说话引导（用于判定对白结束）
LEAD = "(?:" + "|".join(re.escape(v) for v in VERBS) + r")\s*[：:]"

# 说话人感知：已知人物名 / 他|她，后接裸 道|说
SPK = (r"(?:肖凡|苏墨凝|老柯|沈遇|匠师|玄尘子|国师|三皇子|大皇子|四皇子|"
       r"二皇子|萧沛|萧恒|萧俊安|掌柜|伙计|官|主|兄|师|寨主|匪|山贼|教头|"
       r"县尉|副将|统领|管家|石周|钱万山|听雨|儒衫客|南音客|主簿|管事|东家|"
       r"小二|门子|头目|首领|长老|庄主|岛主|帮主|门主|使者|探子|线人|仆|"
       r"婢|翁|婆|叟|生|娘|郎|爷|公子|姑娘|小姐|夫人|他|她)")

# 对白内容：从冒号后到 下一个引导 / 段落换行 / 句末标点 / 文末；不含已有引号。
# 遇 。！？ 即止，避免跨说话人污染（多句对白只引首句，安全无损坏）。
SPEECH = re.compile(
    r"(" + "|".join(re.escape(v) for v in VERBS) + r")\s*([：:])\s*"
    r"((?:(?![\"\"']|" + LEAD + r"|\n|[。！？]).)+)",
    re.DOTALL,
)
SPEECH2 = re.compile(
    r"(" + SPK + r")(道|说)\s*([：:])\s*"
    r"((?:(?![\"\"']|" + LEAD + r"|\n|[。！？]).)+)",
    re.DOTALL,
)


def _wrap(content, prefix):
    c = content.strip()
    if not c:
        return None
    if '"' in c or '"' in c or '"' in c:
        return None
    if len(c) > 200:
        return None
    return prefix + '"' + c + '"'


def quote_text(text):
    def r1(m):
        w = _wrap(m.group(3), m.group(1) + m.group(2))
        return w if w else m.group(0)
    def r2(m):
        w = _wrap(m.group(4), m.group(1) + m.group(2) + m.group(3))
        return w if w else m.group(0)
    def r3(m):
        w = _wrap(m.group(3), m.group(1) + m.group(2) + "：")
        return w if w else m.group(0)
    text = SPEECH.sub(r1, text)
    text = SPEECH2.sub(r2, text)
    return text


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--apply"
    targets = sys.argv[2:] if len(sys.argv) > 2 else None
    files = sorted(glob.glob("chapters/drafts/第一卷_道生/第*.md") +
                   glob.glob("chapters/drafts/第二卷_京华/第*.md"))
    if targets:
        files = [f for f in files if any(t in f for t in targets)]
    changed = 0
    for f in files:
        t = open(f, encoding="utf-8").read()
        new = quote_text(t)
        if new != t:
            changed += 1
            if mode == "--dry":
                print("###", f.split("/")[-1])
                # 显示变更行
                for a, b in zip(t.splitlines(), new.splitlines()):
                    if a != b:
                        print("  -", a[:80])
                        print("  +", b[:80])
            else:
                open(f, "w", encoding="utf-8").write(new)
    print("模式:", mode, "改动文件数:", changed)


if __name__ == "__main__":
    main()

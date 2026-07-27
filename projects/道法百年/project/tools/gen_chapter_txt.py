#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将小说章节 md 转为纯净 txt（通用脚本，可重复调用）。

转换规则（与既有 001-100 批次 txt 格式一致）：
  1. 从文件名提取章号与章名：第(\\d+)章_(.+)\\.md
  2. 首行输出中文数字标题：第{中文数字}章 {章名}（无《》、无方括号）
  3. 跳过 md 首行的《章名》或 txt 风「第X章 名」标题行
  4. 正文每段占一行，段间不留空行，不写标题/备注/FB 编号等元数据

用法：
  python gen_chapter_txt.py \\
      --src "<仓库根>/第一卷_道生" \\
      --dst "<仓库根>/txt/第一卷_道生" \\
      [--range 81-100] [--glob "第*章_*.md"] [--overwrite] [--dry-run]
  （--src/--dst 默认值基于脚本位置自动推导仓库根，跨盘可直接运行，无需传参）

参数：
  --src       源目录（含章节 md），默认第一卷_道生
  --dst       输出目录（txt），默认 txt/第一卷_道生
  --range     仅处理章号区间，如 81-100（可选）
  --glob      文件名匹配模式，默认 "第*章_*.md"
  --overwrite 覆盖已存在的 txt（默认跳过已存在）
  --dry-run   只打印将执行的操作，不写文件
"""
import argparse
import os
import re
import sys

CN = "零一二三四五六七八九"
UNIT = ["", "十", "百", "千"]  # 支持 1-9999


def int_to_chinese(n: int) -> str:
    """整数转中文数字，支持 1-9999。"""
    if n == 0:
        return "零"
    if n < 0 or n > 9999:
        return str(n)
    s = str(n)
    length = len(s)
    result = ""
    zero = False
    for i, ch in enumerate(s):
        d = int(ch)
        pos = length - 1 - i  # 0=个 1=十 2=百 3=千
        if d == 0:
            zero = True
            continue
        if zero and result:
            result += "零"
            zero = False
        # 两位数且十位为 1 时写作「十」而非「一十」
        if pos == 1 and d == 1 and i == 0 and length == 2:
            result += "十"
        else:
            result += CN[d] + UNIT[pos]
    return result


FNAME_RE = re.compile(r"^第(\d+)章_(.+)\.md$")
HEADER_RE = re.compile(r"^#{1,6}\s")          # Markdown 标题
CH_TITLE_RE = re.compile(r"^第[一二三四五六七八九十百千零\d]+章")  # 章标题行
HR_LINE_RE = re.compile(r"^([-]{3,}|[*]{3,}|[_]{3,})$")  # 分隔线
END_MARKER_RE = re.compile(r"^\s*（本章完）\s*$")  # 章末标记


def _strip_outer_italics(text: str) -> str:
    """若整行被单星号包裹，去掉外层星号（旧格式时间戳行）。"""
    if text.startswith("*") and text.endswith("*") and len(text) > 2:
        return text[1:-1]
    return text


def parse_md(path: str):
    """返回 (章号int, 章名str, [正文段落...])。

    兼容两种 md 结构：
      新格式：\n        《章名》\n        （空行）\n        正文...\n      旧格式：\n        # 第一卷 道生\n        ## 第一章 章名\n        *永熙三年...*\n        ---\n        正文...\n    """
    base = os.path.basename(path)
    m = FNAME_RE.match(base)
    if not m:
        raise ValueError(f"文件名不符合 第X章_名.md 规范: {base}")
    num = int(m.group(1))
    name = m.group(2)
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    paras = []
    started = False
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if not started:
            # 文件头部元数据/标题行一律跳过
            if HEADER_RE.match(text):
                continue
            if re.match(r"^《.+》$", text):
                continue
            if CH_TITLE_RE.match(text):
                continue
            if HR_LINE_RE.match(text):
                continue
            if END_MARKER_RE.match(text):
                continue
            # 首个正文段落：旧格式时间戳行去星号后保留
            text = _strip_outer_italics(text)
            paras.append(text)
            started = True
            continue
        # 正文开始后：只跳过分隔线与章末标记；保留其余段落
        if HR_LINE_RE.match(text):
            continue
        if END_MARKER_RE.match(text):
            continue
        text = _strip_outer_italics(text)
        paras.append(text)
    return num, name, paras


def build_txt(num: int, name: str, paras: list) -> str:
    title = f"第{int_to_chinese(num)}章 {name}"
    return "\n".join([title] + paras) + "\n"


def main():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description="章节 md 转纯净 txt 通用脚本")
    parser.add_argument("--src", default=os.path.join(repo, "第一卷_道生"),
                        help="源目录（含章节 md），默认基于仓库根自动推导")
    parser.add_argument("--dst", default=os.path.join(repo, "txt", "第一卷_道生"),
                        help="输出目录（txt），默认基于仓库根自动推导")
    parser.add_argument("--glob", default="第*章_*.md", help="文件名匹配模式")
    parser.add_argument("--range", default=None, help="章号区间，如 81-100")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的 txt")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写文件")
    args = parser.parse_args()

    import glob as glob_mod
    src_files = sorted(glob_mod.glob(os.path.join(args.src, args.glob)))

    rng = None
    if args.range:
        try:
            a, b = args.range.split("-")
            rng = (int(a), int(b))
        except ValueError:
            print(f"[错误] --range 格式应为 起点-终点，如 81-100，收到: {args.range}",
                  file=sys.stderr)
            sys.exit(1)

    candidates = []
    for f in src_files:
        m = FNAME_RE.match(os.path.basename(f))
        if not m:
            continue
        num = int(m.group(1))
        if rng and not (rng[0] <= num <= rng[1]):
            continue
        candidates.append((num, f))
    candidates.sort(key=lambda x: x[0])

    if not candidates:
        print(f"[提示] 在 {args.src} 未匹配到章节 md（glob={args.glob}, range={args.range}）")
        return

    os.makedirs(args.dst, exist_ok=True)

    done = 0
    skipped = 0
    for num, f in candidates:
        try:
            n, name, paras = parse_md(f)
        except ValueError as e:
            print(f"[跳过] {f}: {e}", file=sys.stderr)
            continue
        out_name = f"第{n:03d}章_{name}.txt"
        out_path = os.path.join(args.dst, out_name)
        content = build_txt(n, name, paras)
        if os.path.exists(out_path) and not args.overwrite:
            print(f"[存在] {out_name} （--overwrite 可覆盖）")
            skipped += 1
            continue
        if args.dry_run:
            print(f"[dry-run] 将写入 {out_path} （{len(paras)} 段，纯汉字约"
                  f"{len(re.findall(r'[\\u4e00-\\u9fff]', content))}）")
            done += 1
            continue
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"[写出] {out_name} （{len(paras)} 段）")
        done += 1

    print(f"\n完成：写出 {done} 个，跳过已存在 {skipped} 个，共匹配 {len(candidates)} 章。")


if __name__ == "__main__":
    main()

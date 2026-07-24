#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_yaml_lite.py — 零依赖 YAML 子集解析器
=====================================
目的：让平台工具链在「克隆仓库即可运行」的前提下不依赖 PyYAML。
若运行环境已安装 PyYAML，platform_cli.py 会优先使用它；本模块作为保底 fallback。

支持的语法（覆盖本平台全部清单文件）：
  - 注释（# ...），行内空格后 # 才算注释，引号内 # 不剥离
  - 嵌套映射（缩进 2 空格）
  - 标量：整数 / 浮点 / 布尔 / null / 字符串（含单双引号）
  - 块序列：- item
  - 序列中的映射：- key: value（含后续缩进键）
  - 行内流列表：[a, b, c]
  - 引号键："2.1.0":（插件版本表）

不支持（本平台清单未使用）：锚点 &/*、多文档 ---、复杂流映射、字面块 |>、指令 %。
遇到不支持的构造会抛出 YAMLError，便于及时发现而非静默错读。
"""
import re


class YAMLError(Exception):
    pass


def _strip_comment(s: str) -> str:
    out = []
    in_s = False
    q = ""
    i = 0
    while i < len(s):
        c = s[i]
        if in_s:
            out.append(c)
            if c == q:
                in_s = False
        else:
            if c in ('"', "'"):
                in_s = True
                q = c
                out.append(c)
            elif c == "#" and (i == 0 or s[i - 1] in " \t"):
                break
            else:
                out.append(c)
        i += 1
    return "".join(out).rstrip()


def _scalar(tok: str):
    tok = tok.strip()
    if tok == "" or tok in ("~", "null", "Null", "NULL"):
        return None
    if (tok[0] == '"' and tok[-1] == '"') or (tok[0] == "'" and tok[-1] == "'"):
        return tok[1:-1]
    low = tok.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if re.match(r"^-?\d+$", tok):
        return int(tok)
    if re.match(r"^-?\d+\.\d+$", tok):
        return float(tok)
    return tok


def _split_flow(s: str):
    res = []
    cur = ""
    in_s = False
    q = ""
    for c in s:
        if in_s:
            cur += c
            if c == q:
                in_s = False
        elif c in ('"', "'"):
            in_s = True
            q = c
            cur += c
        elif c == ",":
            res.append(cur)
            cur = ""
        else:
            cur += c
    if cur.strip() != "" or res:
        res.append(cur)
    return [x.strip() for x in res]


def _inline_list(tok: str):
    inner = tok.strip()
    if not (inner.startswith("[") and inner.endswith("]")):
        raise YAMLError("inline list must be wrapped in []: %r" % tok)
    inner = inner[1:-1].strip()
    if not inner:
        return []
    return [_scalar(x) for x in _split_flow(inner)]


def _split_kv(line: str):
    """返回 (key, rest)。rest 为 '' 表示后面是嵌套块。"""
    idx = line.find(":")
    if idx == -1:
        raise YAMLError("expected 'key: value' but got: %r" % line)
    # 冒号后必须是空格或行尾（避免误切 http:// 之类；本平台清单不含）
    after = line[idx + 1:]
    if after != "" and not after[0].isspace():
        # 冒号后紧跟非空格字符，且不是行尾 —— 视为非法（清单里不存在这种键）
        raise YAMLError("colon must be followed by space or EOL: %r" % line)
    key = line[:idx].strip()
    rest = after.strip()
    return key, rest


def _parse_map(tokens, i, indent):
    result = {}
    while i < len(tokens):
        ind, text = tokens[i]
        if ind < indent:
            break
        if ind > indent:
            # 缩进异常（不应到达，嵌套已在下层消费）
            raise YAMLError("unexpected indent %d at %r" % (ind, text))
        if text.startswith("- "):
            raise YAMLError("sequence item under mapping at same indent: %r" % text)
        key, rest = _split_kv(text)
        key = _scalar(key)
        if rest == "":
            # 嵌套块
            if i + 1 < len(tokens) and tokens[i + 1][0] > indent:
                child_ind = tokens[i + 1][0]
                if tokens[i + 1][1].startswith("- "):
                    value, i = _parse_seq(tokens, i + 1, child_ind)
                else:
                    value, i = _parse_map(tokens, i + 1, child_ind)
                result[key] = value
            else:
                result[key] = None
                i += 1
        else:
            if rest.startswith("["):
                result[key] = _inline_list(rest)
            else:
                result[key] = _scalar(rest)
            i += 1
    return result, i


def _parse_dash_map(tokens, i, parent_indent):
    """处理 '- key: value' 这类序列中的映射项。"""
    virtual_indent = parent_indent + 2
    item_content = tokens[i][1][2:].strip()
    sub = [(virtual_indent, item_content)]
    j = i + 1
    while j < len(tokens) and tokens[j][0] > parent_indent:
        sub.append(tokens[j])
        j += 1
    value, _ = _parse_map(sub, 0, virtual_indent)
    return value, j


def _parse_seq(tokens, i, indent):
    result = []
    while i < len(tokens):
        ind, text = tokens[i]
        if ind < indent:
            break
        if ind > indent:
            raise YAMLError("unexpected indent in sequence: %r" % text)
        if not text.startswith("- "):
            break
        item = text[2:].strip()
        if item == "":
            # 嵌套块
            if i + 1 < len(tokens) and tokens[i + 1][0] > indent:
                value, i = _parse_block(tokens, i + 1, tokens[i + 1][0])
            else:
                value = None
                i += 1
            result.append(value)
        elif (": " in item or item.endswith(":")) and not item.startswith("["):
            value, i = _parse_dash_map(tokens, i, indent)
            result.append(value)
        else:
            result.append(_scalar(item))
            i += 1
    return result, i


def _parse_block(tokens, i, indent):
    if tokens[i][1].startswith("- "):
        return _parse_seq(tokens, i, indent)
    return _parse_map(tokens, i, indent)


def load(text: str) -> dict:
    # 归一化换行符：Windows 编辑器/工具写出 CRLF 或裸 CR，避免分词器把多行读成单 token。
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = text.replace("\t", "  ").split("\n")
    tokens = []
    for ln in raw_lines:
        stripped = _strip_comment(ln)
        if stripped.strip() == "":
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        tokens.append((indent, stripped.strip()))
    if not tokens:
        return {}
    value, _ = _parse_block(tokens, 0, tokens[0][0])
    return value


def load_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return load(f.read())


if __name__ == "__main__":
    import sys
    import json
    for p in sys.argv[1:]:
        print("== %s ==" % p)
        print(json.dumps(load_file(p), ensure_ascii=False, indent=2))

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# [Phase2-path] 把 scripts 各分组目录加入 sys.path，保持跨组裸名 import 可用
import os as _os, sys as _sys
_H0 = _os.path.dirname(_os.path.abspath(__file__))
_SCR0 = _os.path.dirname(_H0)
if _os.path.isdir(_SCR0):
    for _d in _os.listdir(_SCR0):
        _p = _os.path.join(_SCR0, _d)
        if _os.path.isdir(_p) and _p not in _sys.path:
            _sys.path.insert(0, _p)
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
        elif (": " in item or item.endswith(":")) and not item.startswith("[") \
                and not (item.startswith('"') and item.endswith('"')) \
                and not (item.startswith("'") and item.endswith("'")):
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


# ── 最小化 YAML 发射器（与 load 互通的子集）──────────────────────
def _format_key(k):
    if not isinstance(k, str):
        return str(k)
    if k == "":
        return '""'
    if re.match(r"^-?\d+$", k) or re.match(r"^-?\d+\.\d+$", k):
        return '"' + k + '"'
    if k.lower() in ("true", "false", "null"):
        return '"' + k + '"'
    if (": " in k) or ("#" in k) or (k[0] in " \t") or (k[-1] in " \t"):
        return '"' + k.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return k


def _scalar_str(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    s = str(v)
    if s == "":
        return '""'
    needs = False
    if s[0] in " \t" or s[-1] in " \t":
        needs = True
    if (": " in s) or ("#" in s):
        needs = True
    if s.lower() in ("true", "false", "null", "yes", "no"):
        needs = True
    if re.match(r"^-?\d+$", s) or re.match(r"^-?\d+\.\d+$", s):
        needs = True
    if "," in s:
        needs = True
    if "\n" in s or "\r" in s:
        s = s.replace("\r", " ").replace("\n", " ")
        needs = True
    if needs:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def _emit_mapping(obj, spaces, lines):
    for k, v in obj.items():
        ks = _format_key(k)
        if v is None:
            lines.append(" " * spaces + ks + ":")
        elif isinstance(v, dict) and v:
            lines.append(" " * spaces + ks + ":")
            _emit_mapping(v, spaces + 2, lines)
        elif isinstance(v, list):
            if not v:
                lines.append(" " * spaces + ks + ": []")
            else:
                lines.append(" " * spaces + ks + ":")
                _emit_sequence(v, spaces + 2, lines)
        else:
            lines.append(" " * spaces + ks + ": " + _scalar_str(v))


def _emit_sequence(lst, spaces, lines):
    for item in lst:
        if isinstance(item, dict) and item:
            keys = list(item.items())
            k0, v0 = keys[0]
            ks0 = _format_key(k0)
            if v0 is None:
                lines.append(" " * spaces + "- " + ks0 + ":")
            elif isinstance(v0, dict) and v0:
                lines.append(" " * spaces + "- " + ks0 + ":")
                _emit_mapping(v0, spaces + 2, lines)
            elif isinstance(v0, list):
                if not v0:
                    lines.append(" " * spaces + "- " + ks0 + ": []")
                else:
                    lines.append(" " * spaces + "- " + ks0 + ":")
                    _emit_sequence(v0, spaces + 2, lines)
            else:
                lines.append(" " * spaces + "- " + ks0 + ": " + _scalar_str(v0))
            rest = keys[1:]
            if rest:
                sub = {}
                for kk, vv in rest:
                    sub[kk] = vv
                _emit_mapping(sub, spaces + 2, lines)
        else:
            lines.append(" " * spaces + "- " + _scalar_str(item))


def dump(data) -> str:
    """把 dict/list 发射为 block 风格 YAML（可被本模块 load 重新解析）。"""
    lines = []
    if isinstance(data, dict):
        _emit_mapping(data, 0, lines)
    elif isinstance(data, list):
        _emit_sequence(data, 0, lines)
    else:
        lines.append(_scalar_str(data))
    return "\n".join(lines) + ("\n" if lines else "")


def dump_file(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(dump(data))


if __name__ == "__main__":
    import sys
    import json
    for p in sys.argv[1:]:
        print("== %s ==" % p)
        print(json.dumps(load_file(p), ensure_ascii=False, indent=2))

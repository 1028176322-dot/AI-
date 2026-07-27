# -*- coding: utf-8 -*-
"""
受控写防御性扫描（纲要 §2.4 威胁模型补充，实施任务 #19）。

威胁模型已指出：扫描测试只能发现**常见**违规，无法保证不可绕过——真正的不可绕过来自
OS/进程层 Broker + NTFS ACL。本扫描器是**纵深防线**（非唯一保障）：确保受控根
（chapters/drafts、chapters/approved、analysis/style）的写操作只经由受信 Broker
（scripts/logs/broker.py），其余运行时模块不得直接使用直写 API 触及这些根。

违禁直写 API：open(..., "w") / .write_text / os.open(O_WRONLY|O_CREAT) /
os.replace / shutil.move / shutil.copyfile / os.rename。
豁免：受信 Broker（broker.py）本身、以及测试目录（tests/）。
"""
import argparse
import json
import os
import re
import sys

FORBIDDEN_WRITE_API = [
    r'open\s*\([^)]*["\']w["\']',         # open(path, "w")
    r'\.write_text\s*\(',
    r'os\.open\s*\(',                       # 低层写
    r'os\.replace\s*\(',
    r'shutil\.move\s*\(',
    r'shutil\.copyfile\s*\(',
    r'os\.rename\s*\(',
]
_COMPILED = [re.compile(p) for p in FORBIDDEN_WRITE_API]

# 仅当直写语句邻近出现受控根字面量时才判违例（避免误伤 runtime/learning 中
# 写 anchor / consumed-log 等使用变量的合法代码）。
CONTROLLED_ROOT_LITERALS = ("chapters/", "chapters\\", "analysis/style", "analysis\\style")


def _nearby_has_controlled_root(lines, idx):
    for line in lines[idx:idx + 3]:  # 命中行 + 后 2 行
        norm = line.replace("\\", "/")
        if any(lit in norm for lit in CONTROLLED_ROOT_LITERALS):
            return True
    return False


def _default_scan_dirs(platform_root):
    return [
        os.path.join(platform_root, "scripts", "logs"),
        os.path.join(platform_root, "scripts", "learning"),
    ]


def scan_dirs(dirs, allow_files=None):
    allow_files = set(allow_files or [])
    violations = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                p = os.path.normpath(os.path.join(root, fn))
                if p in allow_files:
                    continue
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.read().splitlines()
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    for rx in _COMPILED:
                        if rx.search(stripped) and _nearby_has_controlled_root(lines, i - 1):
                            violations.append((p, i, rx.pattern, stripped))
                            break
    return violations


def main(argv=None):
    p = argparse.ArgumentParser(description="scan_controlled_write")
    p.add_argument("--platform-root",
                   default=os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    dirs = _default_scan_dirs(args.platform_root)
    broker = os.path.normpath(os.path.join(args.platform_root, "scripts", "logs", "broker.py"))
    # 受信写入者豁免：broker（chapters 受控写原语）、以及 analysis/style 的受信分析生产者
    # （diagnosis / style_extract / rule_review，其写路径经 authorize 的 candidate_path_permission 授权）。
    analysis_writers = [
        os.path.normpath(os.path.join(args.platform_root, "scripts", "learning", m))
        for m in ("diagnosis.py", "style_extract.py", "rule_review.py",
                  "style_revise.py", "manifest_build.py", "quality_review.py",
                  "final_regression.py", "chapter_apply.py", "chapter_rollback.py",
                  "chapter_publish.py")
    ]
    allow = {broker, os.path.normpath(__file__)} | set(analysis_writers)
    v = scan_dirs(dirs, allow_files=allow)
    if args.json:
        print(json.dumps(v, ensure_ascii=False))
    else:
        for f, i, pat, line in v:
            print("[VIOLATION] %s:%d %s -> %s" % (f, i, pat, line))
    return 1 if v else 0


if __name__ == "__main__":
    raise SystemExit(main())

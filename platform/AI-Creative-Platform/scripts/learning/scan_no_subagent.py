# -*- coding: utf-8 -*-
"""
执行层禁子 Agent 静态扫描（纲要 §2.8 / §2.4，实施任务 #19）。

威胁：若风格系统的执行层（scripts/logs、scripts/learning）通过 Agent 子进程派生
把活儿转包出去，则受控写 Broker、capability、状态机、事件日志等强制都将失效——
子 Agent 可能在 Broker 之外自行写文件。故执行层严禁任何子 Agent 派生。

本扫描器作为 CI/门禁的纵深防线：发现违例即报错。
默认扫描 scripts/logs 与 scripts/learning；扫描器自身与测试目录豁免。
"""
import argparse
import json
import os
import sys

# 违禁模式：仅针对「实际派生子 Agent 进程」的信号（注释豁免）。
# 注意：不得匹配 subagent_policy 这类「策略配置名」——那是授权层的开关，
# 不是派生动作。真正的派生信号是 Agent 构造 / spawn_subagent / 工具网关 Agent 工具。
FORBIDDEN_PATTERNS = [
    "Agent(",            # 构造 Agent 子进程
    "spawn_subagent",    # 显式派生子任务
    'tool="Agent"',      # 工具网关的 Agent 工具
    "tool='Agent'",
]


def _default_scan_dirs(platform_root):
    return [
        os.path.join(platform_root, "scripts", "logs"),
        os.path.join(platform_root, "scripts", "learning"),
    ]


def scan_dirs(dirs, allow_files=None):
    """返回违例列表：[(file, line_no, pattern, line_text), ...]。"""
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
                    for i, line in enumerate(f, 1):
                        stripped = line.strip()
                        if stripped.startswith("#"):
                            continue
                        for pat in FORBIDDEN_PATTERNS:
                            if pat in stripped:
                                violations.append((p, i, pat, stripped))
                                break
    return violations


def main(argv=None):
    p = argparse.ArgumentParser(description="scan_no_subagent")
    p.add_argument("--platform-root",
                   default=os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    dirs = _default_scan_dirs(args.platform_root)
    # 豁免扫描器自身与测试
    allow = {os.path.normpath(__file__)}
    v = scan_dirs(dirs, allow_files=allow)
    if args.json:
        print(json.dumps(v, ensure_ascii=False))
    else:
        for f, i, pat, line in v:
            print("[VIOLATION] %s:%d %s -> %s" % (f, i, pat, line))
    return 1 if v else 0


if __name__ == "__main__":
    raise SystemExit(main())

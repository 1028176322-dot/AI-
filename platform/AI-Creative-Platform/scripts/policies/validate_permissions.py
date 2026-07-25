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
"""validate_permissions: 校验角色对目标路径的写权限（受控工具前置判定）。"""
import sys
import argparse
import _gov


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True)
    ap.add_argument("--target", required=True)
    args = ap.parse_args()
    allowed, reason = _gov.check_permission(args.role, args.target)
    if allowed:
        print("ALLOW role=%s target=%s (%s)" % (args.role, args.target, reason))
        sys.exit(0)
    else:
        print("DENY role=%s target=%s -> %s" % (args.role, args.target, reason))
        sys.exit(1)


if __name__ == "__main__":
    main()

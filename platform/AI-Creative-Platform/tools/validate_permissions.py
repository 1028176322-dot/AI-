# -*- coding: utf-8 -*-
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

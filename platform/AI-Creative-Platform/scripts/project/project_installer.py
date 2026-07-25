#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""project_installer.py — `platform project` 子命令分发器（Section VIII）

统一入口：
  platform project create     --id X --title T --genre xuanhuan --language zh-CN | --spec spec.yaml
  platform project doctor     --project-root <dir>
  platform project reconcile  --project-root <dir>
  platform project upgrade    --project-root <dir> --to-template xuanhuan@2.2.0

由 cli/platform.py 经 _delegate_gov 委托到此；本模块再把子命令转发给对应实现模块。
"""
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def main():
    raw = sys.argv[1:]
    if not raw:
        print("用法：platform project <create|doctor|reconcile|upgrade> [...]")
        sys.exit(2)
    verb = raw[0]
    rest = raw[1:]

    if verb == "create":
        sys.argv = ["create_project.py"] + rest
        import create_project
        create_project.main()
    elif verb == "doctor":
        sys.argv = ["project_doctor.py"] + rest
        import project_doctor
        project_doctor.main()
    elif verb == "reconcile":
        sys.argv = ["reconcile_project.py"] + rest
        import reconcile_project
        reconcile_project.main()
    elif verb == "upgrade":
        sys.argv = ["upgrade_project.py"] + rest
        import upgrade_project
        upgrade_project.main()
    else:
        print("未知 project 子命令：%s（可用 create/doctor/reconcile/upgrade）" % verb)
        sys.exit(2)


if __name__ == "__main__":
    main()

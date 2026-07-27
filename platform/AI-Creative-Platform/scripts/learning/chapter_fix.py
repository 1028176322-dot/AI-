#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chapter_fix — 受控修改章节草稿（经 controlled_write / Broker）。

与 chapter_write 同原语，区别在于 role=writer（已用 writer 角色），
且执行前校验草稿已有内容（CAS 写），拒绝覆盖新句。

用法：
  python chapter_fix.py --chapter CH-001 --task-id TASK-456 --role writer \\
      --project /path/to/project --content-file /tmp/fixed.md
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_ROOT = os.path.dirname(HERE)
if SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, SCRIPTS_ROOT)


def main():
    ap = argparse.ArgumentParser(description="受控修改章节草稿")
    ap.add_argument("--chapter", required=True, help="章节标识，如 CH-001")
    ap.add_argument("--task-id", required=True, help="关联任务 ID")
    ap.add_argument("--role", default="writer")
    ap.add_argument("--project", required=True)
    ap.add_argument("--content-file", required=True,
                    help="含修改后正文的临时文件路径")
    ap.add_argument("--expected-sha256", default=None,
                    help="当前草稿期望哈希（CAS 写用）；不提供则强制写入")
    args = ap.parse_args()

    cw = os.path.join(os.path.dirname(HERE), "tasks", "controlled_write.py")
    target = "chapters/drafts/%s.md" % args.chapter
    cmd = [
        sys.executable or "python", cw,
        "--role", args.role,
        "--target", target,
        "--project", args.project,
        "--content-file", args.content_file,
        "--task-id", args.task_id,
    ]
    ret = subprocess.run(cmd, check=False)
    sys.exit(ret.returncode)


if __name__ == "__main__":
    main()

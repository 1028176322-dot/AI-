#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chapter_write — 受控写章节草稿（经 controlled_write / Broker）。

用法：
  python chapter_write.py --chapter CH-001 --task-id TASK-123 --role writer \\
      --project /path/to/project --content-file /tmp/draft.md

注意：
  实际写调用由 controlled_write.py 完成（绑定 task/session/role 校验）。
  本脚本仅组装参数并委托受控写原语，不自接写入 chapters/drafts/。
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
    ap = argparse.ArgumentParser(description="受控写章节草稿")
    ap.add_argument("--chapter", required=True, help="章节标识，如 CH-001")
    ap.add_argument("--task-id", required=True, help="关联任务 ID")
    ap.add_argument("--role", default="writer")
    ap.add_argument("--project", required=True)
    ap.add_argument("--content-file", required=True,
                    help="含章节正文的临时文件路径")
    args = ap.parse_args()

    # delegate to controlled_write.py
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

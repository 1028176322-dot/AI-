#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chapter_write — strict-v2 经独立 Broker 写草稿；legacy 兼容旧入口。

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
for _child in os.listdir(SCRIPTS_ROOT):
    _path = os.path.join(SCRIPTS_ROOT, _child)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

import project_layout
from controlled_chapter_client import broker_write, resource


def target_for(project, chapter):
    """Return the governed draft target for the current project generation."""
    extension = ".txt" if project_layout.is_style_strict(project) else ".md"
    return "chapters/drafts/%s%s" % (chapter, extension)


def write_chapter(project, chapter, task_id, role, content_file):
    """Validate and write one already-authored draft through the governed path."""
    target = target_for(project, chapter)
    if project_layout.is_style_strict(project):
        with open(content_file, "r", encoding="utf-8") as stream:
            content = stream.read()
        # Word-budget hard gate: fail-closed before broker write.
        try:
            from word_budget_gate import enforce_word_budget
        except Exception as exc:
            raise RuntimeError(
                "word_budget_gate module unavailable: %s" % exc)
        plan_path = os.path.join(
            project, "sources", "outline", "chapters",
            "PLAN-%s.yaml" % chapter)
        ok, errors = enforce_word_budget(content_file, plan_path)
        if not ok:
            raise ValueError(
                "WORD-BUDGET GATE FAILED: %s" % "; ".join(errors))
        target_abs = os.path.join(project, target)
        result = broker_write(
            project, task_id, "chapter_write",
            [resource("target", target_abs, "absent")], content)
        return {
            "target": target,
            "broker_target": result.get("target"),
            "mode": "strict-v2",
        }

    # Existing projects retain the legacy governed writer until migrated.
    controlled_write = os.path.join(
        os.path.dirname(HERE), "tasks", "controlled_write.py")
    command = [
        sys.executable or "python", controlled_write,
        "--role", role,
        "--target", target,
        "--project", project,
        "--content-file", content_file,
        "--task-id", task_id,
    ]
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "legacy controlled write failed: exit=%d"
            % completed.returncode)
    return {"target": target, "mode": "legacy"}


def main():
    ap = argparse.ArgumentParser(description="受控写章节草稿")
    ap.add_argument("--chapter", required=True, help="章节标识，如 CH-001")
    ap.add_argument("--task-id", required=True, help="关联任务 ID")
    ap.add_argument("--role", default="writer")
    ap.add_argument("--project", required=True)
    ap.add_argument("--content-file", required=True,
                    help="含章节正文的临时文件路径")
    args = ap.parse_args()

    try:
        result = write_chapter(
            args.project, args.chapter, args.task_id,
            args.role, args.content_file)
    except (OSError, RuntimeError, ValueError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        sys.exit(2)
    print("CHAPTER WROTE: %s" % result["target"])


if __name__ == "__main__":
    main()

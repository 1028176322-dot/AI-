# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest
from unittest import mock


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for child in os.listdir(os.path.join(PLATFORM_ROOT, "scripts")):
    path = os.path.join(PLATFORM_ROOT, "scripts", child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import chapter_write


class ChapterPlanResolutionTest(unittest.TestCase):
    def test_chapter_id_uses_numeric_canonical_plan(self):
        root = tempfile.mkdtemp(prefix="chapter_plan_")
        with mock.patch.object(
                chapter_write.task_engine, "load_task",
                return_value=(None, None)):
            path = chapter_write.resolve_plan_path(
                root, "CH-202", "TASK-202")
        self.assertEqual(
            os.path.join(
                root, "sources", "outline", "chapters",
                "PLAN-202.yaml"),
            path)

    def test_explicit_task_packet_plan_wins(self):
        root = tempfile.mkdtemp(prefix="chapter_plan_input_")
        explicit = os.path.join(root, "custom-plan.yaml")
        with open(explicit, "w", encoding="utf-8") as stream:
            stream.write("word_budget: 2500\n")
        task = {
            "task": {
                "id": "TASK-X",
                "inputs": {
                    "values": {"chapter_plan": "custom-plan.yaml"},
                },
            },
        }
        with mock.patch.object(
                chapter_write.task_engine, "load_task",
                return_value=("running", task)), mock.patch.object(
                    chapter_write.task_packet, "_resolve_input",
                    return_value=(explicit, True)):
            path = chapter_write.resolve_plan_path(
                root, "special-ending", "TASK-X")
        self.assertEqual(explicit, path)


if __name__ == "__main__":
    unittest.main(verbosity=2)

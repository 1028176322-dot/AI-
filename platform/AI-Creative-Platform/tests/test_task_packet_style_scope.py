# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile
import unittest


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for child in os.listdir(os.path.join(PLATFORM_ROOT, "scripts")):
    path = os.path.join(PLATFORM_ROOT, "scripts", child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import _gov
import task_packet


class TaskPacketStyleScopeTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="task_packet_scope_")
        os.makedirs(os.path.join(
            self.root, "sources", "outline", "chapters"),
            exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_scope_is_derived_from_all_plan_scenes(self):
        _gov.dump_yaml(os.path.join(
            self.root, "sources", "outline", "chapters",
            "PLAN-202.yaml"), {
                "scenes": [
                    {
                        "type": "battle",
                        "participants": ["C-A", "C-B"],
                    },
                    {
                        "type": "revelation",
                        "participants": [
                            {"character_id": "C-C"},
                        ],
                    },
                ],
            })
        task = {
            "id": "T-WRITE-202",
            "chapter_ref": "chapters/drafts/CH-202.txt",
            "inputs": {
                "values": {
                    "scene_types": ["transition"],
                    "character_ids": ["C-EXPLICIT"],
                },
            },
        }
        scenes, characters = task_packet._style_scope_from_plan(
            self.root, task)
        self.assertEqual(
            scenes, ["battle", "revelation", "transition"])
        self.assertEqual(
            characters, ["C-A", "C-B", "C-C", "C-EXPLICIT"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

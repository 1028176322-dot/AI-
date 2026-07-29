# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_ROOT = os.path.join(PLATFORM_ROOT, "scripts")
for child in os.listdir(SCRIPTS_ROOT):
    path = os.path.join(SCRIPTS_ROOT, child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import _gov
import style_orchestrator
import task_engine


class ApprovedEventLineageTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="approved-event-")
        os.makedirs(
            os.path.join(self.root, "tasks", "completed"),
            exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _task(self, task):
        task = dict(task)
        task["status"] = "completed"
        _gov.dump_yaml(os.path.join(
            self.root, "tasks", "completed",
            task["id"] + ".yaml"), {"task": task})

    def test_resolves_approved_chapter_review_through_lineage(self):
        review = {
            "id": "TASK-REVIEW-001",
            "type": "chapter_review",
            "dependencies": [],
            "style_event_history": [{"event": "on_pass"}],
        }
        manifest = {
            "id": "TASK-MANIFEST-001",
            "type": "protected-manifest-build",
            "dependencies": [review["id"]],
        }
        self._task(review)
        self._task(manifest)
        final = {
            "id": "TASK-FINAL-001",
            "type": "final-regression",
            "dependencies": [manifest["id"]],
        }
        self.assertEqual(
            review["id"],
            style_orchestrator._approved_review_event(
                self.root, final))

    def test_unapproved_review_is_not_accepted(self):
        review = {
            "id": "TASK-REVIEW-002",
            "type": "chapter_review",
            "dependencies": [],
            "style_event_history": [{"event": "on_fail"}],
        }
        self._task(review)
        final = {
            "id": "TASK-FINAL-002",
            "type": "final-regression",
            "dependencies": [review["id"]],
        }
        self.assertIsNone(
            style_orchestrator._approved_review_event(
                self.root, final))

    def test_nkb_sync_successor_rebinds_final_snapshot(self):
        source = {
            "id": "TASK-NKB-SYNC-001",
            "type": "nkb_sync",
            "project": "demo",
            "chapter_ref": "CH-001",
            "dependencies": [],
            "inputs": {"values": {
                "chapter_draft": "chapters/drafts/CH-001.txt",
                "nkb_snapshot_after": "NKB/manifest.yaml",
                "outline": "sources/outline/chapters/PLAN-001.yaml",
            }},
        }
        created = []

        def capture(_root, task, model=None, author=None):
            created.append(task)
            return task["id"]

        with mock.patch.object(
                task_engine, "load_task", return_value=(None, None)), \
                mock.patch.object(
                    task_engine, "create_task", side_effect=capture):
            successors = style_orchestrator._create_successors(
                self.root, source, "on_pass", {}, {}, {},
                "reviewer", "model")
        self.assertEqual(1, len(successors))
        values = created[0]["inputs"]["values"]
        self.assertTrue(values["post_nkb_sync"])
        self.assertEqual(
            "NKB/manifest.yaml", values["nkb_snapshot"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

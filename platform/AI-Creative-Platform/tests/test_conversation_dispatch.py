# -*- coding: utf-8 -*-
"""Deterministic tests for conversation-to-task governance."""
import os
import shutil
import sys
import tempfile
import unittest


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_ROOT = os.path.join(PLATFORM_ROOT, "scripts")
for child in os.listdir(SCRIPTS_ROOT):
    path = os.path.join(SCRIPTS_ROOT, child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import _gov
import conversation_dispatch
import project_layout
import status_update
import task_engine


class ConversationDispatchTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="conversation_dispatch_")
        project_layout.scaffold_layout(self.root, "xuanhuan")
        with open(os.path.join(
                self.root, "sources", "outline", "main.md"),
                "w", encoding="utf-8") as stream:
            stream.write("# 主线\n从山门出发。\n")
        status_update.init(self.root, project_id="dispatch-test", stage="writing")
        session_dir = os.path.join(
            self.root, "runtime", "sessions", "SESSION-DISPATCH")
        os.makedirs(session_dir, exist_ok=True)
        _gov.dump_yaml(os.path.join(
            session_dir, "SESSION_MANIFEST.yaml"), {
                "session": {"id": "SESSION-DISPATCH"},
                "project": {"id": "dispatch-test"},
                "ready": True,
            })

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_write_count_means_next_n_chapters(self):
        plan = conversation_dispatch.parse_request("写10章", self.root)
        self.assertEqual(plan["selection"], "count_from_next")
        self.assertEqual(plan["chapters"], list(range(1, 11)))

        approved = os.path.join(
            self.root, "chapters", "approved", "CH-010.md")
        with open(approved, "w", encoding="utf-8") as stream:
            stream.write("# 第十章 旧章\n")
        next_plan = conversation_dispatch.parse_request("续写两章", self.root)
        self.assertEqual(next_plan["chapters"], [11, 12])

    def test_explicit_review_range_is_preserved(self):
        plan = conversation_dispatch.parse_request(
            "审查第3到8章", self.root)
        self.assertEqual(plan["action"], "review_only")
        self.assertEqual(plan["selection"], "explicit_range")
        self.assertEqual(plan["chapters"], [3, 4, 5, 6, 7, 8])

    def test_explicit_single_keeps_legacy_governed_intake(self):
        self.assertFalse(conversation_dispatch.looks_like_chapter_request(
            "写第99章 测试章节"))
        self.assertTrue(conversation_dispatch.looks_like_chapter_request(
            "写10章"))

    def test_dispatch_creates_serial_tasks_and_packets(self):
        plan = conversation_dispatch.dispatch(
            self.root, "写两章并审查", "dispatch-test",
            author="test", model="test")
        task_ids = [item["task_id"] for item in plan["created_tasks"]]
        self.assertEqual(len(task_ids), 2)
        self.assertEqual(task_engine.load_task(self.root, task_ids[0])[0], "ready")
        self.assertEqual(task_engine.load_task(self.root, task_ids[1])[0], "backlog")
        request_id = plan["request_id"]
        expected_publish = "%s-PUBLISH-CH001" % request_id
        self.assertEqual(
            plan["created_tasks"][0]["predicted_pipeline"]["clean"][-1],
            expected_publish)
        _, second = task_engine.load_task(self.root, task_ids[1])
        self.assertEqual(
            second["task"]["dependencies"], [expected_publish])
        for task_id in task_ids:
            packet = os.path.join(
                self.root, "runtime", "task-packets", task_id)
            self.assertTrue(os.path.isfile(os.path.join(packet, "task.yaml")))
            self.assertTrue(os.path.isfile(os.path.join(
                packet, "execution-manifest.yaml")))

    def test_stable_publish_id_ignores_style_route_shape(self):
        task = {
            "id": "DYNAMIC-ROUTE-NODE",
            "conversation_request_id": "REQ-20260729-ABC",
            "chapter_ref": "chapters/drafts/CH-202.txt",
        }
        self.assertEqual(
            task_engine.stable_publish_task_id(task),
            "REQ-20260729-ABC-PUBLISH-CH202")

    def test_dry_run_does_not_mutate_project(self):
        plan = conversation_dispatch.dispatch(
            self.root, "写三章", "dispatch-test", write=False)
        self.assertEqual(plan["chapters"], [1, 2, 3])
        self.assertFalse(os.listdir(os.path.join(self.root, "tasks", "ready")))
        self.assertFalse(os.listdir(os.path.join(self.root, "tasks", "backlog")))


if __name__ == "__main__":
    unittest.main(verbosity=2)

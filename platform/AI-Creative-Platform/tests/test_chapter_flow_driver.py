# -*- coding: utf-8 -*-
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_ROOT = os.path.join(PLATFORM_ROOT, "scripts")
if SCRIPTS_ROOT not in sys.path:
    sys.path.insert(0, SCRIPTS_ROOT)
for child in os.listdir(SCRIPTS_ROOT):
    path = os.path.join(SCRIPTS_ROOT, child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import _gov
import chapter_pipeline_driver as driver
import project_layout
import task_templates


class ChapterFlowDriverTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="chapter_flow_")
        os.makedirs(os.path.join(self.root, "tasks", "ready"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _task(self, task_id, chapter_ref="", title=""):
        path = os.path.join(
            self.root, "tasks", "ready", "%s.yaml" % task_id)
        _gov.dump_yaml(path, {
            "task": {
                "id": task_id,
                "type": "chapter_write",
                "chapter_ref": chapter_ref,
                "title": title,
            },
        })

    def test_task_match_does_not_treat_request_date_as_chapter(self):
        task = {
            "id": "TASK-INTAKE-20260729-001",
            "title": "普通请求",
        }
        self.assertFalse(driver._task_matches(task, "CH-202"))
        task["chapter_ref"] = "chapters/drafts/CH-202.md"
        self.assertTrue(driver._task_matches(task, "CH-202"))

    def test_status_reports_the_real_frontier(self):
        self._task(
            "TASK-WRITE-CH202", chapter_ref="CH-202",
            title="第202章撰写")
        result = driver.status(self.root, "202")
        self.assertEqual("CH-202", result["chapter_id"])
        self.assertEqual("ready", result["frontier"]["state"])
        self.assertEqual(
            "TASK-WRITE-CH202", result["frontier"]["task_id"])

    def test_cli_status_is_registered_as_single_entry(self):
        self._task("TASK-WRITE-CH009", chapter_ref="CH-009")
        command = [
            sys.executable,
            os.path.join(PLATFORM_ROOT, "cli", "platform.py"),
            "chapter-flow", "status",
            "--project-root", self.root,
            "--chapter", "9",
        ]
        completed = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(0, completed.returncode, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual("CH-009", result["chapter_id"])

    def test_post_nkb_tail_rebinds_before_publish(self):
        self.assertEqual(
            ["protected-manifest-build"],
            task_templates.next_types("nkb_sync", "on_pass"))
        self.assertEqual(
            ["chapter_publish"],
            task_templates.next_types(
                "final-regression", "on_pass_post_nkb"))

    def test_new_project_agents_enforces_chapter_flow(self):
        project_root = os.path.join(self.root, "new-project")
        project_layout.scaffold_layout(project_root, "xuanhuan")
        with open(
                os.path.join(project_root, "AGENTS.md"),
                "r", encoding="utf-8") as stream:
            agents = stream.read()
        self.assertIn("platform chapter-flow run/status", agents)

    def test_publish_without_outline_refresh_is_not_complete(self):
        _gov.dump_yaml(os.path.join(self.root, "PROJECT_LAYOUT.yaml"), {
            "style_system": {
                "enabled": True,
                "enforcement_profile": "strict-v2",
                "full_chapter_chain_required": True,
            },
        })
        completed_dir = os.path.join(self.root, "tasks", "completed")
        os.makedirs(completed_dir)
        _gov.dump_yaml(os.path.join(
            completed_dir, "TASK-PUBLISH-CH001.yaml"), {
                "task": {
                    "id": "TASK-PUBLISH-CH001",
                    "type": "chapter_publish",
                    "chapter_ref": "CH-001",
                },
            })
        with self.assertRaises(driver.FlowBlocked) as raised:
            driver.run_flow(
                self.root, "CH-001", "tester", None, max_steps=1)
        self.assertEqual(
            "OUTLINE_REFRESH_INCOMPLETE", raised.exception.code)


if __name__ == "__main__":
    unittest.main(verbosity=2)

# -*- coding: utf-8 -*-
import datetime
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
import auth_engine
import task_engine


class PublishGrantTtlTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="publish_grant_")
        auth_engine._CACHE.clear()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _seconds(self, grant):
        generated = datetime.datetime.fromisoformat(
            grant["generated_at"])
        expires = datetime.datetime.fromisoformat(
            grant["expires_at"])
        return int((expires - generated).total_seconds())

    def test_default_grant_ttl_is_24_hours(self):
        auth_engine.generate_grant(
            self.root, "TASK-PUBLISH", "publish_service",
            "chapter.publish", "canonical",
            ["chapters/approved/CH-202.txt"])
        grant = auth_engine.read_grant(
            self.root, "TASK-PUBLISH")
        self.assertEqual(86400, self._seconds(grant))

    def test_live_publish_task_can_renew_exact_target(self):
        task_dir = os.path.join(self.root, "tasks", "running")
        os.makedirs(task_dir, exist_ok=True)
        _gov.dump_yaml(os.path.join(task_dir, "TASK-PUBLISH.yaml"), {
            "task": {
                "id": "TASK-PUBLISH",
                "type": "chapter_publish",
                "status": "running",
                "owner": "publish_service",
                "publish_target": "chapters/approved/CH-202.txt",
                "agent": {"required_role": "publish_service"},
            },
        })
        task_engine.renew_publish_grant(
            self.root, "TASK-PUBLISH",
            "chapters/approved/CH-202.txt")
        grant = auth_engine.read_grant(
            self.root, "TASK-PUBLISH")
        self.assertEqual(
            ["chapters/approved/CH-202.txt"],
            grant["targets"])
        self.assertEqual(86400, self._seconds(grant))

    def test_renewal_rejects_target_substitution(self):
        task_dir = os.path.join(self.root, "tasks", "running")
        os.makedirs(task_dir, exist_ok=True)
        _gov.dump_yaml(os.path.join(task_dir, "TASK-PUBLISH.yaml"), {
            "task": {
                "id": "TASK-PUBLISH",
                "type": "chapter_publish",
                "status": "running",
                "publish_target": "chapters/approved/CH-202.txt",
                "agent": {"required_role": "publish_service"},
            },
        })
        with self.assertRaisesRegex(
                ValueError, "target mismatch"):
            task_engine.renew_publish_grant(
                self.root, "TASK-PUBLISH",
                "chapters/approved/CH-999.txt")


if __name__ == "__main__":
    unittest.main(verbosity=2)

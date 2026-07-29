# -*- coding: utf-8 -*-
import os
import subprocess
import sys
import tempfile
import unittest


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(PLATFORM_ROOT, "cli", "platform.py")


class TaskFacadeRoutingTest(unittest.TestCase):
    def _run(self, *arguments):
        with tempfile.TemporaryDirectory(
                prefix="task-facade-") as project_root:
            return subprocess.run(
                [sys.executable, CLI, "task"] + [
                    value.replace("<ROOT>", project_root)
                    for value in arguments
                ],
                cwd=PLATFORM_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

    def test_project_root_after_verb(self):
        completed = self._run(
            "list", "--project-root", "<ROOT>")
        self.assertEqual(
            0, completed.returncode,
            completed.stdout + completed.stderr)

    def test_project_root_before_verb(self):
        completed = self._run(
            "--project-root", "<ROOT>", "list")
        self.assertEqual(
            0, completed.returncode,
            completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)

# -*- coding: utf-8 -*-
"""Workspace/project-registry path resolution regression tests."""
import os
import sys
import tempfile
import unittest
from unittest import mock


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for rel in ("scripts/_common", "scripts/platform"):
    path = os.path.join(PLATFORM_ROOT, rel)
    if path not in sys.path:
        sys.path.insert(0, path)

import platform_selfcheck  # noqa: E402


class PlatformSelfcheckWorkspacePathsTest(unittest.TestCase):
    def test_entry_is_resolved_from_explicit_manifest_base(self):
        with tempfile.TemporaryDirectory() as workspace:
            platform_dir = os.path.join(
                workspace, "platform", "AI-Creative-Platform")
            manifest = os.path.join(
                platform_dir, "registry", "projects.yaml")
            os.makedirs(os.path.dirname(manifest))
            expected = os.path.join(workspace, "projects", "demo")
            os.makedirs(expected)

            actual = platform_selfcheck._resolve_manifest_entry(
                manifest, "../../projects/demo", workspace,
                base_dir=platform_dir)

            self.assertEqual(
                os.path.normcase(os.path.realpath(expected)),
                os.path.normcase(actual))

    def test_workspace_roots_do_not_depend_on_current_directory(self):
        with tempfile.TemporaryDirectory() as workspace:
            project = os.path.join(workspace, "projects", "demo")
            os.makedirs(project)
            manifest = os.path.join(workspace, "workspace.yaml")
            with open(manifest, "w", encoding="utf-8") as stream:
                stream.write(
                    "workspace:\n"
                    "  projects:\n"
                    "    - ./projects/demo\n")
            previous = os.getcwd()
            try:
                os.chdir(os.path.dirname(workspace))
                roots = platform_selfcheck._workspace_project_roots(
                    workspace)
            finally:
                os.chdir(previous)

            self.assertEqual(
                [os.path.normcase(os.path.realpath(project))],
                [os.path.normcase(path) for path in roots])

    def test_absolute_and_workspace_escape_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as workspace:
            manifest = os.path.join(workspace, "workspace.yaml")
            with self.assertRaisesRegex(ValueError, "相对路径"):
                platform_selfcheck._resolve_manifest_entry(
                    manifest, os.path.abspath(os.sep), workspace)
            with self.assertRaisesRegex(ValueError, "越出工作区"):
                platform_selfcheck._resolve_manifest_entry(
                    manifest, "../outside", workspace)

    def test_access_error_is_not_reported_as_missing(self):
        with mock.patch.object(
                platform_selfcheck.os, "stat",
                side_effect=PermissionError("denied")):
            is_directory, error = platform_selfcheck._directory_state(
                "unreadable")

        self.assertIsNone(is_directory)
        self.assertIn("denied", error)


if __name__ == "__main__":
    unittest.main()

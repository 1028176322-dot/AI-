# -*- coding: utf-8 -*-
import os
import unittest


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(PLATFORM_ROOT))


def read_text(*parts):
    path = os.path.join(*parts)
    with open(path, "r", encoding="utf-8-sig") as stream:
        return stream.read()


class GitCoordinatorEntrypointTest(unittest.TestCase):
    def test_workspace_and_platform_point_to_single_authority(self):
        workspace_agents = read_text(WORKSPACE_ROOT, "AGENTS.md")
        platform_manifest = read_text(PLATFORM_ROOT, "platform.yaml")
        platform_agents = read_text(PLATFORM_ROOT, "AGENTS.md")
        core_manifest = read_text(
            PLATFORM_ROOT, "core", "core.yaml")

        marker = "governance.git_coordination"
        self.assertIn(marker, workspace_agents)
        self.assertIn(
            "git_coordination: core/governance/Git协调者唯一入口.md",
            platform_manifest)
        self.assertIn(
            "git_scope_policy: core/governance/git-scopes.json",
            platform_manifest)
        self.assertIn(marker, platform_agents)
        self.assertIn("origin/main", platform_agents)
        self.assertIn("platform git status/sync/commit/publish", platform_agents)
        self.assertIn("governance:", core_manifest)

    def test_authority_defines_single_main_and_project_scopes(self):
        authority = read_text(
            PLATFORM_ROOT, "core", "governance",
            "Git协调者唯一入口.md")

        for marker in (
                "# Git 单 main 项目权限唯一入口",
                "origin/main",
                "platform git status/sync/commit/publish",
                "git-scopes.json",
                "同一设备的并发对话使用独立 worktree",
                "projects/<project-id>/**",
                "PATH_SCOPE_VIOLATION",
                "REMOTE_CAS_REJECTED",
                "force push / force-with-lease",
                "服务器级硬阻断",
                "## 15. 首次启用",
                "自举例外立即且永久失效"):
            self.assertIn(marker, authority)

    def test_worktree_guide_only_authorizes_local_isolation(self):
        guide = read_text(
            PLATFORM_ROOT, "core", "governance",
            "AI共享Git工作区指南.md")

        self.assertIn("Git协调者唯一入口.md", guide)
        self.assertIn("git-scopes.json", guide)
        self.assertIn("origin/main", guide)
        self.assertIn("旧的 `Pull` 和 `Push` 参数", guide)
        self.assertIn("fail-closed", guide)
        self.assertIn("platform git publish", guide)
        self.assertNotIn(
            "codex-<agent-id>-<project-id>-<task-id>-<short-sha>",
            guide)
        self.assertNotIn("每任务唯一", guide)
        self.assertNotIn("-Action Pull", guide)
        self.assertNotIn("-Action Push", guide)

    def test_new_projects_inherit_git_scope_boundary(self):
        generator = read_text(
            PLATFORM_ROOT, "scripts", "project", "project_layout.py")

        self.assertIn("governance.git_coordination", generator)
        self.assertIn("所有对话只发布远端 main", generator)
        self.assertIn(
            "platform git status/sync/commit/publish",
            generator)
        self.assertIn("权限表登记的负责项目路径", generator)

    def test_existing_project_has_narrow_scope(self):
        agents = read_text(
            WORKSPACE_ROOT, "projects", "dushi-jishi", "AGENTS.md")

        self.assertIn("platform git status/sync/commit/publish", agents)
        self.assertIn("projects/dushi-jishi/**", agents)
        self.assertIn("其他项目和平台内容只有读取、同步和使用权限", agents)


if __name__ == "__main__":
    unittest.main(verbosity=2)

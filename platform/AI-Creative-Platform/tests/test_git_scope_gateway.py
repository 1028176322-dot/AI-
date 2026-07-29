import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATEWAY = os.path.join(
    PLATFORM_ROOT, "scripts", "git", "git_scope_gateway.py")
POLICY = os.path.join(
    PLATFORM_ROOT, "core", "governance", "git-scopes.json")


def run(command, cwd=None, env=None, check=True):
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and completed.returncode:
        raise AssertionError(
            "command failed: %r\nstdout=%s\nstderr=%s" % (
                command, completed.stdout, completed.stderr))
    return completed


class GitScopeGatewayTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="git-scope-gateway-")
        self.remote = os.path.join(self.temp, "remote.git")
        self.seed = os.path.join(self.temp, "seed")
        self.writer = os.path.join(self.temp, "writer")
        self.audit = os.path.join(self.temp, "audit")

        run(["git", "init", "--bare", self.remote])
        run(["git", "init", self.seed])
        run(["git", "config", "user.name", "Gateway Test"], cwd=self.seed)
        run(
            ["git", "config", "user.email", "gateway@example.invalid"],
            cwd=self.seed)

        policy_target = os.path.join(
            self.seed, "platform", "AI-Creative-Platform",
            "core", "governance", "git-scopes.json")
        os.makedirs(os.path.dirname(policy_target), exist_ok=True)
        shutil.copyfile(POLICY, policy_target)
        platform_file = os.path.join(
            self.seed, "platform", "AI-Creative-Platform", "README.md")
        os.makedirs(os.path.dirname(platform_file), exist_ok=True)
        with open(platform_file, "w", encoding="utf-8") as stream:
            stream.write("platform\n")
        project_file = os.path.join(
            self.seed, "projects", "dushi-jishi", "project.txt")
        os.makedirs(os.path.dirname(project_file), exist_ok=True)
        with open(project_file, "w", encoding="utf-8") as stream:
            stream.write("base\n")
        task_root = os.path.join(
            self.seed, "projects", "dushi-jishi", "tasks", "completed")
        os.makedirs(task_root, exist_ok=True)
        for number in range(1, 6):
            task_id = "TASK-TEST-%03d" % number
            with open(
                    os.path.join(task_root, task_id + ".yaml"),
                    "w", encoding="utf-8") as stream:
                stream.write("id: %s\nstatus: completed\n" % task_id)
        daofa_file = os.path.join(
            self.seed, "projects", "道法百年", "project.txt")
        os.makedirs(os.path.dirname(daofa_file), exist_ok=True)
        with open(daofa_file, "w", encoding="utf-8") as stream:
            stream.write("base\n")
        daofa_task_root = os.path.join(
            self.seed, "projects", "道法百年", "tasks", "completed")
        os.makedirs(daofa_task_root, exist_ok=True)
        with open(
                os.path.join(daofa_task_root, "TASK-DSF-001.yaml"),
                "w", encoding="utf-8") as stream:
            stream.write("id: TASK-DSF-001\nstatus: completed\n")

        run(["git", "add", "-A"], cwd=self.seed)
        run(["git", "commit", "-m", "seed"], cwd=self.seed)
        run(["git", "branch", "-M", "main"], cwd=self.seed)
        run(["git", "remote", "add", "origin", self.remote], cwd=self.seed)
        run(["git", "push", "origin", "main"], cwd=self.seed)
        run(
            ["git", "symbolic-ref", "HEAD", "refs/heads/main"],
            cwd=self.remote)
        run(["git", "clone", self.remote, self.writer])
        run(["git", "config", "user.name", "Writer A"], cwd=self.writer)
        run(
            ["git", "config", "user.email", "writer@example.invalid"],
            cwd=self.writer)
        self.environment = os.environ.copy()
        self.environment["ACP_GIT_AUDIT_DIR"] = self.audit

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def gateway(self, *arguments, check=True):
        completed = run(
            [sys.executable, GATEWAY] + list(arguments),
            cwd=self.writer,
            env=self.environment,
            check=False,
        )
        try:
            body = json.loads(completed.stdout)
        except ValueError:
            self.fail(
                "gateway did not return JSON\nstdout=%s\nstderr=%s" % (
                    completed.stdout, completed.stderr))
        if check and completed.returncode:
            self.fail("gateway blocked unexpectedly: %r" % body)
        return completed, body

    def test_project_writer_can_commit_and_publish_only_own_project(self):
        path = os.path.join(
            self.writer, "projects", "dushi-jishi", "project.txt")
        with open(path, "a", encoding="utf-8") as stream:
            stream.write("writer change\n")

        _, commit = self.gateway(
            "commit", "--actor-id", "writer-a",
            "--task-id", "TASK-TEST-001",
            "--message", "test: project change",
            "--path", "projects/dushi-jishi/project.txt")
        self.assertEqual("ALLOW", commit["decision"])
        self.assertEqual(
            ["projects/dushi-jishi/project.txt"], commit["paths"])

        _, publish = self.gateway(
            "publish", "--actor-id", "writer-a",
            "--task-id", "TASK-TEST-001")
        self.assertEqual("ALLOW", publish["decision"])
        remote_tip = run(
            ["git", "ls-remote", self.remote, "refs/heads/main"],
            cwd=self.writer).stdout.split()[0]
        self.assertEqual(commit["commit"], remote_tip)

    def test_project_writer_cannot_commit_platform_path(self):
        path = os.path.join(
            self.writer, "platform", "AI-Creative-Platform", "README.md")
        with open(path, "a", encoding="utf-8") as stream:
            stream.write("unauthorized\n")

        completed, body = self.gateway(
            "commit", "--actor-id", "writer-a",
            "--task-id", "TASK-TEST-002",
            "--message", "bad",
            "--path", "platform/AI-Creative-Platform/README.md",
            check=False)
        self.assertNotEqual(0, completed.returncode)
        self.assertEqual("PATH_SCOPE_VIOLATION", body["code"])

    def test_publish_rechecks_every_commit_path(self):
        path = os.path.join(
            self.writer, "platform", "AI-Creative-Platform", "README.md")
        with open(path, "a", encoding="utf-8") as stream:
            stream.write("raw git bypass attempt\n")
        run(["git", "add", "--", "platform/AI-Creative-Platform/README.md"],
            cwd=self.writer)
        run(["git", "commit", "-m", "raw bypass"], cwd=self.writer)

        completed, body = self.gateway(
            "publish", "--actor-id", "writer-a",
            "--task-id", "TASK-TEST-003",
            check=False)
        self.assertNotEqual(0, completed.returncode)
        self.assertEqual("PATH_SCOPE_VIOLATION", body["code"])

    def test_read_only_actor_cannot_commit_or_publish(self):
        path = os.path.join(
            self.writer, "projects", "dushi-jishi", "project.txt")
        with open(path, "a", encoding="utf-8") as stream:
            stream.write("read-only attempt\n")
        completed, body = self.gateway(
            "commit", "--actor-id", "read-only",
            "--message", "bad",
            "--path", "projects/dushi-jishi/project.txt",
            check=False)
        self.assertNotEqual(0, completed.returncode)
        self.assertEqual("ACTION_NOT_AUTHORIZED", body["code"])

    def test_sync_refuses_dirty_worktree(self):
        path = os.path.join(
            self.writer, "projects", "dushi-jishi", "project.txt")
        with open(path, "a", encoding="utf-8") as stream:
            stream.write("dirty\n")
        completed, body = self.gateway(
            "sync", "--actor-id", "writer-a", check=False)
        self.assertNotEqual(0, completed.returncode)
        self.assertEqual("DIRTY_WORKTREE", body["code"])

    def test_sync_rebases_non_overlapping_scoped_commit(self):
        writer_path = os.path.join(
            self.writer, "projects", "dushi-jishi", "project.txt")
        with open(writer_path, "a", encoding="utf-8") as stream:
            stream.write("local project change\n")
        self.gateway(
            "commit", "--actor-id", "writer-a",
            "--task-id", "TASK-TEST-004",
            "--message", "test: local scoped commit",
            "--path", "projects/dushi-jishi/project.txt")
        old_writer_head = run(
            ["git", "rev-parse", "HEAD"], cwd=self.writer).stdout.strip()

        incoming_path = os.path.join(
            self.seed, "projects", "another-project", "incoming.txt")
        os.makedirs(os.path.dirname(incoming_path), exist_ok=True)
        with open(incoming_path, "w", encoding="utf-8") as stream:
            stream.write("independent remote change\n")
        run(["git", "add", "-A"], cwd=self.seed)
        run(["git", "commit", "-m", "remote: other project"], cwd=self.seed)
        run(["git", "push", "origin", "main"], cwd=self.seed)

        _, sync = self.gateway(
            "sync", "--actor-id", "writer-a")
        self.assertEqual("SCOPED_REBASED", sync["state"])
        new_writer_head = run(
            ["git", "rev-parse", "HEAD"], cwd=self.writer).stdout.strip()
        self.assertNotEqual(old_writer_head, new_writer_head)

        _, publish = self.gateway(
            "publish", "--actor-id", "writer-a",
            "--task-id", "TASK-TEST-004")
        self.assertEqual("ALLOW", publish["decision"])

    def test_path_traversal_is_rejected(self):
        writer_path = os.path.join(
            self.writer, "projects", "dushi-jishi", "project.txt")
        with open(writer_path, "a", encoding="utf-8") as stream:
            stream.write("dirty before invalid path\n")
        completed, body = self.gateway(
            "commit", "--actor-id", "writer-a",
            "--task-id", "TASK-TEST-005",
            "--message", "bad path",
            "--path", "projects/dushi-jishi/../../platform",
            check=False)
        self.assertNotEqual(0, completed.returncode)
        self.assertEqual("PATH_INVALID", body["code"])

    def test_fake_task_id_is_rejected(self):
        writer_path = os.path.join(
            self.writer, "projects", "dushi-jishi", "project.txt")
        with open(writer_path, "a", encoding="utf-8") as stream:
            stream.write("change with fake task\n")
        completed, body = self.gateway(
            "commit", "--actor-id", "writer-a",
            "--task-id", "TASK-NOT-REAL",
            "--message", "bad task",
            "--path", "projects/dushi-jishi/project.txt",
            check=False)
        self.assertNotEqual(0, completed.returncode)
        self.assertEqual("TASK_NOT_FOUND_OR_ELIGIBLE", body["code"])

    def test_local_policy_cannot_redirect_origin(self):
        policy_path = os.path.join(
            self.writer, "platform", "AI-Creative-Platform",
            "core", "governance", "git-scopes.json")
        with open(policy_path, "r", encoding="utf-8") as stream:
            policy = json.load(stream)
        policy["remote"] = "attacker"
        with open(policy_path, "w", encoding="utf-8") as stream:
            json.dump(policy, stream)
        completed, body = self.gateway(
            "status", "--actor-id", "writer-a", check=False)
        self.assertNotEqual(0, completed.returncode)
        self.assertEqual("POLICY_REMOTE_INVALID", body["code"])

    def test_second_project_writer_can_commit_unicode_project_path(self):
        project_path = os.path.join(
            self.writer, "projects", "道法百年", "project.txt")
        with open(project_path, "a", encoding="utf-8") as stream:
            stream.write("道法项目修改\n")
        _, body = self.gateway(
            "commit", "--actor-id", "writer-novel-dsf",
            "--task-id", "TASK-DSF-001",
            "--message", "test: daofa project",
            "--path", "projects/道法百年/project.txt")
        self.assertEqual("ALLOW", body["decision"])
        self.assertEqual(
            ["projects/道法百年/project.txt"], body["paths"])

    def test_second_project_writer_cannot_commit_dushi(self):
        project_path = os.path.join(
            self.writer, "projects", "dushi-jishi", "project.txt")
        with open(project_path, "a", encoding="utf-8") as stream:
            stream.write("wrong project\n")
        completed, body = self.gateway(
            "commit", "--actor-id", "writer-novel-dsf",
            "--task-id", "TASK-DSF-001",
            "--message", "bad project",
            "--path", "projects/dushi-jishi/project.txt",
            check=False)
        self.assertNotEqual(0, completed.returncode)
        self.assertEqual("PATH_SCOPE_VIOLATION", body["code"])


if __name__ == "__main__":
    unittest.main()

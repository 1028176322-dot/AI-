# -*- coding: utf-8 -*-
import os
import subprocess
import unittest


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(
    PLATFORM_ROOT, "scripts", "git", "ai_git_worktree.ps1")


class GitWorktreeManagerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SCRIPT, "r", encoding="utf-8") as stream:
            cls.source = stream.read()

    def test_powershell_syntax_is_valid(self):
        command = (
            "$errors=$null; "
            "[void][System.Management.Automation.Language.Parser]::"
            "ParseFile($env:AI_GIT_SCRIPT_UNDER_TEST,"
            "[ref]$null,[ref]$errors); "
            "if($errors.Count){$errors|ForEach-Object{Write-Error $_};"
            "exit 1}")
        environment = os.environ.copy()
        environment["AI_GIT_SCRIPT_UNDER_TEST"] = SCRIPT
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             command],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=False, env=environment)
        self.assertEqual(
            0, completed.returncode,
            completed.stdout + completed.stderr)

    def test_auto_mode_has_verified_flat_fallback(self):
        self.assertIn(
            '[ValidateSet("Auto", "Slash", "Flat")]',
            self.source)
        self.assertIn(
            'return @("codex/$Id", "codex-$Id")',
            self.source)
        self.assertIn(
            '"rev-parse", "--verify", $probeRef',
            self.source)
        self.assertIn(
            "git reported success but ref verification failed",
            self.source)

    def test_all_git_calls_enable_windows_longpaths(self):
        self.assertIn("-c core.longpaths=true", self.source)

    def test_rollback_is_scoped_and_does_not_delete_global_index_lock(self):
        self.assertIn(
            '"update-ref", "-d",\n'
            '                    "refs/heads/$branch", $branchTarget',
            self.source)
        self.assertIn(
            "Repository index.lock was not deleted",
            self.source)
        self.assertNotIn(
            'Remove-Item -Force ".git/index.lock"',
            self.source)

    def test_diagnose_reports_namespace_finding(self):
        self.assertIn(
            "refs/codex/* and refs/heads/codex/* are separate namespaces",
            self.source)
        self.assertIn(
            "packed_codex_namespace_conflict = $false",
            self.source)

    def test_remote_tip_comes_from_ls_remote_and_exact_sha(self):
        self.assertIn(
            '"ls-remote", "--exit-code", "origin", $remoteRef',
            self.source)
        self.assertIn(
            '"cat-file", "-e", "$sha`^{commit}"',
            self.source)
        self.assertIn(
            "$mainRemote = Get-RemoteBranchTip",
            self.source)
        self.assertIn(
            '"merge", "--ff-only", $source',
            self.source)

    def test_push_is_verified_without_remote_tracking_ref_dependency(self):
        self.assertIn(
            "$remoteAfter = Get-RemoteBranchTip",
            self.source)
        self.assertNotIn(
            '"push", "-u", "origin"',
            self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)

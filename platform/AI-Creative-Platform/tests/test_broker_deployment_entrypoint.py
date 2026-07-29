# -*- coding: utf-8 -*-
"""Canonical cross-device Broker deployment entrypoint regression tests."""
import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for child in os.listdir(os.path.join(PLATFORM_ROOT, "scripts")):
    path = os.path.join(PLATFORM_ROOT, "scripts", child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import broker_cli  # noqa: E402
import controlled_chapter_client  # noqa: E402


class BrokerDeploymentEntrypointTest(unittest.TestCase):
    def test_machine_json_is_safe_on_strict_gbk_console(self):
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(
            buffer, encoding="gbk", errors="strict")
        try:
            with mock.patch.object(broker_cli.sys, "stdout", stream):
                broker_cli._emit_json({
                    "acl": "\ufffd",
                    "project": "道法百年",
                }, indent=2)
                stream.flush()
            payload = buffer.getvalue()
        finally:
            stream.detach()
        self.assertIn(b"\\ufffd", payload)
        self.assertIn(b"\\u9053\\u6cd5\\u767e\\u5e74", payload)

    def test_cli_deploy_invokes_only_canonical_script(self):
        arguments = argparse.Namespace(
            mode="Plan",
            project_root=os.path.join(PLATFORM_ROOT, "example-project"),
            auto_elevate=False,
            remove_identities=False,
        )
        completed = mock.Mock(returncode=0)
        with mock.patch.object(
                broker_cli.os, "name", "nt"), mock.patch.object(
                broker_cli.shutil, "which",
                return_value=r"C:\Windows\System32\WindowsPowerShell"
                             r"\v1.0\powershell.exe"), mock.patch.object(
                broker_cli.subprocess, "run",
                return_value=completed) as run, mock.patch.dict(
                broker_cli.os.environ, {
                    "ACP_BROKER_INITIATING_IDENTITY":
                        r"DEVICE\TaskInvoker"}):
            self.assertEqual(broker_cli._deploy(arguments), 0)
        command = run.call_args.args[0]
        self.assertTrue(any(
            value.endswith("deploy_broker_windows.ps1")
            for value in command))
        self.assertIn("-ExecutionPolicy", command)
        self.assertIn("Bypass", command)
        self.assertIn("-Mode", command)
        self.assertIn("Plan", command)
        self.assertIn("-InitiatingIdentity", command)
        self.assertIn(r"DEVICE\TaskInvoker", command)
        self.assertNotIn("sc.exe", command)
        self.assertNotIn("icacls.exe", command)

    def test_non_windows_deployment_fails_closed(self):
        arguments = argparse.Namespace()
        with mock.patch.object(broker_cli.os, "name", "posix"):
            with self.assertRaisesRegex(SystemExit, "Windows.*NTFS"):
                broker_cli._deploy(arguments)

    def test_client_uses_project_status_and_protected_token(self):
        with tempfile.TemporaryDirectory() as root:
            status_dir = os.path.join(root, "runtime", "learning")
            os.makedirs(status_dir)
            with open(
                    os.path.join(status_dir, "broker-status.json"),
                    "w", encoding="utf-8") as stream:
                json.dump({
                    "host": "127.0.0.1",
                    "port": 50123,
                    "client_registry_path":
                        r"SOFTWARE\AI-Creative-Platform\Brokers\ABC12345",
                }, stream)
            clean = {
                key: value for key, value in os.environ.items()
                if key not in (
                    "STYLE_BROKER_HOST", "STYLE_BROKER_PORT",
                    "STYLE_BROKER_CLIENT_TOKEN")
            }
            with mock.patch.dict(os.environ, clean, clear=True), \
                    mock.patch.object(
                        controlled_chapter_client,
                        "_registry_client_token",
                        return_value="device-local-token"):
                self.assertEqual(
                    controlled_chapter_client._endpoint(root),
                    ("127.0.0.1", 50123, "device-local-token"))

    def test_deployment_script_declares_all_governed_modes(self):
        path = os.path.join(
            PLATFORM_ROOT, "scripts", "logs",
            "deploy_broker_windows.ps1")
        with open(path, "r", encoding="utf-8-sig") as stream:
            text = stream.read()
        for marker in (
                'ValidateSet("Plan", "Apply", "Verify", "Rollback")',
                "Write-ClientRegistryConfiguration",
                "Write-VerificationReport",
                "Find-AvailableLoopbackPort",
                "ConvertTo-PowerShellLiteral",
                "-EncodedCommand",
                "-InitiatingIdentity",
                "initiating_identity_read",
                "IsNullOrWhiteSpace($legacyReportedRoot)",
                "Stop-GovernedService",
                "did not reach STOPPED state",
                "AIStyleChapterWriter",
                "Failed to delete governed legacy service",
                "function Remove-LegacyAclEntry",
                "Read-back is authoritative",
                "Test-ExplicitAclEntryPresent",
                "taskrunner_direct_write_denied",
                "taskrunner_direct_delete_denied",
                "DEPLOYED_VERIFIED",
                "ROLLED_BACK"):
            self.assertIn(marker, text)
        self.assertIn("New-Service", text)
        self.assertNotIn("STYLE_WRITER_SERVICE_PASSWORD", text)
        self.assertNotIn("password= $env:", text)


if __name__ == "__main__":
    unittest.main()

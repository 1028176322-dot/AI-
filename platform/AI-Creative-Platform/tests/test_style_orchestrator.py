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
import diagnosis
import style_orchestrator
import task_engine
import task_templates


class StyleOrchestratorTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="style_orchestrator_")
        for state in task_engine.STATES:
            os.makedirs(os.path.join(self.root, "tasks", state),
                        exist_ok=True)
        session_dir = os.path.join(
            self.root, "runtime", "sessions", "S1")
        os.makedirs(session_dir, exist_ok=True)
        _gov.dump_yaml(os.path.join(
            session_dir, "SESSION_MANIFEST.yaml"), {
                "session": {
                    "id": "S1",
                    "loaded": {
                        "constitution": True,
                        "specification": True,
                        "project_yaml": True,
                        "nkb": True,
                        "role_policy": True,
                        "workflow": True,
                    },
                },
            })
        template = task_templates.load("ai-diagnose")
        task = {
            "id": "T-DIAGNOSE",
            "type": "ai-diagnose",
            "project": "P1",
            "chapter_ref": "CH001",
            "owner": "agent-1",
            "lease_expire": (
                datetime.datetime.now()
                + datetime.timedelta(minutes=10)
            ).isoformat(timespec="seconds"),
            "agent": {"required_role": "writer"},
            "execution_policy": template["execution_policy"],
            "permissions": template["permissions"],
            "inputs": {"required": [], "values": {}},
            "status": "running",
        }
        _gov.dump_yaml(os.path.join(
            self.root, "tasks", "running", "T-DIAGNOSE.yaml"), {
                "task": task})
        report = diagnosis.ai_diagnose(
            "CH001", "RC1", "T-DIAGNOSE",
            "沈砚推门入城。", protected_manifest_sha256="m" * 64)
        self.report_path = diagnosis.persist(
            report, self.root, "CH001", "T-DIAGNOSE")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_clean_event_creates_baseline_regression_once(self):
        result = style_orchestrator.finish_with_event(
            self.root, "T-DIAGNOSE", "on_clean",
            {"diagnosis_report": self.report_path},
            checks={"semantic_contract": True},
            actor="agent-1", role="writer")
        self.assertEqual(result["style_state"], "DIAGNOSED_CLEAN")
        self.assertEqual(len(result["successors"]), 1)
        successor = result["successors"][0]
        _, body = task_engine.load_task(self.root, successor)
        values = body["task"]["inputs"]["values"]
        self.assertEqual(values["final_regression_mode"], "baseline")
        replay = style_orchestrator.finish_with_event(
            self.root, "T-DIAGNOSE", "on_clean",
            {"diagnosis_report": self.report_path},
            actor="agent-1", role="writer")
        self.assertTrue(replay["idempotent"])
        self.assertEqual(replay["successors"], [successor])

    def test_undeclared_event_is_rejected(self):
        with self.assertRaisesRegex(
                style_orchestrator.StyleEventError, "not declared"):
            style_orchestrator.finish_with_event(
                self.root, "T-DIAGNOSE", "on_pass",
                {"diagnosis_report": self.report_path},
                actor="agent-1", role="writer")

    def test_all_required_events_have_handlers(self):
        self.assertTrue(
            {
                "on_complete", "on_clean", "on_warning", "on_issues",
                "on_pass", "on_fail", "on_rolled_back", "on_conflict",
                "on_fail_baseline", "on_fail_post_apply",
            }.issubset(style_orchestrator.SUPPORTED_EVENTS))


if __name__ == "__main__":
    unittest.main(verbosity=2)

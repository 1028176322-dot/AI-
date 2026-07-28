# -*- coding: utf-8 -*-
"""Regression coverage for platform-wide integrity and review contracts."""
import os
import shutil
import sys
import tempfile
import unittest


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for rel in ("scripts/_common", "scripts/tasks", "scripts/platform"):
    path = os.path.join(PLATFORM_ROOT, rel)
    if path not in sys.path:
        sys.path.insert(0, path)

import _gov
import platform_selfcheck
import project_template
import review_orchestrator
import task_engine
import task_templates


class PlatformIntegrityTest(unittest.TestCase):

    def test_repository_selfcheck_is_clean(self):
        workspace_root = os.path.dirname(os.path.dirname(PLATFORM_ROOT))
        report = platform_selfcheck.audit(workspace_root)
        self.assertEqual(report["summary"]["decision"], "proceed",
                         report["findings"])
        self.assertEqual(report["summary"]["errors"], 0)
        self.assertEqual(report["summary"]["warnings"], 0)

    def test_task_template_graph_has_no_dangling_links(self):
        entries = task_templates.registry()
        self.assertIn("system_maintenance", entries)
        self.assertIn("system_verify", entries)
        self.assertIn("nkb_sync", entries)
        for task_type, entry in entries.items():
            links = (entry["template"].get("next_tasks") or {})
            for raw_targets in links.values():
                targets = raw_targets if isinstance(raw_targets, list) else [raw_targets]
                for target in targets:
                    self.assertIsNotNone(
                        task_templates.resolve_type(target),
                        "%s -> %s" % (task_type, target),
                    )

    def test_project_template_registry_file_is_not_a_template(self):
        report = project_template.govern(PLATFORM_ROOT)
        self.assertEqual(report["gate"]["decision"], "proceed",
                         report["gate"]["reasons"])

    def test_review_validator_rejects_false_pass(self):
        root = tempfile.mkdtemp(prefix="review_contract_")
        try:
            task_id = "T-CONTRACT"
            review_dir = os.path.join(
                root, "runtime", "reviews", "REVIEW-%s" % task_id)
            os.makedirs(review_dir)
            report_path = os.path.join(review_dir, "report.yaml")
            report = {
                "review_id": "REV-1",
                "task_id": task_id,
                "chapter_ref": "1",
                "created_at": "2026-07-27T00:00:00+08:00",
                "stages": ["continuity"],
                "findings": [{
                    "id": "F-1",
                    "category": "hard_consistency",
                    "severity": "block",
                    "location": "第1章",
                    "observation": "事实冲突",
                    "evidence": "NKB 与正文不一致",
                    "reasoning": "同一事实出现互斥取值",
                    "impact": "破坏连续性",
                    "recommended_fix": "按 NKB 修正",
                }],
                "verdict": "pass",
            }
            _gov.dump_yaml(report_path, report)
            ok, errors = review_orchestrator.validate_report(root, task_id)
            self.assertFalse(ok)
            self.assertTrue(any("verdict 不能为 pass" in item for item in errors))
            report["verdict"] = "blocked"
            _gov.dump_yaml(report_path, report)
            ok, errors = review_orchestrator.validate_report(root, task_id)
            self.assertTrue(ok, errors)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_system_verify_can_consume_submitted_parent(self):
        root = tempfile.mkdtemp(prefix="system_verify_chain_")
        try:
            task_id = "T-SYSTEM-MAINT"
            template = task_templates.load("system_maintenance")
            task_engine.create_task(root, {"task": {
                "id": task_id,
                "type": "system_maintenance",
                "title": "平台维护",
                "priority": "high",
                "agent": {"required_role": "system-maintainer"},
                "permissions": template["permissions"],
                "inputs": {
                    "required": ["change_brief", "explicit_user_approval"],
                    "values": {
                        "change_brief": "测试维护",
                        "explicit_user_approval": True,
                    },
                },
            }})
            task_engine.claim(root, task_id, "tester", "system-maintainer")
            task_engine.start(root, task_id, "tester", "system-maintainer")
            outputs = {}
            for name, filename in (
                    ("patch", "platform-patch-summary.md"),
                    ("validation_report", "validation-report.yaml"),
                    ("operation_manifest", "operation-manifest.yaml")):
                relative = (
                    "tasks/running/%s/outputs/%s"
                    % (task_id, filename))
                path = os.path.join(root, relative)
                with open(path, "w", encoding="utf-8") as stream:
                    stream.write(
                        "status: pass\n"
                        if filename.endswith(".yaml") else "# pass\n")
                outputs[name] = relative
            _, verify_id = task_engine.submit(
                root, task_id, outputs["validation_report"],
                outputs=outputs,
                agent="tester", role="system-maintainer")
            ok, report = task_engine.ready_check(root, verify_id)
            self.assertTrue(ok, report)
            self.assertEqual(
                task_engine._state_of(root, task_id), "submitted")
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

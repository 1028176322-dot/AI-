# -*- coding: utf-8 -*-
"""Regression tests for the canonical NKB 1.3 governance loop."""
import os
import shutil
import sys
import tempfile
import unittest


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_ROOT = os.path.join(PLATFORM_ROOT, "scripts")
for child in os.listdir(SCRIPTS_ROOT):
    path = os.path.join(SCRIPTS_ROOT, child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import _gov
import context_builder
import nkb_validator
import task_cli
import task_engine


COMPONENTS = [
    "Canon", "Characters", "Locations", "Organizations", "Timeline",
    "WorldState", "Events", "Foreshadow", "Assets", "Terminology",
    "StoryState", "ReaderState", "Graph", "Derived",
]


class NkbGovernanceTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="nkb_governance_")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _project(self, strict=True):
        os.makedirs(os.path.join(self.root, "NKB"), exist_ok=True)
        _gov.dump_yaml(os.path.join(self.root, "project.yaml"), {
            "project": {"id": "nkb-test", "name": "NKB Test"},
        })
        if strict:
            _gov.dump_yaml(os.path.join(
                self.root, "PROJECT_LAYOUT.yaml"), {
                    "version": "2.0.0", "strict": True,
                })
        for component in COMPONENTS:
            _gov.dump_yaml(os.path.join(
                self.root, "NKB", "%s.yaml" % component), {
                    "schema_version": "1.3.0",
                    "project_id": "nkb-test",
                    "records": [],
                })
        _gov.dump_yaml(os.path.join(self.root, "NKB", "manifest.yaml"), {
            "nkb": {
                "project_id": "nkb-test",
                "schema_version": "1.3.0",
                "snapshot_id": "NKB-TEST-001",
                "status": "active",
                "authoritative": True,
            },
            "components": {
                component: {
                    "file": "%s.yaml" % component,
                    "version": 0,
                }
                for component in COMPONENTS
            },
            "integrity": {
                "unresolved_conflicts": 0,
                "broken_references": 0,
                "pending_candidates": 0,
            },
        })

    def test_empty_strict_canonical_store_is_structurally_valid(self):
        self._project()
        report = nkb_validator.validate_project(self.root)
        self.assertEqual(report["gate"]["decision"], "proceed", report)
        self.assertEqual(report["components_expected"], COMPONENTS)

    def test_strict_record_requires_complete_fields_and_provenance(self):
        self._project()
        data = _gov.load_yaml(os.path.join(
            self.root, "NKB", "Characters.yaml"))
        data["records"] = [{
            "id": "bad id",
            "name": "缺字段角色",
            "source": {"approval_status": "draft"},
        }]
        _gov.dump_yaml(os.path.join(
            self.root, "NKB", "Characters.yaml"), data)
        report = nkb_validator.validate_project(self.root)
        codes = {item["code"] for item in report["findings"]}
        self.assertEqual(report["gate"]["decision"], "block")
        self.assertIn("FIELD_MISSING", codes)
        self.assertIn("ID_FORMAT_INVALID", codes)
        self.assertIn("SOURCE_FIELD_MISSING", codes)
        self.assertIn("SOURCE_APPROVAL_INVALID", codes)

    def test_legacy_store_reports_drift_without_forced_migration(self):
        self._project(strict=False)
        os.remove(os.path.join(self.root, "NKB", "Organizations.yaml"))
        report = nkb_validator.validate_project(self.root)
        self.assertEqual(report["gate"]["decision"], "proceed", report)
        self.assertTrue(any(
            item["code"] == "COMPONENT_MISSING"
            and item["severity"] == "warn"
            for item in report["findings"]))

    def test_context_understands_ch_100_and_projects_all_domains(self):
        self._project()
        event_data = _gov.load_yaml(os.path.join(
            self.root, "NKB", "Events.yaml"))
        event_data["records"] = [
            {
                "id": "EVT-100", "name": "百章事件", "chapter": "CH-100",
                "participants": ["CHR-100"], "effect": "命运改变",
            },
            {
                "id": "EVT-001", "name": "远古事件", "chapter": "CH-001",
                "participants": [], "effect": "不应进入窗口",
            },
        ]
        _gov.dump_yaml(os.path.join(
            self.root, "NKB", "Events.yaml"), event_data)
        char_data = _gov.load_yaml(os.path.join(
            self.root, "NKB", "Characters.yaml"))
        char_data["records"] = [{
            "id": "CHR-100", "name": "百章角色", "role": "supporting",
            "status": "active",
        }]
        _gov.dump_yaml(os.path.join(
            self.root, "NKB", "Characters.yaml"), char_data)
        state, _ = task_engine.create_task(self.root, {
            "task": {
                "id": "TASK-CH-100",
                "type": "chapter_write",
                "project": "nkb-test",
                "title": "写第100章",
                "chapter_ref": "CH-100",
                "priority": "high",
                "inputs": {"required": []},
                "permissions": {
                    "read": ["NKB/**"],
                    "write": ["chapters/drafts/**"],
                },
                "agent": {"required_role": "writer"},
            },
        })
        self.assertEqual(state, "ready")
        output = context_builder.build_context(
            self.root, "TASK-CH-100", budget=12000)
        with open(output, "r", encoding="utf-8") as stream:
            text = stream.read()
        for heading in (
                "章节计划", "Canon 不可违背事实", "出场角色当前状态",
                "地点与组织", "世界/读者/故事态", "时间线", "相关事件",
                "资产与能力状态", "未回收伏笔", "术语约束", "关系图摘要"):
            self.assertIn(heading, text)
        self.assertIn("百章事件", text)
        self.assertIn("百章角色", text)
        self.assertNotIn("远古事件", text)

    def test_platform_nkb_request_uses_maintenance_task(self):
        template, task_type, _ = task_cli._map_request(
            "修改平台 NKB 校验脚本和 policy")
        self.assertEqual(template, "system-maintenance")
        self.assertEqual(task_type, "system_maintenance")

    def test_back_to_back_chat_tasks_get_distinct_ids(self):
        self._project(strict=False)
        first, _, _ = task_cli._build_task_from_request(
            self.root, "写第1章", "nkb-test", "writer")
        second, _, _ = task_cli._build_task_from_request(
            self.root, "写第2章", "nkb-test", "writer")
        self.assertNotEqual(first["id"], second["id"])


if __name__ == "__main__":
    unittest.main()

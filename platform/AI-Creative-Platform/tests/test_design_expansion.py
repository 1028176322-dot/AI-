# -*- coding: utf-8 -*-
"""Tests for inspiration -> governed design candidate production."""
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
import build_nkb_genesis
import design_expansion
import project_layout
import task_cli
import task_engine


class DesignExpansionTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="design_expansion_")
        project_layout.scaffold_layout(self.root, "xuanhuan")
        _gov.dump_yaml(os.path.join(self.root, "project.yaml"), {
            "project": {
                "id": "design-test",
                "name": "设计测试",
                "type": "xuanhuan",
            },
        })

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _candidate(self, cid="CAND-LOC-001", impact="low",
                   authority="ai_proposed", requires=False,
                   domain="locations"):
        path = os.path.join(
            self.root, "sources", "design", "_candidates",
            "%s.yaml" % cid)
        _gov.dump_yaml(path, {
            "design_candidate": {
                "id": cid,
                "project_id": "design-test",
                "domain": domain,
                "target_document_type": "location",
                "target_path": "sources/design/locations/LOC-001.yaml",
                "proposal": {
                    "document": {
                        "id": "LOC-001",
                        "type": "location",
                        "title": "青石镇",
                        "status": "draft",
                        "version": 1,
                        "updated_at": "2026-07-27",
                        "owner": "project-producer",
                        "project_id": "design-test",
                    },
                    "location": {
                        "id": "LOC-001",
                        "canonical_name": "青石镇",
                        "type": "town",
                        "status": "active",
                        "accessibility": "官道可达",
                    },
                },
                "rationale": "给开篇经营线提供稳定场景",
                "basis": ["用户要求前期偏市井经营"],
                "confidence": 0.86,
                "authority_class": authority,
                "impact": impact,
                "requires_user_decision": requires,
                "dependencies": [],
                "potential_conflicts": [],
                "originality": {
                    "reference_methods_only": True,
                    "copied_expression": False,
                    "copied_proper_nouns": [],
                },
                "status": "pending_review",
            },
        })
        return path

    def test_prepare_structures_free_form_direction(self):
        outputs = design_expansion.prepare(
            self.root,
            "古代玄幻。希望前期偏市井经营。不要系统。主角是工程师转世。",
            mode="balanced")
        for path in outputs.values():
            self.assertTrue(os.path.isfile(path), path)
        brief = _gov.load_yaml(outputs["brief"])["inspiration_brief"]
        self.assertIn("不要系统", brief["forbidden"])
        self.assertIn("希望前期偏市井经营", brief["preferences"])
        self.assertIn("主角是工程师转世", brief["locked_facts"])
        plan = _gov.load_yaml(outputs["generation_plan"])["generation_plan"]
        self.assertEqual(plan["execution_mode"], "single_agent_sequential")
        self.assertTrue(plan["steps"])

    def test_gap_matrix_blocks_empty_design(self):
        design_expansion.prepare(self.root, "玄幻经营文", mode="balanced")
        _, report = design_expansion.build_gap_matrix(self.root)
        self.assertEqual(report["design_gap_matrix"]["gate"], "block")
        self.assertIn(
            "story_core",
            report["design_gap_matrix"]["blocking_gaps"])

    def test_low_impact_delegated_domain_candidate_is_valid(self):
        design_expansion.prepare(self.root, "玄幻经营文", mode="balanced")
        path = self._candidate()
        ok, errors, _ = design_expansion.validate_candidate(
            path, self.root)
        self.assertTrue(ok, errors)
        _, packet = design_expansion.build_approval_packet(self.root)
        self.assertEqual(packet["approval_packet"]["gate"], "proceed")
        self.assertEqual(
            packet["approval_packet"]["delegated_approvals"][0]["id"],
            "CAND-LOC-001")

    def test_high_impact_cannot_fake_delegated_approval(self):
        design_expansion.prepare(self.root, "玄幻经营文", mode="balanced")
        path = self._candidate(
            impact="high", authority="delegated_approved")
        ok, errors, _ = design_expansion.validate_candidate(
            path, self.root)
        self.assertFalse(ok)
        self.assertIn("impact level requires author decision", errors)

    def test_high_impact_candidate_waits_for_explicit_author_decision(self):
        design_expansion.prepare(self.root, "玄幻经营文", mode="balanced")
        self._candidate(impact="high", authority="ai_proposed")
        _, packet = design_expansion.build_approval_packet(self.root)
        self.assertEqual(
            packet["approval_packet"]["gate"], "awaiting_author")
        decisions = os.path.join(
            self.root, "lifecycle", "design", "USER_DECISIONS.yaml")
        _gov.dump_yaml(decisions, {
            "author_decisions": {
                "explicit_user_approval": True,
                "decided_by": "user",
                "approved": ["CAND-LOC-001"],
                "rejected": [],
            },
        })
        _, evidence, updated = design_expansion.apply_author_decisions(
            self.root, decisions)
        self.assertTrue(os.path.isfile(evidence))
        self.assertEqual(
            updated["approval_packet"]["gate"], "proceed")

    def test_review_requires_six_evidence_complete_lenses(self):
        path = design_expansion.prepare_review(self.root)
        report = _gov.load_yaml(path)
        ok, errors, _ = design_expansion.validate_review(path)
        self.assertFalse(ok)
        self.assertTrue(errors)
        for lens in design_expansion.REVIEW_LENSES:
            report["design_review"]["lenses"][lens] = {
                "score": 82,
                "observation": "结构可持续",
                "evidence": ["设计源中的具体字段"],
                "issues": [],
                "recommendations": ["保持约束"],
                "confidence": 0.8,
            }
        report["design_review"]["reviewed_at"] = "2026-07-27"
        report["design_review"]["reviewer"] = "design-reviewer"
        report["design_review"]["gate"] = {
            "decision": "proceed", "reasons": []}
        _gov.dump_yaml(path, report)
        ok, errors, _ = design_expansion.validate_review(path)
        self.assertTrue(ok, errors)

    def test_chat_new_project_direction_routes_to_project_design(self):
        template, task_type, chapter = task_cli._map_request(
            "新项目灵感：玄幻世界观，主角经营成长，补充人物和故事大纲")
        self.assertEqual(template, "project-design")
        self.assertEqual(task_type, "project_design")
        self.assertIsNone(chapter)

    def test_strict_genesis_rejects_missing_design_approval(self):
        argv = list(sys.argv)
        try:
            sys.argv = [
                "build_nkb_genesis",
                "--project-root", self.root,
            ]
            with self.assertRaises(SystemExit) as raised:
                build_nkb_genesis.main()
            self.assertEqual(raised.exception.code, 1)
        finally:
            sys.argv = argv

    def test_review_pass_creates_design_approval_successor(self):
        design_expansion.prepare(self.root, "玄幻经营文", mode="balanced")
        task_engine.create_task(self.root, {
            "task": {
                "id": "TASK-DESIGN",
                "type": "project_design",
                "project": "design-test",
                "priority": "high",
                "inputs": {
                    "required": [],
                    "values": {
                        "autonomy_policy":
                            "sources/design/_intake/autonomy-policy.yaml",
                    },
                },
                "permissions": {
                    "read": ["sources/**"],
                    "write": ["sources/design/_candidates/**"],
                },
                "agent": {"required_role": "project-producer"},
            },
        })
        task_engine.claim(
            self.root, "TASK-DESIGN", "producer", "project-producer")
        task_engine.start(
            self.root, "TASK-DESIGN", "producer", "project-producer")
        source_rel = "tasks/running/TASK-DESIGN/outputs/design.yaml"
        candidate_rel = "tasks/running/TASK-DESIGN/outputs/candidates.yaml"
        _gov.dump_yaml(os.path.join(self.root, source_rel), {"design": []})
        _gov.dump_yaml(os.path.join(
            self.root, candidate_rel), {"candidates": []})
        review_id = task_engine.submit(
            self.root, "TASK-DESIGN", source_rel,
            outputs={
                "design_sources": source_rel,
                "design_candidates": candidate_rel,
            },
            agent="producer", role="project-producer")[1]
        task_engine.claim(
            self.root, review_id, "reviewer", "design-reviewer")
        task_engine.start(
            self.root, review_id, "reviewer", "design-reviewer")
        report_path = design_expansion.prepare_review(self.root)
        report = _gov.load_yaml(report_path)
        for lens in design_expansion.REVIEW_LENSES:
            report["design_review"]["lenses"][lens] = {
                "score": 80,
                "observation": "具备可写性",
                "evidence": ["E-1"],
                "issues": [],
                "recommendations": ["继续"],
                "confidence": 0.8,
            }
        report["design_review"]["reviewed_at"] = "2026-07-27"
        report["design_review"]["reviewer"] = "reviewer"
        report["design_review"]["gate"] = {
            "decision": "proceed", "reasons": []}
        _gov.dump_yaml(report_path, report)
        approval_path, _ = design_expansion.build_approval_packet(
            self.root)
        report_rel = os.path.relpath(
            report_path, self.root).replace("\\", "/")
        approval_rel = os.path.relpath(
            approval_path, self.root).replace("\\", "/")
        task_engine.submit(
            self.root, review_id, report_rel,
            outputs={
                "design_review_report": report_rel,
                "approval_packet": approval_rel,
            },
            agent="reviewer", role="design-reviewer")
        task_engine.review(
            self.root, review_id, "pass",
            reviewer="reviewer", role="design-reviewer")
        approval_task = "%s-DESIGN-APPROVAL" % review_id
        self.assertEqual(
            task_engine.load_task(self.root, approval_task)[0], "ready")


if __name__ == "__main__":
    unittest.main()

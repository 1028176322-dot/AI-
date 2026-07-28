# -*- coding: utf-8 -*-
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
import feedback_learning
import project_layout
import reader_panel
import reference_learning
import task_engine
import compliance_scan


class LearningLoopTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="learning_loop_")
        self._old_fingerprint_key = os.environ.get(
            "FS_FINGERPRINT_KEY_DEFAULT")
        os.environ["FS_FINGERPRINT_KEY_DEFAULT"] = (
            "unit-test-reference-key-not-for-production")

    def tearDown(self):
        if self._old_fingerprint_key is None:
            os.environ.pop("FS_FINGERPRINT_KEY_DEFAULT", None)
        else:
            os.environ["FS_FINGERPRINT_KEY_DEFAULT"] = (
                self._old_fingerprint_key)
        shutil.rmtree(self.root, ignore_errors=True)

    def _reference(self, name="sample.txt"):
        path = os.path.join(self.root, name)
        text = (
            "第一章 山门\n夜色压住山门。少年忽然听见钟声，他问：“谁在那里？”\n"
            "风停了，门后却没有人。\n第二章 来客\n"
            "清晨，陌生人带来一条规则。少年必须选择，否则秘密将被公开？\n"
        )
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(text)
        return path

    def test_reference_profile_contains_no_raw_text(self):
        out_dir = os.path.join(self.root, "learning", "candidates")
        path, report = reference_learning.analyze(
            self._reference(), "xuanhuan", out_dir)
        self.assertFalse(report["raw_text_stored"])
        self.assertTrue(report["meta"]["source_hash"])
        self.assertFalse(report["candidates"])
        self.assertTrue(report["style_dimensions"])
        self.assertTrue(report["legacy_candidates"])
        with open(path, "r", encoding="utf-8") as stream:
            self.assertNotIn("夜色压住山门", stream.read())
        ok, errors = reference_learning.validate_profile(path)
        self.assertTrue(ok, errors)

    def test_project_promotion_requires_approval(self):
        out_dir = os.path.join(self.root, "learning", "candidates")
        reference_learning.analyze(self._reference(), "xuanhuan", out_dir)
        summary_path, _ = reference_learning.batch(
            self.root, "xuanhuan", out_dir)
        with self.assertRaises(ValueError):
            reference_learning.promote_project(
                summary_path, self.root, approved=False)
        with self.assertRaisesRegex(ValueError, "没有候选规则"):
            reference_learning.promote_project(
                summary_path, self.root, approved=True)

    def test_review_feedback_becomes_guidance(self):
        finding = {
            "category": "logic", "severity": "fail",
            "observation": "结果先于原因出现", "reasoning": "缺少触发条件",
            "recommended_fix": "复查因果链",
        }
        result = feedback_learning.capture_findings(
            self.root, "TASK-R1", [finding], decision="fail")
        self.assertTrue(os.path.isfile(result["writing_guidance"]))
        self.assertTrue(os.path.isfile(result["review_regression"]))
        feedback_learning.capture_findings(
            self.root, "TASK-R2", [finding], decision="fail")
        ledger = _gov.load_yaml(result["ledger"])
        self.assertEqual(ledger["records"][0]["occurrences"], 2)

    def test_reader_panel_requires_all_evidence(self):
        path, _ = reader_panel.prepare_panel(
            self.root, "TASK-REVIEW", "CH001", "chapters/drafts/CH001.md")
        ok, errors, report = reader_panel.validate_panel(path)
        self.assertFalse(ok)
        self.assertTrue(errors)
        for lens in report["lenses"]:
            lens.update({
                "score": 75, "observation": "可理解",
                "evidence_location": "第1段", "reading_effect": "继续阅读",
                "expectation": "希望看到选择结果",
                "recommended_fix": "保持因果清晰", "confidence": 0.8,
            })
        report["dropoff"] = {
            "risk": "low", "location": "无明显停读点", "reason": "推进稳定"}
        report["summary"] = "整体可继续阅读"
        _gov.dump_yaml(path, report)
        ok, errors, finalized = reader_panel.validate_panel(path)
        self.assertTrue(ok, errors)
        self.assertEqual(finalized["gate"]["decision"], "proceed")

    def test_human_feedback_is_separate_calibration(self):
        reader_panel.prepare_panel(self.root, "TASK-HUMAN")
        source = os.path.join(self.root, "human.yaml")
        _gov.dump_yaml(source, {"participants": [
            {"reader_id": "R1", "segment": "new", "completion_ratio": 90,
             "recommend_score": 80, "payment_intent": 70,
             "dropoff_location": None},
            {"reader_id": "R2", "segment": "veteran", "completion_ratio": 80,
             "recommend_score": 75, "payment_intent": 65,
             "dropoff_location": "第6段"},
            {"reader_id": "R3", "segment": "target", "completion_ratio": 95,
             "recommend_score": 85, "payment_intent": 80,
             "dropoff_location": None},
        ]})
        out, report = reader_panel.ingest_human(
            self.root, "TASK-HUMAN", source)
        self.assertTrue(os.path.isfile(out))
        self.assertEqual(report["participant_count"], 3)
        self.assertEqual(report["schema"], "human-reader-feedback@1.0.0")

    def test_layout_is_strict_only_when_marked(self):
        self.assertFalse(project_layout.validate(self.root)["response"]["strict"])
        project_layout.scaffold_layout(self.root, "xuanhuan")
        self.assertEqual(
            project_layout.validate(self.root)["gate"]["decision"], "proceed")
        with open(os.path.join(self.root, "loose.tmp"), "w",
                  encoding="utf-8") as stream:
            stream.write("x")
        blocked = project_layout.validate(self.root)
        self.assertEqual(blocked["gate"]["decision"], "block")
        self.assertIn("loose.tmp", blocked["response"]["unexpected"])

    def test_strict_project_review_cannot_bypass_reader_panel(self):
        project_layout.scaffold_layout(self.root, "xuanhuan")
        dep = {"task": {
            "id": "TASK-WRITE", "type": "chapter_write",
            "project": "p", "status": "submitted", "chapter_ref": "CH001",
        }}
        review = {"task": {
            "id": "TASK-REVIEW", "type": "chapter_review",
            "project": "p", "status": "running",
            "dependencies": ["TASK-WRITE"],
        }}
        _gov.dump_yaml(os.path.join(
            self.root, "tasks", "submitted", "TASK-WRITE.yaml"), dep)
        _gov.dump_yaml(os.path.join(
            self.root, "tasks", "running", "TASK-REVIEW.yaml"), review)
        with self.assertRaisesRegex(ValueError, "reader panel missing"):
            task_engine.review(self.root, "TASK-REVIEW", "pass")

    def test_strict_project_governs_non_prose_files(self):
        self.assertFalse(compliance_scan._requires_task(
            self.root, "analysis/learning/result.yaml"))
        project_layout.scaffold_layout(self.root, "xuanhuan")
        self.assertTrue(compliance_scan._requires_task(
            self.root, "analysis/learning/result.yaml"))
        self.assertFalse(compliance_scan._requires_task(
            self.root, "tasks/running/TASK-X.yaml"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

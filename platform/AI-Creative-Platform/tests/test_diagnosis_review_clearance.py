# -*- coding: utf-8 -*-
import os
import sys
import unittest


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEARNING = os.path.join(PLATFORM_ROOT, "scripts", "learning")
if LEARNING not in sys.path:
    sys.path.insert(0, LEARNING)

import diagnosis


class DiagnosisReviewClearanceTest(unittest.TestCase):
    def test_passed_review_clears_deterministic_signal_for_routing(self):
        review = {
            "review_id": "REVIEW-1",
            "task_id": "TASK-REVIEW-1",
            "verdict": "pass",
            "stages": ["immersive", "style", "reader_panel"],
            "findings": [],
        }
        clearance = diagnosis.clearance_from_review(
            review, "a" * 64)
        report = diagnosis.ai_diagnose(
            "CH-001", "RC-001", "TASK-DIAG-1",
            "夜色如墨。人物推门而入。",
            protected_manifest_sha256="b" * 64,
            require_semantic_evidence=True,
            semantic_clearance=clearance)
        self.assertFalse(report["has_issues"])
        self.assertFalse(report["only_warnings"])
        self.assertEqual("skip", report["recommended_action"])
        self.assertEqual(
            "chapter_review_clearance",
            report["literary_judgment_source"])

    def test_blocking_style_finding_cannot_clear(self):
        clearance = diagnosis.clearance_from_review({
            "review_id": "REVIEW-2",
            "task_id": "TASK-REVIEW-2",
            "verdict": "pass_with_fixes",
            "findings": [{
                "category": "style",
                "severity": "fail",
            }],
        })
        self.assertIsNone(clearance)
        with self.assertRaisesRegex(ValueError, "requires structured"):
            diagnosis.ai_diagnose(
                "CH-001", "RC-001", "TASK-DIAG-2",
                "正文。",
                require_semantic_evidence=True,
                semantic_clearance=clearance)


if __name__ == "__main__":
    unittest.main(verbosity=2)

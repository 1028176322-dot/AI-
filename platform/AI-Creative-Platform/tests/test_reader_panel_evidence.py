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
import reader_panel


class ReaderPanelEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="reader-evidence-")
        self.source = os.path.join(self.root, "chapter.txt")
        with open(self.source, "w", encoding="utf-8") as stream:
            stream.write("第一句证据。\n中间发生了变化。\n第二句结论。")
        self.report, _ = reader_panel.prepare_panel(
            self.root, "TASK-READER-001",
            chapter_ref="CH-001", chapter_path=self.source)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _fill(self, evidence):
        report = _gov.load_yaml(self.report)
        for lens in report["lenses"]:
            lens.update({
                "score": 80,
                "observation": "证据支持判断",
                "evidence_location": "第一至三句",
                "evidence_excerpt": evidence,
                "reading_effect": "能够理解变化",
                "expectation": "期待后续兑现",
                "recommended_fix": "保留因果",
                "confidence": 0.8,
            })
        report["dropoff"] = {
            "risk": "low",
            "location": "无",
            "reason": "推进清楚",
        }
        report["summary"] = "通过"
        _gov.dump_yaml(self.report, report)
        return reader_panel.validate_panel(self.report)

    def test_ordered_excerpt_list_can_span_sentences(self):
        ok, errors, _ = self._fill(
            ["第一句证据", "第二句结论"])
        self.assertTrue(ok, errors)

    def test_ellipsis_separated_excerpt_can_span_sentences(self):
        ok, errors, _ = self._fill(
            "第一句证据……第二句结论")
        self.assertTrue(ok, errors)

    def test_fabricated_fragment_is_rejected(self):
        ok, errors, _ = self._fill(
            ["第一句证据", "正文中不存在"])
        self.assertFalse(ok)
        self.assertTrue(any(
            "evidence_excerpt" in error for error in errors))


if __name__ == "__main__":
    unittest.main(verbosity=2)

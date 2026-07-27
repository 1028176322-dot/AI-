# -*- coding: utf-8 -*-
"""#21 回归：F1 只读诊断（ai-diagnose，不改正文）。"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM_ROOT = os.path.dirname(HERE)
for _c in ("learning", "logs"):
    _p = os.path.join(PLATFORM_ROOT, "scripts", _c)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import diagnosis as dx  # noqa: E402


class DiagnosisTest(unittest.TestCase):
    def _draft(self, body):
        return ("第一章 风雪夜\n" + body)

    def test_readonly_does_not_mutate_inputs(self):
        """诊断严格只读：传入的 nkb 快照不得被修改。"""
        nkb = {"canon": [{"id": "C1", "name": "肖凡"}]}
        nkb_before = repr(nkb)
        draft = self._draft("他似乎也许大概在犹豫。事实上，值得注意的是，显而易见的是，"
                             "他在想。他在想。他在想。")
        r = dx.ai_diagnose("CH1", "TA1", "T1", draft, nkb_snapshot=nkb)
        self.assertEqual(repr(nkb), nkb_before, "nkb_snapshot must not be mutated")

    def test_detects_issues(self):
        draft = self._draft("他似乎也许大概在犹豫。事实上，值得注意的是，显而易见的是，"
                             "他握紧了刀。他握紧了刀。他握紧了刀。他握紧了刀。")
        r = dx.ai_diagnose("CH1", "TA1", "T1", draft)
        self.assertTrue(r["has_issues"])
        self.assertTrue(len(r["issue_list"]) > 0)
        cats = {i["category"] for i in r["issue_list"]}
        self.assertIn("repetitive_opener", cats)

    def test_clean_draft_no_issues_skip(self):
        draft = self._draft("肖凡推开木门。冷风灌进来。他眯起眼，望向院中的老槐。")
        r = dx.ai_diagnose("CH1", "TA1", "T1", draft)
        self.assertFalse(r["has_issues"])
        self.assertEqual(r["recommended_action"], "skip")

    def test_recommended_action_in_enum(self):
        draft = self._draft("他似乎也许大概在犹豫。事实上，值得注意的是，显而易见的是，"
                             "他握紧了刀。他握紧了刀。他握紧了刀。他握紧了刀。")
        r = dx.ai_diagnose("CH1", "TA1", "T1", draft)
        self.assertIn(r["recommended_action"], ("revise", "skip", "human_review"))

    def test_schema_validation_ok(self):
        draft = self._draft("肖凡推开木门。冷风灌进来。他眯起眼。")
        r = dx.ai_diagnose("CH1", "TA1", "T1", draft, protected_manifest_sha256="m" * 64)
        ok, errors = dx.validate_diagnosis(r)
        self.assertTrue(ok, errors)

    def test_source_draft_sha256_matches(self):
        import hashlib
        draft = self._draft("肖凡推开木门。冷风灌进来。")
        r = dx.ai_diagnose("CH1", "TA1", "T1", draft)
        self.assertEqual(r["source_draft_sha256"],
                         hashlib.sha256(draft.encode("utf-8")).hexdigest())

    def test_persist_and_read_roundtrip(self):
        root = tempfile.mkdtemp(prefix="dx_")
        draft = self._draft("他似乎也许大概在犹豫。事实上，值得注意的是。")
        r = dx.ai_diagnose("CH1", "TA1", "T1", draft)
        p = dx.persist(r, root, "CH1", "T1")
        self.assertTrue(os.path.exists(p))
        self.assertIn("analysis", p.replace("\\", "/"))
        self.assertNotIn("chapters", p.replace("\\", "/"))
        back = dx.read(root, "CH1", "T1")
        self.assertEqual(back["source_draft_sha256"], r["source_draft_sha256"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

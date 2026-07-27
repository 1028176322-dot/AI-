# -*- coding: utf-8 -*-
"""#23 final_regression：双模式（baseline/post_apply）、FINAL_PASSED/FINAL_FAILED。"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM_ROOT = os.path.dirname(HERE)
for _c in ("learning",):
    _p = os.path.join(PLATFORM_ROOT, "scripts", _c)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import final_regression as fr


class FinalRegressionTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.ch, self.cyc, self.task = "CH1", "TA1", "final-reg-1"
        self.draft = "肖凡握紧刀柄。他在雪地里奔跑。忽然一阵枪响划破夜空。那一年是一三二七年。"
        self.pre = "肖凡在雪地里跌倒了。远处传来狼嚎。"
        self.applied = "肖凡握紧刀柄。他在雪地里奔跑。枪声划破夜空。那一年是一三二七年。"
        self.manifest_sha = "abcd1234"
        self.nkb_sha = "efgh5678"
        self.nkb_rev = "N1"

    def test_baseline_passes(self):
        """mode=baseline：所有绑定齐全 → FINAL_PASSED"""
        d = fr.run_regression("baseline", self.ch, self.cyc, self.task,
                               draft_text=self.draft,
                               nkb_revision=self.nkb_rev,
                               nkb_snapshot_sha256=self.nkb_sha,
                               protected_manifest_sha256=self.manifest_sha,
                               outline_sha256="out123",
                               chapter_review_report_sha256="review456")
        self.assertEqual(d["overall"], "FINAL_PASSED")
        ok, errs = fr.validate_result(d)
        self.assertTrue(ok, errs)
        self.assertEqual(d["mode"], "baseline")
        self.assertTrue(len(d["checks"]) >= 2)

    def test_baseline_fails_on_missing_bindings(self):
        """mode=baseline：缺少 nkb 绑定 → FINAL_FAILED（hard_fail）"""
        d = fr.run_regression("baseline", self.ch, self.cyc, self.task,
                               draft_text=self.draft,
                               nkb_revision="", nkb_snapshot_sha256="",
                               protected_manifest_sha256="")
        self.assertEqual(d["overall"], "FINAL_FAILED")
        ok, errs = fr.validate_result(d)
        self.assertTrue(ok, errs)

    def test_post_apply_passes(self):
        """mode=post_apply：保真度高 + 质量不下滑 + 绑定齐 → FINAL_PASSED"""
        d = fr.run_regression("post_apply", self.ch, self.cyc, self.task,
                               pre_apply_text=self.pre,
                               applied_draft_text=self.applied,
                               nkb_revision=self.nkb_rev,
                               nkb_snapshot_sha256=self.nkb_sha,
                               protected_manifest_sha256=self.manifest_sha,
                               outline_sha256="out123")
        self.assertEqual(d["overall"], "FINAL_PASSED")
        ok, errs = fr.validate_result(d)
        self.assertTrue(ok, errs)
        self.assertEqual(d["mode"], "post_apply")

    def test_post_apply_fails_on_low_fidelity(self):
        """mode=post_apply：大幅修改草稿 → 保真度低 → FINAL_FAILED"""
        pre = "肖凡在雪地里。那年是一三二七年。气温零下十五度。"
        app = "张三在城市里。那年是二〇二四年。天气暖和。"
        d = fr.run_regression("post_apply", self.ch, self.cyc, self.task,
                               pre_apply_text=pre, applied_draft_text=app,
                               nkb_revision=self.nkb_rev,
                               nkb_snapshot_sha256=self.nkb_sha,
                               protected_manifest_sha256=self.manifest_sha)
        self.assertEqual(d["overall"], "FINAL_FAILED")
        # 保真度检查应失败
        fidelity_check = [c for c in d["checks"] if c["check"] == "fidelity"][0]
        self.assertFalse(fidelity_check["passed"])
        self.assertLess(fidelity_check["fact_retention"], 0.95)

    def test_baseline_fails_chapter_review_missing(self):
        """mode=baseline：缺少 chapter_review 绑定 → FINAL_FAILED"""
        d = fr.run_regression("baseline", self.ch, self.cyc, self.task,
                               draft_text=self.draft,
                               nkb_revision=self.nkb_rev,
                               nkb_snapshot_sha256=self.nkb_sha,
                               protected_manifest_sha256=self.manifest_sha,
                               chapter_review_report_sha256="")
        self.assertEqual(d["overall"], "FINAL_FAILED")

    def test_invalid_mode_returns_failed(self):
        d = fr.run_regression("invalid_mode", self.ch, self.cyc, self.task)
        self.assertEqual(d["overall"], "FINAL_FAILED")
        self.assertIn("error", d)

    def test_persist_analysis_style_only(self):
        d = fr.run_regression("baseline", self.ch, self.cyc, self.task,
                               draft_text=self.draft,
                               nkb_revision=self.nkb_rev,
                               nkb_snapshot_sha256=self.nkb_sha,
                               protected_manifest_sha256=self.manifest_sha,
                               chapter_review_report_sha256="review456")
        path = fr.persist(d, self.root, self.ch, self.cyc, self.task)
        self.assertTrue(os.path.exists(path))
        self.assertIn("analysis/style", path.replace("\\", "/"))

    def test_validate_result_rejects_bad_overall(self):
        ok, errs = fr.validate_result({"overall": "INVALID"})
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()

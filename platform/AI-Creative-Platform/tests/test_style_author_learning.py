# -*- coding: utf-8 -*-
"""#10 author_learning：span 级反馈记录、≥3 证据门槛生成 L4 候选、持久化。"""
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

import author_learning as al


class AuthorLearningTest(unittest.TestCase):
    def setUp(self):
        self.fb_dir = tempfile.mkdtemp()

    def _record(self, kind="stylistic", description="prefer short sentences",
                accepted=True):
        return al.record_feedback(
            chapter_id="CH1", span_start=0, span_end=20,
            original_text="事实上可以说很明显",
            revised_text="",
            reason="remove meta commentary",
            kind=kind, scene_type="battle",
            accepted=accepted, reviewer_id="author1",
            task_id="task-fb-1", feedback_store=self.fb_dir)

    def test_record_feedback_creates_file(self):
        entry = self._record()
        self.assertEqual(entry["kind"], "stylistic")
        self.assertTrue(entry["accepted"])
        files = os.listdir(self.fb_dir)
        self.assertEqual(len(files), 1)

    def test_cluster_feedback(self):
        self._record(accepted=True)
        self._record(accepted=True)
        clusters = al.cluster_feedback(self.fb_dir)
        self.assertEqual(len(clusters), 1)
        key = list(clusters.keys())[0]
        self.assertEqual(clusters[key]["count"], 2)

    def test_generate_candidates_below_threshold(self):
        # 2 条证据 < 3 门槛
        self._record(accepted=True)
        self._record(accepted=True)
        candidates = al.generate_l4_candidates(self.fb_dir, min_evidence=3)
        self.assertEqual(len(candidates), 0)

    def test_generate_candidates_above_threshold(self):
        for _ in range(3):
            self._record(accepted=True)
        candidates = al.generate_l4_candidates(self.fb_dir, min_evidence=3)
        self.assertEqual(len(candidates), 1)
        c = candidates[0]
        self.assertEqual(c["evidence_count"], 3)
        self.assertIn("L4-", c["rule_id"])

    def test_generate_candidates_rejected_not_counted(self):
        # 3 条但 2 条拒绝 → 不被提升
        self._record(accepted=True)
        self._record(accepted=False)
        self._record(accepted=False)
        candidates = al.generate_l4_candidates(self.fb_dir, min_evidence=3)
        self.assertEqual(len(candidates), 0)

    def test_persist_l4_candidate(self):
        style_dir = tempfile.mkdtemp()
        candidate = {"rule_id": "L4-test", "kind": "stylistic",
                     "description": "test", "evidence_count": 3}
        path = al.persist_l4_candidate(candidate, style_dir)
        self.assertTrue(os.path.exists(path))
        # 读回
        loaded = al.read_l4_candidates(style_dir)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["rule_id"], "L4-test")


if __name__ == "__main__":
    unittest.main()

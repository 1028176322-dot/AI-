# -*- coding: utf-8 -*-
"""#10 style_hitrate：追加式日志、命中率聚合、硬规则豁免、抑制回调。"""
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

import style_hitrate as hr


class HitrateTest(unittest.TestCase):
    def setUp(self):
        self.log_dir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.log_dir, "hitrate.log")
        self.hl = hr.HitrateLog(path=self.log_path)

    def test_record_and_aggregate(self):
        self.hl.record_hit("pref_short_sent", "battle", usage_count=10, hit_count=9)
        self.hl.record_hit("pref_short_sent", "battle", usage_count=10, hit_count=8)
        stats = self.hl.aggregate()
        self.assertIn("pref_short_sent", stats)
        s = stats["pref_short_sent"]
        self.assertEqual(s["opportunities"], 20)
        self.assertEqual(s["hits"], 17)
        self.assertAlmostEqual(s["hitrate"], 0.85)
        self.assertTrue(s["suppressed"])

    def test_hard_rules_excluded(self):
        self.hl.record_hit("hard_pov", "battle", usage_count=5, hit_count=5)
        self.hl.record_hit("pref_short_sent", "battle", usage_count=10, hit_count=9)
        stats = self.hl.aggregate(hard_rule_ids=["hard_pov"])
        self.assertNotIn("hard_pov", stats)
        self.assertIn("pref_short_sent", stats)

    def test_suppressed_rules_list(self):
        self.hl.record_hit("pref_a", "battle", usage_count=10, hit_count=9)
        self.hl.record_hit("pref_b", "dialogue", usage_count=10, hit_count=2)
        suppressed = self.hl.suppressed_rules()
        self.assertIn("pref_a", suppressed)
        self.assertNotIn("pref_b", suppressed)

    def test_calibrate_suppressed_weights(self):
        stats = {"pref_a": {"suppressed": True, "hitrate": 0.9},
                 "pref_b": {"suppressed": False, "hitrate": 0.2}}
        weights = {"pref_a": 1.0, "pref_b": 1.0}
        cal = hr.calibrate_suppressed_weights(stats, weights)
        self.assertEqual(cal["pref_a"], 0.5)
        self.assertEqual(cal["pref_b"], 1.0)

    def test_scene_type_filter(self):
        self.hl.record_hit("pref_a", "battle", usage_count=10, hit_count=9)
        self.hl.record_hit("pref_a", "dialogue", usage_count=10, hit_count=2)
        battle = self.hl.aggregate(scene_type="battle")
        self.assertEqual(battle["pref_a"]["hitrate"], 0.9)
        dialogue = self.hl.aggregate(scene_type="dialogue")
        self.assertEqual(dialogue["pref_a"]["hitrate"], 0.2)

    def test_should_suppress_helper(self):
        self.assertTrue(hr.should_suppress(0.9))
        self.assertFalse(hr.should_suppress(0.5))
        self.assertFalse(hr.should_suppress(0.85, suppression_threshold=0.86))


if __name__ == "__main__":
    unittest.main()

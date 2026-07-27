# -*- coding: utf-8 -*-
"""#22 quality_review：版本化判定、comparator 方向、样本不足、hard_gate 拒豁免、WAIVED。"""
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

import quality_review as qr
from authorize import Authorizer, TaskContext

DEFAULT_POLICY = os.path.join(
    PLATFORM_ROOT, "core", "learning", "quality-policies", "default.v1.yaml")


class QualityReviewTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.policy = qr.load_policy(DEFAULT_POLICY)
        self.ch, self.cyc, self.task = "CH1", "TA1", "quality-review-1"

    # 好稿：第三人称 / 战斗线索齐 / 句长平稳 / 低重复
    GOOD = ("肖凡握紧刀柄。他在雪地里冲锋。枪声划破夜空。火光映红了他的脸。敌人溃退了。")

    # 坏稿：第一人称 + 元评论词 + 无战斗线索 + 高重复
    BAD = ("我觉得事实上这很奇怪。我觉得事实上这很奇怪。我觉得事实上这很奇怪。"
           "我认为毋庸置疑一切都错了。")

    # 仅非硬指标失败（高重复但第三人称+战斗线索）：用于测试人工豁免
    WAIVE = "肖凡握紧刀柄。肖凡握紧刀柄。肖凡握紧刀柄。肖凡握紧刀柄。"

    def _review(self, text, scene="battle", override=False):
        return qr.review(self.ch, self.cyc, self.task, self.task, scene, text,
                         self.policy, human_override=override)

    def test_good_passes(self):
        d = self._review(self.GOOD)
        self.assertEqual(d["overall"], "QUALITY_PASSED")
        ok, errs = qr.validate_report(d)
        self.assertTrue(ok, errs)
        self.assertEqual(d["quality_policy_version"], "1.0.0")

    def test_bad_fails_hard_gate_cannot_be_overridden(self):
        d = self._review(self.BAD)
        self.assertEqual(d["overall"], "QUALITY_FAILED")
        # 第一人称 → pov_consistency 低 → hard_gate 失败 → 即便请求豁免仍 FAILED
        d2 = self._review(self.BAD, override=True)
        self.assertEqual(d2["overall"], "QUALITY_FAILED")
        self.assertFalse(d2["human_override"])

    def test_human_override_waives_non_hard_failure(self):
        d = self._review(self.WAIVE)
        self.assertEqual(d["overall"], "QUALITY_FAILED")  # 仅 redundancy(非硬) 失败
        d2 = self._review(self.WAIVE, override=True)
        self.assertEqual(d2["overall"], "QUALITY_WAIVED")
        self.assertTrue(d2["human_override"])

    def test_short_text_missing_data_policy_warn_not_fail(self):
        # 单句 → sample_size < minimum_sample_size，missing_data_policy=warn → 不判失败
        d = self._review("肖凡挥刀冲入雪地。")
        self.assertIn(d["overall"], ("QUALITY_PASSED", "QUALITY_WAIVED"))

    def test_comparator_direction_low_redundancy_passes(self):
        # redundancy 越低越好（lt）：高重复文本必失败
        d = self._review(self.WAIVE)
        red = [m for m in d["metrics"] if m["name"] == "redundancy"][0]
        self.assertFalse(red["passed"])
        # 低重复的好稿 redundancy 通过
        good_red = [m for m in self._review(self.GOOD)["metrics"] if m["name"] == "redundancy"][0]
        self.assertTrue(good_red["passed"])

    def test_authorize_quality_review_gates_path(self):
        auth = Authorizer()
        qpath = os.path.join(self.root, "analysis", "style", self.ch, self.cyc,
                             "%s.quality-report.json" % self.task)
        res = [{"canonical_path": qpath, "expected_sha256": "absent"}]
        ctx_ok = TaskContext(task_id=self.task, actor_id="A", session_ready=True,
                              subagent_policy="denied", lease_owner="A", state="RUNNING")
        r = auth.authorize("quality_review", ctx_ok, resources=res, env={"root": self.root})
        self.assertTrue(r.allowed, r.failed)

        bad = os.path.join(self.root, "chapters", "approved", "CH1.md")
        r2 = auth.authorize("quality_review",
                            TaskContext(task_id=self.task, actor_id="A", session_ready=True,
                                        subagent_policy="denied", lease_owner="A", state="RUNNING"),
                            resources=[{"canonical_path": bad, "expected_sha256": "absent"}],
                            env={"root": self.root})
        self.assertFalse(r2.allowed)
        self.assertIn("candidate_path_permission", [f["check"] for f in r2.failed])


if __name__ == "__main__":
    unittest.main()

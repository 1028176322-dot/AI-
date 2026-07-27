# -*- coding: utf-8 -*-
"""#23 chapter_rollback：ROLLED_BACK / ROLLBACK_CONFLICT 检测、产合规 dict、authorize 门禁。"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM_ROOT = os.path.dirname(HERE)
for _c in ("learning", "logs", "_common"):
    _p = os.path.join(PLATFORM_ROOT, "scripts", _c)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import chapter_rollback as cr
from authorize import Authorizer, TaskContext


class ChapterRollbackTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "chapters", "drafts"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "analysis", "style"), exist_ok=True)
        self.ch, self.cyc, self.task = "CH1", "TA1", "rollback-1"
        self.pre_apply = "肖凡在雪地里跌倒了。远处传来狼嚎。"
        self.applied = "肖凡握紧刀柄。他在雪地里奔跑。枪声划破夜空。"
        self.applied_sha = cr._sha256(self.applied)

    def test_rollback_same_hash_returns_rolled_back(self):
        """当前草稿哈希与 applied_draft_sha256 一致 → ROLLED_BACK"""
        d = cr.prepare_rollback(self.ch, self.cyc, self.task,
                                 self.pre_apply, self.applied_sha,
                                 self.applied)
        self.assertEqual(d["result"], "ROLLED_BACK")
        ok, errs = cr.validate_rollback_result(d)
        self.assertTrue(ok, errs)
        self.assertEqual(d["pre_apply_sha256"], cr._sha256(self.pre_apply))
        self.assertEqual(d["applied_draft_sha256"], self.applied_sha)

    def test_rollback_conflict_draft_changed(self):
        """草稿在 apply 后被改动 → ROLLBACK_CONFLICT"""
        changed = "完全不同了的新草稿内容都在这里了。"
        d = cr.prepare_rollback(self.ch, self.cyc, self.task,
                                 self.pre_apply, self.applied_sha,
                                 changed)
        self.assertEqual(d["result"], "ROLLBACK_CONFLICT")
        ok, errs = cr.validate_rollback_result(d)
        self.assertTrue(ok, errs)
        self.assertIn("draft changed", d.get("error", ""))

    def test_rollback_conflict_current_not_matching(self):
        """不同哈希时 current_draft_sha256 ≠ applied_draft_sha256"""
        changed = "张三在城市里。那年是二〇二四年。"
        d = cr.prepare_rollback(self.ch, self.cyc, self.task,
                                 self.pre_apply, self.applied_sha,
                                 changed)
        self.assertEqual(d["result"], "ROLLBACK_CONFLICT")
        self.assertNotEqual(d["current_draft_sha256"], d["applied_draft_sha256"])

    def test_authorize_rollback_gates_path(self):
        auth = Authorizer()
        src_path = os.path.join(self.root, "analysis", "style", self.ch, self.cyc,
                                 "draft-pre-apply.md")
        tgt_path = os.path.join(self.root, "chapters", "drafts", "CH1.md")
        res = [
            {"canonical_path": src_path, "expected_sha256": "absent", "role": "source"},
            {"canonical_path": tgt_path, "expected_sha256": "absent", "role": "target"},
        ]
        ctx = TaskContext(task_id=self.task, actor_id="A", session_ready=True,
                          subagent_policy="denied", lease_owner="A",
                          state="ROLLBACK_READY")
        r = auth.authorize("rollback", ctx, resources=res, env={"root": self.root})
        self.assertTrue(r.allowed, r.failed)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""#23 chapter_apply：产合规 apply-result、pre_apply 备份、STALE 检测、authorize 门禁。"""
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

import chapter_apply as ca
from authorize import Authorizer, TaskContext


class ChapterApplyTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "chapters", "drafts"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "analysis", "style"), exist_ok=True)
        self.ch, self.cyc, self.task = "CH1", "TA1", "apply-1"
        self.draft = "肖凡握紧刀柄。他在雪地里奔跑。那一年是一三二七年。"
        self.candidate = "肖凡握紧刀柄。他在雪地奔跑。那一年是一三二七年。枪声响了。"
        self.candidate_sha = ca._sha256(self.candidate)

    def test_prepare_apply_returns_ready(self):
        d = ca.prepare_apply(self.ch, self.cyc, self.task,
                              self.draft, self.candidate, self.candidate_sha,
                              source_draft_sha256=ca._sha256(self.draft))
        self.assertEqual(d["status"], "APPLY_READY")
        ok, errs = ca.validate_apply_result(d)
        self.assertTrue(ok, errs)
        self.assertIn("pre_apply_sha256", d)

    def test_prepare_apply_detect_stale(self):
        """草稿变化后候选 STALE"""
        different_draft = "张三在城市里。那年是二〇二四年。"
        d = ca.prepare_apply(self.ch, self.cyc, self.task,
                              different_draft, self.candidate, self.candidate_sha,
                              source_draft_sha256=ca._sha256(self.draft))
        self.assertEqual(d["status"], "STALE")
        self.assertIn("draft changed", d.get("error", ""))

    def test_persist_pre_apply_backup(self):
        path = ca.persist_pre_apply(self.root, self.ch, self.cyc, self.draft)
        self.assertTrue(os.path.exists(path))
        self.assertIn("analysis/style", path.replace("\\", "/"))
        self.assertIn("draft-pre-apply.md", path)

    def test_read_pre_apply_restores(self):
        ca.persist_pre_apply(self.root, self.ch, self.cyc, self.draft)
        restored = ca.read_pre_apply(self.root, self.ch, self.cyc)
        self.assertEqual(restored, self.draft)

    def test_authorize_apply_gates_path(self):
        auth = Authorizer()
        draft_path = os.path.join(self.root, "chapters", "drafts", "CH1.md")
        src_path = os.path.join(self.root, "chapters", "drafts", "CH1.md")
        cand_path = os.path.join(self.root, "analysis", "style", self.ch, self.cyc,
                                 "revision-candidate.md")
        res = [
            {"canonical_path": src_path, "expected_sha256": "absent", "role": "source"},
            {"canonical_path": draft_path, "expected_sha256": "absent", "role": "target"},
            {"canonical_path": cand_path, "expected_sha256": "absent", "role": "candidate_or_backup"},
        ]
        ctx = TaskContext(task_id=self.task, actor_id="A", session_ready=True,
                          subagent_policy="denied", lease_owner="A",
                          state="APPLY_READY")
        r = auth.authorize("apply", ctx, resources=res, env={"root": self.root})
        self.assertTrue(r.allowed, r.failed)


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""#22 style_revise：只写 analysis/style、绑定哈希、STALE 检测、authorize 集成。"""
import hashlib
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

import style_revise as rv
from authorize import Authorizer, TaskContext


def _sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


class StyleReviseTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "chapters", "drafts"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "analysis", "style"), exist_ok=True)
        self.ch, self.cyc, self.task = "CH1", "TA1", "style-revise-1"
        self.draft = "肖凡握紧刀柄。事实上他必须前进。他在雪地里奔跑。一股莫名寒意袭来。"

    def _persist(self, draft, rules=None, prev=None):
        d = rv.ai_revise(self.ch, self.cyc, self.task, draft,
                         protected_manifest_sha256="m123",
                         applied_style_rules=rules, previous_result=prev)
        rv.persist(d, self.root, d and self._cand(draft, rules), self.ch, self.cyc, self.task)
        return d

    def _cand(self, draft, rules):
        # 复算候选文本（与 ai_revise 内部变换一致）
        from style_revise import _apply_rule_transforms
        t, _ = _apply_rule_transforms(draft, rules)
        return t

    def test_only_writes_analysis_style_not_chapters(self):
        d = rv.ai_revise(self.ch, self.cyc, self.task, self.draft, protected_manifest_sha256="m1")
        rv.persist(d, self.root, self.draft, self.ch, self.cyc, self.task)
        cand = os.path.join(self.root, "analysis", "style", self.ch, self.cyc, "revision-candidate.md")
        res = os.path.join(self.root, "analysis", "style", self.ch, self.cyc,
                           "%s.revision-result.json" % self.task)
        self.assertTrue(os.path.exists(cand))
        self.assertTrue(os.path.exists(res))
        # chapters/ 不应被触及
        for base, _, files in os.walk(os.path.join(self.root, "chapters")):
            self.assertEqual(files, [], "chapters/ must stay untouched: %s" % files)

    def test_binds_source_draft_sha256(self):
        d = rv.ai_revise(self.ch, self.cyc, self.task, self.draft, protected_manifest_sha256="m1")
        self.assertEqual(d["source_draft_sha256"], _sha(self.draft))
        self.assertEqual(d["candidate_sha256"], _sha(self.draft))  # 无规则 → 候选==草稿
        self.assertFalse(d["stale"])

    def test_stale_when_draft_changes(self):
        first = rv.ai_revise(self.ch, self.cyc, self.task, self.draft, protected_manifest_sha256="m1")
        new_draft = self.draft + "新的一句改变了草稿。"
        second = rv.ai_revise(self.ch, self.cyc, self.task, new_draft,
                              protected_manifest_sha256="m1", previous_result=first)
        self.assertTrue(second["stale"])
        self.assertNotEqual(second["source_draft_sha256"], first["source_draft_sha256"])

    def test_applies_style_rules_and_records_changes(self):
        rules = [{"rule_id": "R1", "rule_type": "style_target", "kind": "meta_commentary"}]
        d = rv.ai_revise(self.ch, self.cyc, self.task, self.draft,
                         protected_manifest_sha256="m1", applied_style_rules=rules)
        cand, changes = rv._apply_rule_transforms(self.draft, rules)
        self.assertIn("事实上", self.draft)
        self.assertNotIn("事实上", cand)
        self.assertGreater(len(changes), 0)
        self.assertEqual(d["applied_style_rules"], ["R1"])

    def test_authorize_style_revise_allowed_and_denied(self):
        auth = Authorizer()  # 无 Broker 密钥，不签发 chapters capability
        cand_path = os.path.join(self.root, "analysis", "style", self.ch, self.cyc, "revision-candidate.md")
        res = [{"canonical_path": cand_path, "expected_sha256": "absent"}]

        ctx_ok = TaskContext(task_id=self.task, actor_id="A", session_ready=True,
                              subagent_policy="denied", lease_owner="A", state="RUNNING")
        r = auth.authorize("style_revise", ctx_ok, resources=res, env={"root": self.root})
        self.assertTrue(r.allowed, r.failed)
        self.assertIsNone(r.capability)  # 非 chapters 写，不签发 Broker capability

        # 非 lease owner → 拒绝
        ctx_bad = TaskContext(task_id=self.task, actor_id="A", session_ready=True,
                               subagent_policy="denied", lease_owner="OTHER", state="RUNNING")
        r2 = auth.authorize("style_revise", ctx_bad, resources=res, env={"root": self.root})
        self.assertFalse(r2.allowed)
        self.assertIn("lease_owner", [f["check"] for f in r2.failed])

        # 路径越界（写到 chapters）→ 拒绝
        bad_path = os.path.join(self.root, "chapters", "drafts", "CH1.md")
        r3 = auth.authorize("style_revise",
                            TaskContext(task_id=self.task, actor_id="A", session_ready=True,
                                        subagent_policy="denied", lease_owner="A", state="RUNNING"),
                            resources=[{"canonical_path": bad_path, "expected_sha256": "absent"}],
                            env={"root": self.root})
        self.assertFalse(r3.allowed)
        self.assertIn("candidate_path_permission", [f["check"] for f in r3.failed])


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""#21 回归：风格规则候选审批原型 + 事件日志凭证 + 晋升链。"""
import hashlib
import os
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM_ROOT = os.path.dirname(HERE)
for _c in ("learning", "logs", "_common"):
    _p = os.path.join(PLATFORM_ROOT, "scripts", _c)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import event_log as el  # noqa: E402
import rule_review as rr  # noqa: E402
import style_extract as se  # noqa: E402
import authorize as az  # noqa: E402


BROKER_KEY = b"broker-signing-key-32bytes-long-1234567890"


def _key_provider():
    return el.KeyProvider(key=BROKER_KEY)


def _make_candidate(n_src=5):
    ex = se.StyleExtractor()
    srcs = []
    text = ("肖凡推开木门。冷风灌进来。他眯起眼，望向院中老槐。"
            "“走。”他只说了这一个字。夜色像潮水般漫过屋檐。")
    for i in range(n_src):
        srcs.append({"source_id": "SRC%d" % i, "text": text + (" 第%d卷尾声，风更冷。" % i)})
    return ex.extract(srcs, "RC1", "T1")[0]


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rv_")
        self.log_path = os.path.join(self.tmp, "task-events.log")
        self.elog = el.EventLog(self.log_path, _key_provider())

    def test_lifecycle_extracted_to_active(self):
        c = _make_candidate()
        rev = rr.RuleReviewer(self.elog)
        rev.submit_for_review(c)
        self.assertEqual(c["review_status"], "REVIEW_PENDING")
        rev.approve(c, "rev1", "reviewer", "RT1", reason="ok")
        self.assertEqual(c["review_status"], "APPROVED")
        rev.promote(c)
        self.assertEqual(c["review_status"], "ACTIVE")

    def test_rejected_is_terminal(self):
        c = _make_candidate()
        rev = rr.RuleReviewer(self.elog)
        rev.submit_for_review(c)
        rev.reject(c, "rev1", "reviewer", "RT1", reason="too specific")
        self.assertEqual(c["review_status"], "REJECTED")
        with self.assertRaises(rr.RuleReviewError):
            rev.promote(c)

    def test_approval_credential_references_event_log_hash(self):
        c = _make_candidate()
        rev = rr.RuleReviewer(self.elog)
        rev.submit_for_review(c)
        rev.approve(c, "rev1", "reviewer", "RT1")
        integ = c["integrity"]
        self.assertIsNotNone(integ)
        self.assertEqual(integ["canonicalization_version"], "1.0.0")
        # event_log_entry_hash 必须对应日志中真实存在的审批事件
        events = self.elog.read_events()
        matches = [e for e in events
                   if e.get("event_type") == "rule_review"
                   and e.get("details", {}).get("candidate_id") == c["candidate_id"]]
        self.assertEqual(len(matches), 1)
        self.assertEqual(integ["event_log_entry_hash"], el.event_hash(matches[0]))

    def test_promote_fails_if_log_tampered(self):
        c = _make_candidate()
        rev = rr.RuleReviewer(self.elog)
        rev.submit_for_review(c)
        rev.approve(c, "rev1", "reviewer", "RT1")
        # 篡改日志（破坏哈希链）
        with open(self.log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        lines[0] = lines[0].replace('"rule_review"', '"RULE_REVIEW_X"')
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        res = self.elog.verify()
        self.assertFalse(res["valid"])
        with self.assertRaises(rr.RuleReviewError):
            rev.promote(c)

    def test_source_withdrawal_revokes(self):
        c = _make_candidate()
        rev = rr.RuleReviewer(self.elog)
        rev.submit_for_review(c)
        rev.approve(c, "rev1", "reviewer", "RT1")
        rev.promote(c)
        self.assertEqual(c["review_status"], "ACTIVE")
        rev.revoke(c, reason="source withdrawn")
        self.assertEqual(c["review_status"], "REVOKED")

    def test_approve_requires_broker_key(self):
        # 无密钥的 EventLog -> 无法写审批事件
        nokey_elog = el.EventLog(self.log_path, el.KeyProvider())
        c = _make_candidate()
        rev = rr.RuleReviewer(nokey_elog)
        rev.submit_for_review(c)
        with self.assertRaises(el.SigningKeyUnavailable):
            rev.approve(c, "rev1", "reviewer", "RT1")

    def test_authorize_review_requires_reviewer_role(self):
        root = self.tmp
        analysis = os.path.join(root, "analysis", "style", "CH1", "T1")
        os.makedirs(analysis, exist_ok=True)
        target = os.path.join(analysis, "cand.json")
        resources = [{"role": "target", "canonical_path": target, "expected_sha256": "absent"}]

        # writer 角色 -> 拒绝
        auth_w = az.Authorizer()
        ctx_w = az.TaskContext(task_id="T1", actor_id="A", actor_role="writer",
                                 lease_owner="A", session_ready=True, subagent_policy="denied",
                                 state="REVIEW_PENDING")
        r_w = auth_w.authorize("review", ctx_w, resources=resources, env={"root": root})
        self.assertFalse(r_w.allowed)
        self.assertIn("reviewer_role", [f["check"] for f in r_w.failed])

        # reviewer 角色 + 路径合规 -> 放行
        auth_r = az.Authorizer()
        ctx_r = az.TaskContext(task_id="T1", actor_id="A", actor_role="reviewer",
                                lease_owner="A", session_ready=True, subagent_policy="denied",
                                state="REVIEW_PENDING")
        r_r = auth_r.authorize("review", ctx_r, resources=resources, env={"root": root})
        self.assertTrue(r_r.allowed, r_r.failed)

    def test_authorize_extract_candidate_path_only(self):
        root = self.tmp
        analysis = os.path.join(root, "analysis", "style", "CH1", "T1")
        os.makedirs(analysis, exist_ok=True)
        target = os.path.join(analysis, "cand.json")
        resources = [{"role": "target", "canonical_path": target, "expected_sha256": "absent"}]
        auth = az.Authorizer()
        ctx = az.TaskContext(task_id="T1", actor_id="A", actor_role="writer",
                              lease_owner="A", session_ready=True, subagent_policy="denied",
                              state="RUNNING")
        r = auth.authorize("extract", ctx, resources=resources, env={"root": root})
        self.assertTrue(r.allowed, r.failed)
        # 若路径落在 chapters/ 下 -> 拒
        bad = [{"role": "target", "canonical_path": os.path.join(root, "chapters", "drafts", "CH1.md"),
                "expected_sha256": "absent"}]
        r2 = auth.authorize("extract", ctx, resources=bad, env={"root": root})
        self.assertFalse(r2.allowed)
        self.assertIn("candidate_path_permission", [f["check"] for f in r2.failed])


if __name__ == "__main__":
    unittest.main(verbosity=2)

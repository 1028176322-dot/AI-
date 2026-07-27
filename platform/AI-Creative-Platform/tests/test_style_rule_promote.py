# -*- coding: utf-8 -*-
"""#10 style_rule_promote：晋升链完整循环、审批凭证校验、ACTIVE写入。"""
import json
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

import style_rule_promote as srp


class RulePromoteTest(unittest.TestCase):
    def setUp(self):
        self.store = tempfile.mkdtemp()
        self.lc = srp.RuleLifecycle(self.store)
        self.cid = "rule-cand-001"
        # 预置 APPROVED 态
        self.lc._set_state(self.cid, "APPROVED", metadata={"prev": True})

    def _cred(self, decision="approved"):
        return {
            "candidate_id": self.cid,
            "candidate_sha256": "abc123",
            "source_set_hash": "def456",
            "reviewer_id": "reviewer1",
            "reviewer_role": "reviewer",
            "review_task_id": "task-review-1",
            "session_id": "sess-1",
            "decision": decision,
            "approved_rule_ids": ["r1"],
            "reason": "good style",
            "approved_at": 1000.0,
            "payload_sha256": None,
            "event_log_ref": "log1",
            "event_log_entry_hash": "evt1",
        }

    def _fix_payload(self, cred):
        payload = {k: v for k, v in cred.items()
                   if k not in ("payload_sha256", "event_log_ref", "event_log_entry_hash")}
        import hashlib, json
        cred["payload_sha256"] = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        return cred

    def test_validate_credential_valid(self):
        cred = self._fix_payload(self._cred())
        ok, errs = srp.validate_approval_credential(cred)
        self.assertTrue(ok, errs)

    def test_validate_credential_missing_field(self):
        ok, errs = srp.validate_approval_credential({})
        self.assertFalse(ok)
        self.assertTrue(any("missing" in e for e in errs))

    def test_validate_credential_bad_role(self):
        cred = self._fix_payload(self._cred())
        cred["reviewer_role"] = "writer"
        ok, errs = srp.validate_approval_credential(cred)
        self.assertFalse(ok)

    def test_validate_credential_payload_mismatch(self):
        cred = self._cred()
        cred["payload_sha256"] = "bad_hash"
        ok, errs = srp.validate_approval_credential(cred)
        self.assertFalse(ok)

    def test_promote_approved_to_promotion_eligible(self):
        cred = self._fix_payload(self._cred())
        result = srp.promote(self.cid, cred, self.lc)
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "PROMOTION_ELIGIBLE")
        self.assertEqual(self.lc.get_state(self.cid), "PROMOTION_ELIGIBLE")

    def test_promote_rejected(self):
        cred = self._fix_payload(self._cred(decision="rejected"))
        result = srp.promote(self.cid, cred, self.lc)
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "REJECTED")

    def test_follow_promote_to_promoted(self):
        self.lc._set_state(self.cid, "PROMOTION_ELIGIBLE")
        result = srp.follow_promote(self.cid, self.lc)
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "PROMOTED")

    def test_activate_writes_style_card(self):
        self.lc._set_state(self.cid, "PROMOTED")
        card_dir = tempfile.mkdtemp()
        card_path = os.path.join(card_dir, "activated.json")
        rule_data = {"rule_id": "r1", "value": "use short sentences"}
        result = srp.activate(self.cid, self.lc, rule_data=rule_data,
                               style_card_path=card_path)
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "ACTIVE")
        self.assertTrue(os.path.exists(card_path))
        with open(card_path, "r", encoding="utf-8") as f:
            entries = json.load(f)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["status"], "ACTIVE")

    def test_suspend_and_revoke(self):
        self.lc._set_state(self.cid, "ACTIVE")
        r = srp.suspend(self.cid, self.lc, reason="testing")
        self.assertTrue(r["ok"])
        self.assertEqual(self.lc.get_state(self.cid), "SUSPENDED")
        self.lc._set_state(self.cid, "ACTIVE")
        r2 = srp.revoke(self.cid, self.lc, reason="bad rule")
        self.assertTrue(r2["ok"])
        self.assertEqual(self.lc.get_state(self.cid), "REVOKED")


if __name__ == "__main__":
    unittest.main()

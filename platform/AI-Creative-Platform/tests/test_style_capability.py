# -*- coding: utf-8 -*-
"""#18 回归：多资源能力令牌（发行/校验/单次消费/过期/签名篡改/资源角色缺失/持久化）。"""
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM_ROOT = os.path.dirname(HERE)
for _child in os.listdir(os.path.join(PLATFORM_ROOT, "scripts")):
    _p = os.path.join(PLATFORM_ROOT, "scripts", _child)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import capability as cap  # noqa: E402
from capability import (issue, verify, consume, CapabilityStore, CapabilityError,  # noqa: E402
                        load_required_roles)

KEY = b"cap-key-32bytes-long-abcdefghijklmnop"


class CapabilityTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="cap_")
        self.store = CapabilityStore(os.path.join(self.root, "consumed.jsonl"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _tok(self, op="apply"):
        roles = load_required_roles()[op]
        res = [{"role": r, "canonical_path": "p/%s.md" % r, "expected_sha256": "deadbeef"}
               for r in roles]
        return issue("T1", "S1", "A", op, res, "POLICYSHA", KEY)

    def test_issue_verify(self):
        tok = self._tok("apply")
        ok, why = verify(tok, KEY, self.store)
        self.assertTrue(ok, why)

    def test_single_use_consume(self):
        tok = self._tok("apply")
        self.assertTrue(verify(tok, KEY, self.store)[0])
        consume(tok, self.store)
        ok, why = verify(tok, KEY, self.store)
        self.assertFalse(ok)
        self.assertEqual(why, "already consumed (single_use)")

    def test_expired(self):
        tok = self._tok("apply")
        tok["expires_at"] = time.time() - 1
        ok, why = verify(tok, KEY, self.store)
        self.assertFalse(ok)
        self.assertEqual(why, "expired")

    def test_signature_tamper(self):
        tok = self._tok("apply")
        tok["nonce"] = "tampered"
        ok, why = verify(tok, KEY, self.store)
        self.assertFalse(ok)
        self.assertEqual(why, "signature mismatch")

    def test_missing_resource_role(self):
        with self.assertRaises(CapabilityError):
            issue("T1", "S1", "A", "apply",
                  [{"role": "source", "canonical_path": "p.md", "expected_sha256": "x"}],
                  "P", KEY)

    def test_unknown_operation(self):
        with self.assertRaises(CapabilityError):
            issue("T1", "S1", "A", "frobnicate", [], "P", KEY)

    def test_store_persistence(self):
        tok = self._tok("apply")
        consume(tok, self.store)
        store2 = CapabilityStore(self.store.path)
        self.assertTrue(store2.is_consumed(tok["capability_id"]))

    def test_verify_resources_absent_but_exists(self):
        p = os.path.join(self.root, "target.md")
        open(p, "w", encoding="utf-8").write("data")
        tok = issue("T1", "S1", "A", "chapter_write",
                    [{"role": "target", "canonical_path": p, "expected_sha256": "absent"}],
                    "P", KEY)
        ok, why = cap.verify_resources(tok)
        self.assertFalse(ok, why)


if __name__ == "__main__":
    unittest.main(verbosity=2)

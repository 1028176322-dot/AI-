# -*- coding: utf-8 -*-
"""#18 回归：不可变事件日志（哈希链 / 链头锚定 / 篡改检测 / 无密钥拒绝）。"""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM_ROOT = os.path.dirname(HERE)
for _child in os.listdir(os.path.join(PLATFORM_ROOT, "scripts")):
    _p = os.path.join(PLATFORM_ROOT, "scripts", _child)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import event_log  # noqa: E402
from event_log import EventLog, KeyProvider, SigningKeyUnavailable  # noqa: E402

KEY = b"broker-signing-key-32bytes-long-1234567890"


class EventLogTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="evlog_")
        self.log = os.path.join(self.root, "task-events.log")
        self.el = EventLog(self.log, KeyProvider(key=KEY))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_append_verify_ok(self):
        self.el.append("create", "actor1", "T1", operation="create")
        self.el.append("run", "actor1", "T1", operation="run")
        res = self.el.verify()
        self.assertTrue(res["valid"], res)
        self.assertEqual(res["checked"], 2)

    def test_seq_monotonic(self):
        self.el.append("create", "a", "T1")
        self.el.append("run", "a", "T1")
        self.el.append("complete", "a", "T1")
        self.assertEqual([e["seq"] for e in self.el._load()], [1, 2, 3])

    def test_tamper_detected(self):
        self.el.append("create", "actor1", "T1")
        self.el.append("run", "actor1", "T1")
        with open(self.log, "r", encoding="utf-8") as f:
            lines = f.readlines()
        lines[0] = lines[0].replace('"actor1"', '"actorX"')
        with open(self.log, "w", encoding="utf-8") as f:
            f.writelines(lines)
        res = self.el.verify()
        self.assertFalse(res["valid"], res)
        self.assertIn("signature mismatch", res["error"])

    def test_no_key_refuses_append(self):
        el = EventLog(self.log, KeyProvider())  # 无密钥
        with self.assertRaises(SigningKeyUnavailable):
            el.append("create", "a", "T1")

    def test_chain_head_anchor(self):
        self.el.append("create", "a", "T1")
        self.el.append("run", "a", "T1")
        self.el.anchor()
        res = self.el.verify()
        self.assertTrue(res["valid"], res)
        self.assertTrue(res["anchor_checked"])
        # 篡改最后事件 -> 链头不一致
        with open(self.log, "r", encoding="utf-8") as f:
            lines = f.readlines()
        lines[-1] = lines[-1].replace('"actor_id": "a"', '"actor_id": "Z"')
        with open(self.log, "w", encoding="utf-8") as f:
            f.writelines(lines)
        res = self.el.verify()
        self.assertFalse(res["valid"], res)


if __name__ == "__main__":
    unittest.main(verbosity=2)

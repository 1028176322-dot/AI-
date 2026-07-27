# -*- coding: utf-8 -*-
"""#23 chapter_publish：PUBLISH_READY / STALE 绑定校验、产合规 dict、authorize 门禁。"""
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

import chapter_publish as cp
from authorize import Authorizer, TaskContext


class ChapterPublishTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "chapters", "drafts"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "chapters", "approved"), exist_ok=True)
        self.ch, self.cyc, self.task = "CH1", "TA1", "publish-1"
        self.draft = "肖凡握紧刀柄。他在雪地里奔跑。枪声划破夜空。那一年是一三二七年。"
        self.draft_sha = cp._sha256(self.draft)

    def test_publish_ready_when_bindings_match(self):
        """所有绑定齐全 → PUBLISH_READY"""
        d = cp.prepare_publish(self.ch, self.cyc, self.task,
                                self.draft, self.draft_sha,
                                nkb_revision="N1",
                                nkb_snapshot_sha256="nkb_sha_123",
                                outline_sha256="out_sha_456",
                                protected_manifest_sha256="manifest_sha_789",
                                style_guidance_sha256="style_sha_abc",
                                chapter_review_report_sha256="review_sha_def")
        self.assertEqual(d["status"], "PUBLISH_READY")
        ok, errs = cp.validate_publish_result(d)
        self.assertTrue(ok, errs)
        self.assertEqual(d["draft_sha256"], self.draft_sha)

    def test_stale_when_draft_changed(self):
        """草稿已变 → STALE"""
        different = "完全不同了的草稿内容。"
        d = cp.prepare_publish(self.ch, self.cyc, self.task,
                                different, self.draft_sha,
                                nkb_revision="N1",
                                nkb_snapshot_sha256="nkb_sha_123",
                                outline_sha256="out_sha_456",
                                protected_manifest_sha256="manifest_sha_789",
                                style_guidance_sha256="style_sha_abc")
        self.assertEqual(d["status"], "STALE")
        self.assertIn("draft sha changed", d.get("error", ""))

    def test_stale_when_nkb_binding_missing(self):
        """nkb_revision 为空 → STALE"""
        d = cp.prepare_publish(self.ch, self.cyc, self.task,
                                self.draft, self.draft_sha,
                                nkb_revision="",
                                nkb_snapshot_sha256="",
                                outline_sha256="",
                                protected_manifest_sha256="")
        self.assertEqual(d["status"], "STALE")

    def test_publish_result_includes_mode_and_version(self):
        d = cp.prepare_publish(self.ch, self.cyc, self.task,
                                self.draft, self.draft_sha,
                                nkb_revision="N1",
                                nkb_snapshot_sha256="nkb_sha",
                                outline_sha256="out_sha",
                                protected_manifest_sha256="manifest_sha",
                                style_guidance_sha256="style_sha",
                                final_regression_mode="post_apply",
                                final_regression_config_version="1.2.0")
        self.assertEqual(d["status"], "PUBLISH_READY")
        self.assertEqual(d["final_regression_mode"], "post_apply")
        self.assertEqual(d["final_regression_config_version"], "1.2.0")

    def test_authorize_publish_gates_path(self):
        auth = Authorizer()
        src_path = os.path.join(self.root, "chapters", "drafts", "CH1.md")
        tgt_path = os.path.join(self.root, "chapters", "approved", "CH1.md")
        res = [
            {"canonical_path": src_path, "expected_sha256": "absent", "role": "source"},
            {"canonical_path": tgt_path, "expected_sha256": "absent", "role": "target"},
        ]
        ctx = TaskContext(task_id=self.task, actor_id="A", session_ready=True,
                          subagent_policy="denied", lease_owner="A",
                          state="PUBLISH_READY",
                          dependency_binding=True)
        r = auth.authorize("publish", ctx, resources=res, env={"root": self.root})
        self.assertTrue(r.allowed, r.failed)


if __name__ == "__main__":
    unittest.main()

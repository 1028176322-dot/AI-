# -*- coding: utf-8 -*-
"""#22 manifest_build：产合规 manifest、冲突裁决 NKB 优先、唯一生产者、不写 chapters。"""
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

import manifest_build as mb
from authorize import Authorizer, TaskContext


def _sha(t):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


class ManifestBuildTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "chapters", "drafts"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "analysis", "style"), exist_ok=True)
        self.ch, self.cyc, self.task = "CH1", "TA1", "manifest-build-1"
        self.draft = "肖凡握紧刀柄。他在雪地里奔跑。忽然一阵枪响划破夜空。那一年是一三二七年。"

    def test_produces_compliant_manifest(self):
        res = mb.build_manifest(self.ch, self.cyc, self.task, self.draft,
                                nkb_snapshot={"revision": "N1"},
                                outline_text="章纲：雪夜弃婴。", builder_version="1.0.0")
        self.assertEqual(res["status"], "MANIFEST_READY")
        m = res["manifest"]
        ok, errs = mb.validate_manifest(m)
        self.assertTrue(ok, errs)
        self.assertEqual(m["source_draft_sha256"], _sha(self.draft))
        self.assertIn("hard_preserve", m)
        self.assertIn("functional_preserve", m)
        self.assertIn("soft_preserve", m)
        self.assertTrue(len(m["hard_preserve"]["items"]) > 0)

    def test_persist_only_analysis_style_not_chapters(self):
        res = mb.build_manifest(self.ch, self.cyc, self.task, self.draft,
                                nkb_snapshot={"revision": "N1"})
        out = mb.persist(res, self.root, self.ch, self.cyc)
        self.assertTrue(os.path.exists(out["path"]))
        self.assertIn("analysis/style", out["path"].replace("\\", "/"))
        for base, _, files in os.walk(os.path.join(self.root, "chapters")):
            self.assertEqual(files, [], "chapters/ must stay untouched")

    def test_nkb_conflict_resolved_nkb_wins(self):
        # 草稿与 NKB 硬事实冲突（年份不符）→ MANIFEST_CONFLICT，且裁决 nkb_wins
        facts = [{"text": "一三二七年", "expected": "一三二六年"}]
        res = mb.build_manifest(self.ch, self.cyc, self.task, self.draft,
                                nkb_snapshot={"revision": "N1"}, nkb_hard_facts=facts)
        self.assertEqual(res["status"], "MANIFEST_CONFLICT")
        self.assertEqual(len(res["conflicts"]), 1)
        self.assertEqual(res["conflicts"][0]["resolution"], "nkb_wins")
        self.assertEqual(res["conflicts"][0]["expected"], "一三二六年")

    def test_authorize_manifest_build_gates_path(self):
        auth = Authorizer()
        mpath = os.path.join(self.root, "analysis", "style", self.ch, self.cyc, "protected-manifest.yaml")
        res = [{"canonical_path": mpath, "expected_sha256": "absent"}]
        ctx_ok = TaskContext(task_id=self.task, actor_id="A", session_ready=True,
                              subagent_policy="denied", lease_owner="A", state="RUNNING")
        r = auth.authorize("manifest_build", ctx_ok, resources=res, env={"root": self.root})
        self.assertTrue(r.allowed, r.failed)

        bad = os.path.join(self.root, "chapters", "drafts", "CH1.md")
        r2 = auth.authorize("manifest_build",
                            TaskContext(task_id=self.task, actor_id="A", session_ready=True,
                                        subagent_policy="denied", lease_owner="A", state="RUNNING"),
                            resources=[{"canonical_path": bad, "expected_sha256": "absent"}],
                            env={"root": self.root})
        self.assertFalse(r2.allowed)
        self.assertIn("candidate_path_permission", [f["check"] for f in r2.failed])

    def test_manifest_sha256_stable(self):
        res = mb.build_manifest(self.ch, self.cyc, self.task, self.draft,
                                nkb_snapshot={"revision": "N1"})
        s1 = mb.manifest_sha256(res["manifest"])
        res2 = mb.build_manifest(self.ch, self.cyc, self.task, self.draft,
                                 nkb_snapshot={"revision": "N1"})
        self.assertEqual(s1, mb.manifest_sha256(res2["manifest"]))


if __name__ == "__main__":
    unittest.main()

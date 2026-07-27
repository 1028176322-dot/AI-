# -*- coding: utf-8 -*-
"""#18 回归：authorize() 分操作策略（各 operation 放行/拒绝分支 + 子Agent禁用 + capability 发放）。"""
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

import authorize  # noqa: E402
import capability as capmod  # noqa: E402
from authorize import Authorizer, TaskContext, RealFS  # noqa: E402

KEY = b"cap-key-32bytes-long-abcdefghijklmnop"


class AuthorizeTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="auth_")
        self.auth = Authorizer(capability_key=KEY, issuer=capmod)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _ctx(self, **kw):
        return TaskContext(**kw)

    # -- create -----------------------------------------------------------
    def test_create_allowed(self):
        ctx = self._ctx(task_id="T1", executor_role="writer", session_ready=True)
        self.assertTrue(self.auth.authorize("create", ctx).allowed)

    def test_create_denied_no_session(self):
        ctx = self._ctx(task_id="T1", executor_role="writer", session_ready=False)
        r = self.auth.authorize("create", ctx)
        self.assertFalse(r.allowed)
        self.assertIn("session_ready", [f["check"] for f in r.failed])

    def test_create_denied_bad_role(self):
        ctx = self._ctx(task_id="T1", executor_role="dragon", session_ready=True)
        r = self.auth.authorize("create", ctx)
        self.assertFalse(r.allowed)
        self.assertIn("creator_can_assign_role", [f["check"] for f in r.failed])

    # -- claim ------------------------------------------------------------
    def test_claim_role_mismatch(self):
        ctx = self._ctx(task_id="T1", actor_id="A", executor_id="B",
                        session_ready=True, state="CREATED")
        r = self.auth.authorize("claim", ctx)
        self.assertFalse(r.allowed)
        self.assertIn("actor_matches_executor", [f["check"] for f in r.failed])

    def test_claim_ok(self):
        ctx = self._ctx(task_id="T1", actor_id="A", executor_id="A",
                        session_ready=True, state="CREATED")
        self.assertTrue(self.auth.authorize("claim", ctx).allowed)

    # -- run (+ 子Agent 禁用) --------------------------------------------
    def test_run_ok(self):
        ctx = self._ctx(task_id="T1", actor_id="A", actor_role="writer", executor_role="writer",
                        session_ready=True, subagent_policy="denied", state="CLAIMED",
                        lease_owner="A", lease_expires_at=0.0)
        self.assertTrue(self.auth.authorize("run", ctx).allowed)

    def test_run_subagent_allowed_denied(self):
        ctx = self._ctx(task_id="T1", actor_id="A", actor_role="writer", executor_role="writer",
                        session_ready=True, subagent_policy="allowed", state="CLAIMED",
                        lease_owner="A")
        r = self.auth.authorize("run", ctx)
        self.assertFalse(r.allowed)
        self.assertIn("subagent_policy_denied", [f["check"] for f in r.failed])

    def test_run_lease_expired(self):
        ctx = self._ctx(task_id="T1", actor_id="A", actor_role="writer", executor_role="writer",
                        session_ready=True, subagent_policy="denied", state="CLAIMED",
                        lease_owner="A", lease_expires_at=1.0)
        r = self.auth.authorize("run", ctx)
        self.assertFalse(r.allowed)
        self.assertIn("lease_owner", [f["check"] for f in r.failed])

    # -- complete / resume ------------------------------------------------
    def test_complete_needs_authority(self):
        ctx = self._ctx(task_id="T1", actor_id="A", actor_role="writer", executor_role="writer",
                        session_ready=True, subagent_policy="denied", state="RUNNING",
                        lease_owner="A", completion_authority="operator")
        r = self.auth.authorize("complete", ctx)
        self.assertFalse(r.allowed)
        self.assertIn("completion_authority", [f["check"] for f in r.failed])

    def test_complete_ok(self):
        ctx = self._ctx(task_id="T1", actor_id="op", actor_role="operator", executor_role="writer",
                        session_ready=True, subagent_policy="denied", state="RUNNING",
                        lease_owner="op", completion_authority="operator")
        self.assertTrue(self.auth.authorize("complete", ctx).allowed)

    def test_resume_ok_and_denied(self):
        ctx = self._ctx(task_id="T1", actor_id="A", actor_role="writer", executor_role="writer",
                        session_ready=True, subagent_policy="denied", state="PAUSED", lease_owner="A")
        self.assertTrue(self.auth.authorize("resume", ctx).allowed)
        ctx.state = "CREATED"
        self.assertFalse(self.auth.authorize("resume", ctx).allowed)

    # -- candidate_create（路径权限） ------------------------------------
    def test_candidate_create_path_forbidden(self):
        bad = [{"role": "target",
                "canonical_path": os.path.join(self.root, "chapters", "drafts", "CH1.md"),
                "expected_sha256": "absent"}]
        ctx = self._ctx(task_id="T1", actor_id="A", session_ready=True, subagent_policy="denied",
                        lease_owner="A", state="RUNNING")
        r = self.auth.authorize("candidate_create", ctx, resources=bad, env={"root": self.root})
        self.assertFalse(r.allowed)
        self.assertIn("candidate_path_permission", [f["check"] for f in r.failed])

    def test_candidate_create_ok_issues_capability(self):
        good = [{"role": "target",
                 "canonical_path": os.path.join(self.root, "analysis", "style", "CH1", "TA1",
                                                "revision-candidate.md"),
                 "expected_sha256": "absent"}]
        ctx = self._ctx(task_id="T1", actor_id="A", session_ready=True, subagent_policy="denied",
                        lease_owner="A", state="RUNNING")
        r = self.auth.authorize("candidate_create", ctx, resources=good, env={"root": self.root})
        self.assertTrue(r.allowed, r.failed)
        self.assertIsNotNone(r.capability)

    # -- apply（状态 + 多资源哈希 + 路径 + capability） ------------------
    def _apply_resources(self, state):
        dd = os.path.join(self.root, "chapters", "drafts")
        ad = os.path.join(self.root, "analysis", "style", "CH1", "TA1")
        os.makedirs(dd, exist_ok=True)
        os.makedirs(ad, exist_ok=True)
        src = os.path.join(dd, "CH1.md")
        open(src, "w", encoding="utf-8").write("hello")
        cand = os.path.join(ad, "revision-candidate.md")
        open(cand, "w", encoding="utf-8").write("hello2")
        fs = RealFS()
        sha_src = fs.sha256(src)
        sha_cand = fs.sha256(cand)
        res = [
            {"role": "source", "canonical_path": src, "expected_sha256": sha_src},
            {"role": "target", "canonical_path": src, "expected_sha256": sha_src},
            {"role": "candidate_or_backup", "canonical_path": cand, "expected_sha256": sha_cand},
        ]
        ctx = self._ctx(task_id="T1", actor_id="A", session_ready=True, subagent_policy="denied",
                        lease_owner="A", state=state)
        return ctx, res, {"root": self.root, "fs": fs}

    def test_apply_missing_state(self):
        ctx, res, env = self._apply_resources("RUNNING")
        r = self.auth.authorize("apply", ctx, resources=res, env=env)
        self.assertFalse(r.allowed)
        self.assertIn("APPLY_READY", [f["check"] for f in r.failed])

    def test_apply_ok_issues_capability(self):
        ctx, res, env = self._apply_resources("APPLY_READY")
        r = self.auth.authorize("apply", ctx, resources=res, env=env)
        self.assertTrue(r.allowed, r.failed)
        self.assertIsNotNone(r.capability)
        self.assertEqual(r.capability["operation"], "apply")
        roles = sorted(x["role"] for x in r.capability["resources"])
        self.assertEqual(roles, ["candidate_or_backup", "source", "target"])

    # -- publish（依赖绑定） ---------------------------------------------
    def test_publish_dependency_binding(self):
        dd = os.path.join(self.root, "chapters", "drafts")
        ad = os.path.join(self.root, "chapters", "approved")
        os.makedirs(dd, exist_ok=True)
        os.makedirs(ad, exist_ok=True)
        src = os.path.join(dd, "CH1.md")
        open(src, "w", encoding="utf-8").write("x")
        approved = os.path.join(ad, "CH1.md")  # 尚未创建 -> absent 允许
        sha = RealFS().sha256(src)
        res = [
            {"role": "source", "canonical_path": src, "expected_sha256": sha},
            {"role": "target", "canonical_path": approved, "expected_sha256": "absent"},
        ]
        ctx = self._ctx(task_id="T1", actor_id="A", session_ready=True, subagent_policy="denied",
                        lease_owner="A", state="PUBLISH_READY", dependency_binding=True)
        env = {"root": self.root, "fs": RealFS()}
        self.assertTrue(self.auth.authorize("publish", ctx, resources=res, env=env).allowed)
        ctx.dependency_binding = False
        r2 = self.auth.authorize("publish", ctx, resources=res, env=env)
        self.assertFalse(r2.allowed)
        self.assertIn("dependency_binding", [f["check"] for f in r2.failed])


if __name__ == "__main__":
    unittest.main(verbosity=2)

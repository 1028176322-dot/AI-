# -*- coding: utf-8 -*-
"""#19 回归：受控写 Broker / localhost IPC / 5 项禁用测试 / NTFS ACL dry-run。

5 项禁用测试（不可绕过验证）：
  test_disabled_no_write_without_authorization
  test_disabled_capability_single_use_replay
  test_disabled_path_symlink_and_traversal
  test_disabled_write_to_forbidden_root
  (第 5 项在 test_style_no_subagent.py: test_disabled_subagent_invocation_in_execution_layer)
"""
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM_ROOT = os.path.dirname(HERE)
for _child in os.listdir(os.path.join(PLATFORM_ROOT, "scripts")):
    _p = os.path.join(PLATFORM_ROOT, "scripts", _child)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import broker as bmod  # noqa: E402
from authorize import TaskContext, RealFS  # noqa: E402
import capability as capmod  # noqa: E402

KEY = b"broker-key-32bytes-long-abcdefghijklmno"


def _ctx(state, actor="A", lease_future=True):
    return TaskContext(
        task_id="T1", actor_id=actor, actor_role="writer", executor_id=actor,
        executor_role="writer", state=state, session_id="S1", session_ready=True,
        subagent_policy="denied", lease_owner=actor,
        lease_expires_at=(time.time() + 3600) if lease_future else (time.time() - 1),
        completion_authority="operator", outputs_valid=True, outputs_consistent=True,
        dependency_binding=True,
    )


class BrokerBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="broker_")
        self.drafts = os.path.join(self.root, "chapters", "drafts")
        self.approved = os.path.join(self.root, "chapters", "approved")
        self.analysis = os.path.join(self.root, "analysis", "style")
        self.nkb = os.path.join(self.root, "nkb")  # 越权根（禁止写）
        for d in (self.drafts, self.approved, self.analysis, self.nkb):
            os.makedirs(d, exist_ok=True)
        # Production defaults remain strict. These legacy fixtures predate the
        # complete dependency bundle and therefore opt out explicitly.
        self.writer = bmod.ControlledWriter(
            self.root, key_vault=bmod.BrokerKeyVault(key=KEY),
            strict_dependencies=False)
        self.fs = RealFS()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _seed_draft(self, name="CH1.md", content="original draft"):
        p = os.path.join(self.drafts, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return p, self.fs.sha256(p)

    def _seed_candidate(self, content="revised"):
        p = os.path.join(self.analysis, "CH1", "TA1", "revision-candidate.md")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return p, self.fs.sha256(p)

    def _apply_resources(self, draft_path, draft_hash, cand_path, cand_hash):
        return [
            {"role": "source", "canonical_path": draft_path, "expected_sha256": draft_hash},
            {"role": "target", "canonical_path": draft_path, "expected_sha256": draft_hash},
            {"role": "candidate_or_backup", "canonical_path": cand_path, "expected_sha256": cand_hash},
        ]


class TrustedSessionCompatibilityTest(unittest.TestCase):
    def test_current_agent_runtime_is_accepted(self):
        session = {
            "agent_runtime": {
                "agent_mode": "single",
                "subagents_enabled": False,
                "delegation_enabled": False,
                "background_execution_enabled": False,
                "max_active_agents": 1,
            },
        }
        self.assertTrue(bmod._trusted_session_policy(
            session, {"loaded": {"project_yaml": True}}))

    def test_legacy_runtime_policy_is_accepted(self):
        session = {
            "runtime_policy": {
                "agent_mode": "single",
                "subagents_enabled": False,
                "delegation_allowed": False,
                "parallel_agents_allowed": False,
                "max_active_agents": 1,
            },
            "ready": True,
        }
        self.assertTrue(
            bmod._trusted_session_policy(session, {}))

    def test_missing_policy_fails_closed(self):
        with self.assertRaisesRegex(
                bmod.BrokerError, "single-agent policy"):
            bmod._trusted_session_policy({"ready": True}, {})


class HappyPathTest(BrokerBase):
    def test_happy_apply_via_broker(self):
        dp, dh = self._seed_draft()
        cp, ch = self._seed_candidate()
        res = self.writer.request_write(
            "apply", _ctx("APPLY_READY"), self._apply_resources(dp, dh, cp, ch),
            "new content from broker")
        self.assertIn("event_id", res)
        with open(dp, encoding="utf-8") as _f:
            self.assertEqual(_f.read(), "new content from broker")
        # capability 已消费
        self.assertTrue(self.writer.cap_store.is_consumed(res["capability_id"]))
        # 不可变事件已记录
        ev = self.writer.event_log.verify()
        self.assertTrue(ev["valid"])
        self.assertGreaterEqual(ev["checked"], 1)


class IpcTest(BrokerBase):
    def test_ipc_authz_write_loop_and_forged_rejected(self):
        dp, dh = self._seed_draft()
        cp, ch = self._seed_candidate()
        srv = bmod.BrokerServer(
            self.writer, allow_legacy_test_context=True)
        port = srv.start()
        try:
            cli = bmod.BrokerClient(
                port=port, legacy_test_context=True)
            authz = cli.authz("apply", _ctx("APPLY_READY"),
                              self._apply_resources(dp, dh, cp, ch))
            self.assertTrue(authz["ok"], authz)
            cap = authz["capability"]
            self.assertEqual(cap["operation"], "apply")
            out = cli.write(cap, "ipc written content")
            self.assertTrue(out["ok"], out)
            with open(dp, encoding="utf-8") as _f:
                self.assertEqual(_f.read(), "ipc written content")

            # 伪造令牌（错误密钥签名）——客户端无密钥，无法伪造合法令牌
            forged = capmod.issue(
                task_id="T1", session_id="S1", actor_id="A", operation="apply",
                resources=self._apply_resources(dp, dh, cp, ch),
                policy_sha256="x", key=b"wrongwrongwrongwrongwrongwrongwrongwrong")
            bad = cli.write(forged, "evil")
            self.assertFalse(bad["ok"], "forged capability must be rejected")
        finally:
            srv.shutdown()


class DisabledTests(BrokerBase):
    def test_disabled_no_write_without_authorization(self):
        """授权拒绝时绝不写文件（无合法 capability）。"""
        dp, dh = self._seed_draft()
        cp, ch = self._seed_candidate()
        with self.assertRaises(bmod.BrokerError):
            self.writer.request_write(
                "apply", _ctx("RUNNING"),  # 非 APPLY_READY → 授权失败
                self._apply_resources(dp, dh, cp, ch), "should not be written")
        # 原稿未被改动
        with open(dp, encoding="utf-8") as stream:
            self.assertEqual(stream.read(), "original draft")

    def test_disabled_capability_single_use_replay(self):
        """capability 单次消费：重放同一令牌第二次被拒。"""
        dp, dh = self._seed_draft()
        cp, ch = self._seed_candidate()
        res = self.writer.authorizer.authorize(
            "apply", _ctx("APPLY_READY"), resources=self._apply_resources(dp, dh, cp, ch),
            env={"root": self.root, "fs": self.fs})
        self.assertTrue(res.allowed, res.failed)
        cap = res.capability
        first = self.writer._commit(cap, "first", "A", "S1", "T1")
        self.assertIn("event_id", first)
        with self.assertRaises(bmod.BrokerError):
            self.writer._commit(cap, "second", "A", "S1", "T1")

    def _issue(self, target_path, target_expected="absent"):
        """用 Broker 的密钥签发一个合法的 apply capability（target 可指向恶意路径）。"""
        dp, dh = self._seed_draft()
        cp, ch = self._seed_candidate()
        resources = [
            {"role": "source", "canonical_path": dp, "expected_sha256": dh},
            {"role": "target", "canonical_path": target_path, "expected_sha256": target_expected},
            {"role": "candidate_or_backup", "canonical_path": cp, "expected_sha256": ch},
        ]
        return capmod.issue(task_id="T1", session_id="S1", actor_id="A", operation="apply",
                            resources=resources, policy_sha256="x", key=KEY)

    def test_disabled_path_symlink_and_traversal(self):
        """符号链接与路径穿越均被拒（即便 capability 本身签名合法）。"""
        # ① 符号链接指向受控根之外
        outside = os.path.join(self.root, "escape.txt")
        with open(outside, "w", encoding="utf-8") as stream:
            stream.write("x")
        link = os.path.join(self.drafts, "evil_link.md")
        try:
            os.symlink(outside, link)
        except OSError as exc:
            # WinError 1314 is expected on Windows without symlink privilege.
            if getattr(exc, "winerror", None) != 1314:
                raise
        else:
            cap_link = self._issue(link, target_expected="absent")
            with self.assertRaises(bmod.PathEscalation):
                self.writer._commit(cap_link, "x", "A", "S1", "T1")
        # ② 路径穿越 ../
        traversal = os.path.join(self.drafts, "..", "escape.md")
        cap_trav = self._issue(traversal, target_expected="absent")
        with self.assertRaises(bmod.PathEscalation):
            self.writer._commit(cap_trav, "x", "A", "S1", "T1")

    def test_disabled_write_to_forbidden_root(self):
        """目标落在受控白名单之外（如 NKB 目录）被拒。"""
        forbidden = os.path.join(self.nkb, "canon.yaml")
        cap = self._issue(forbidden, target_expected="absent")
        with self.assertRaises(bmod.PathEscalation):
            self.writer._commit(cap, "x", "A", "S1", "T1")
        self.assertFalse(os.path.exists(forbidden))


class AclTest(BrokerBase):
    def test_ntfs_acl_dryrun_safe(self):
        """NTFS ACL 默认 dry-run：返回正确 icacls 命令且不实际变更。"""
        out = bmod.apply_ntfs_acl(self.drafts, self.approved, "SVC_TaskRunner", "SVC_ChapterWriter")
        self.assertFalse(out["applied"], "dry-run must not apply")
        cmds = out["commands"]
        # 2 directories × (grant writer / clear old deny / deny runner).
        self.assertEqual(len(cmds), 6)
        joined = "\n".join(cmds)
        self.assertIn("SVC_ChapterWriter", joined)
        self.assertIn("SVC_TaskRunner", joined)
        self.assertIn("(OI)(CI)M", joined)


if __name__ == "__main__":
    unittest.main(verbosity=2)

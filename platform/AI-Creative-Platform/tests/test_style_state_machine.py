# -*- coding: utf-8 -*-
"""#20 状态机回归 + 绕过测试（纲要 §2.9 / §2.8）。

覆盖：全部合法转换被接受、非法转换拒绝、CAS 防并发、FINAL_PASSED 仅 final-regression
可达、condition 强制、ROLLBACK_CONFLICT→BLOCKED、STALE 重诊、直接篡改状态文件被
verify_consistency 检出、事件日志签名篡改被 verify 检出。
"""
import os
import sys
import tempfile
import unittest

# 测试框架将 scripts/* 加入 sys.path；这里显式兜底
_THIS = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_THIS, "..", "scripts", "logs"),
           os.path.join(_THIS, "..", "scripts", "_common")):
    if _p not in sys.path:
        sys.path.insert(0, os.path.normpath(_p))

from state_machine import (StateMachine, CasConflict, IllegalTransition,  # noqa: E402
                            load_schema)
from event_log import EventLog, KeyProvider  # noqa: E402

_KEY = b"broker-signing-key-32bytes-long-1234567890"
_SCHEMA = os.path.normpath(os.path.join(
    _THIS, "..", "core", "learning", "schemas", "revision-candidate-state.schema.yaml"))


class TestStateMachine(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sm_")
        self.log_path = os.path.join(self.root, "task-events.log")
        self.el = EventLog(self.log_path, KeyProvider(key=_KEY))
        self.sm = StateMachine(schema_path=_SCHEMA, event_log=self.el,
                               state_dir=os.path.join(self.root, "state"), key=_KEY)

    # ------------------------------------------------------------------
    def _load_schema_transitions(self):
        s = load_schema(_SCHEMA)
        return s["transitions"]

    def test_schema_block_parsed(self):
        """SSOT 已被平台零依赖解析器正确解析（#20a 修复静默失败）。"""
        s = load_schema(_SCHEMA)
        self.assertEqual(s["initial"], "DRAFT_STABLE")
        self.assertIn("DRAFT_STABLE", s["states"])
        self.assertIn("PUBLISHED", s["states"])
        # 每条转换都是结构化的 dict（无垃圾单键）
        for t in s["transitions"]:
            self.assertIsInstance(t, dict)
            self.assertIn("from", t)
            self.assertIn("to", t)
            self.assertIn("via", t)

    def test_all_legal_transitions_accepted(self):
        """① 每条 SSOT 转换都能被 transition_state 接受（含种子边）。"""
        for i, t in enumerate(self._load_schema_transitions()):
            cid = "cycle-%d" % i
            frm, to, via = t["from"], t["to"], t["via"]
            cond = t.get("condition")
            # 前置：把周期置于 from 态（单元测试隔离每条边）
            self.sm._set_state(cid, frm)
            res = self.sm.transition_state(cid, frm, to, via, condition=cond,
                                           actor_id="A", task_id=cid)
            self.assertEqual(res["to"], to)
            self.assertEqual(self.sm.get_state(cid), to)

    def test_illegal_transition_rejected(self):
        """② 非法转换（不在 SSOT）被拒。"""
        # DRAFT_STABLE 不能直接到 APPLIED
        self.assertRaises(IllegalTransition,
                          self.sm.transition_state, "c1", "DRAFT_STABLE", "APPLIED",
                          "chapter-apply-revision", condition="cas_ok")
        # STRUCTURE_STABLE 不能到 DIAGNOSED（正确入口是经 MANIFEST_READY）
        self.sm._set_state("c2", "STRUCTURE_STABLE")
        self.assertRaises(IllegalTransition,
                          self.sm.transition_state, "c2", "STRUCTURE_STABLE", "DIAGNOSED",
                          "ai-diagnose")

    def test_cas_conflict(self):
        """③ CAS：旧 expected 的并发转换被拒。"""
        self.sm._set_state("c3", "STRUCTURE_STABLE")
        # 合法推进一次
        self.sm.transition_state("c3", "STRUCTURE_STABLE", "MANIFEST_BUILDING",
                                 "protected-manifest-build")
        # 另一个进程用旧快照（仍以为 STRUCTURE_STABLE）→ 冲突
        self.assertRaises(CasConflict,
                          self.sm.transition_state, "c3", "STRUCTURE_STABLE",
                          "MANIFEST_BUILDING", "protected-manifest-build")

    def test_final_passed_only_via_final_regression(self):
        """④ FINAL_PASSED 仅经 final-regression（via/condition 双约束）可达。"""
        self.sm._set_state("c4", "FINAL_CHECK_READY")
        # 伪造 via
        self.assertRaises(IllegalTransition,
                          self.sm.transition_state, "c4", "FINAL_CHECK_READY",
                          "FINAL_PASSED", "style-revise")
        # 正确 via 但错误 condition
        self.assertRaises(IllegalTransition,
                          self.sm.transition_state, "c4", "FINAL_CHECK_READY",
                          "FINAL_PASSED", "final-regression", condition="wrong")
        # 合法
        res = self.sm.transition_state("c4", "FINAL_CHECK_READY", "FINAL_PASSED",
                                       "final-regression", condition="pass")
        self.assertEqual(res["to"], "FINAL_PASSED")

    def test_condition_enforced(self):
        """⑤ APPLY_READY→APPLIED 必须有 condition=cas_ok。"""
        self.sm._set_state("c5", "APPLY_READY")
        self.assertRaises(IllegalTransition,
                          self.sm.transition_state, "c5", "APPLY_READY", "APPLIED",
                          "chapter-apply-revision", condition="wrong")
        res = self.sm.transition_state("c5", "APPLY_READY", "APPLIED",
                                       "chapter-apply-revision", condition="cas_ok")
        self.assertEqual(res["to"], "APPLIED")

    def test_rollback_conflict_then_blocked(self):
        """⑥ ROLLBACK_CONFLICT → BLOCKED 合法闭合（绝不覆盖新内容）。"""
        self.sm._set_state("c6", "ROLLBACK_READY")
        self.sm.transition_state("c6", "ROLLBACK_READY", "ROLLBACK_CONFLICT",
                                 "chapter-rollback-revision", condition="draft_changed")
        self.sm.transition_state("c6", "ROLLBACK_CONFLICT", "BLOCKED", "system")
        self.assertEqual(self.sm.get_state("c6"), "BLOCKED")

    def test_stale_rediagnose(self):
        """⑦ STALE 重诊入口合法。"""
        self.sm._set_state("c7", "APPLY_READY")
        self.sm.transition_state("c7", "APPLY_READY", "STALE",
                                 "dependency_change", condition="hash_or_dep_changed")
        self.sm.transition_state("c7", "STALE", "DIAGNOSED",
                                 "ai-diagnose", condition="re_diagnose")
        self.assertEqual(self.sm.get_state("c7"), "DIAGNOSED")

    def _advance_to_apply_ready(self, cid):
        steps = [
            ("DRAFT_STABLE", "STRUCTURE_STABLE", "structure-stability-gate", None),
            ("STRUCTURE_STABLE", "MANIFEST_BUILDING", "protected-manifest-build", None),
            ("MANIFEST_BUILDING", "MANIFEST_READY", "protected-manifest-build", "build_ok"),
            ("MANIFEST_READY", "DIAGNOSED", "ai-diagnose", None),
            ("DIAGNOSED", "CANDIDATE_CREATED", "style-revise", "has_issues"),
            ("CANDIDATE_CREATED", "FIDELITY_PASSED", "fidelity-review", "pass"),
            ("FIDELITY_PASSED", "QUALITY_PASSED", "style-quality-review", "pass"),
            ("QUALITY_PASSED", "APPLY_READY", "system", None),
        ]
        for frm, to, via, cond in steps:
            self.sm.transition_state(cid, frm, to, via, condition=cond,
                                     actor_id="A", task_id=cid)

    def test_verify_consistency_clean(self):
        """合法推进后 verify_consistency 一致。"""
        self._advance_to_apply_ready("c8")
        r = self.sm.verify_consistency("c8")
        self.assertTrue(r["consistent"], r)
        self.assertEqual(r["current_state"], "APPLY_READY")

    def test_tamper_state_file_detected(self):
        """⑧ 绕过 transition_state 直接改状态文件 → verify_consistency 检出。"""
        self._advance_to_apply_ready("c9")
        # 攻击者直接落地为 PUBLISHED（未经任何合法转换）
        self.sm._set_state("c9", "PUBLISHED")
        r = self.sm.verify_consistency("c9")
        self.assertFalse(r["consistent"], r)
        self.assertEqual(r["replayed"], "APPLY_READY")
        self.assertEqual(r["persisted"], "PUBLISHED")

    def test_event_log_integrity(self):
        """⑨ 事件日志签名：合法链 verify 通过；篡改任一事件 verify 失败。"""
        self._advance_to_apply_ready("c10")
        res = self.el.verify(key=_KEY)
        self.assertTrue(res["valid"], res)
        self.assertGreater(res["checked"], 0)
        # 篡改日志：把 actor_id 改成 Z
        s = open(self.log_path, encoding="utf-8").read()
        s2 = s.replace('"actor_id": "A"', '"actor_id": "Z"')
        self.assertNotEqual(s, s2)
        open(self.log_path, "w", encoding="utf-8").write(s2)
        res2 = self.el.verify(key=_KEY)
        self.assertFalse(res2["valid"], res2)

    def test_transition_requires_signing_key(self):
        """⑩ 无密钥无法产生合法 STATE_CHANGE 事件（仅 Broker 可写）。"""
        nokey_el = EventLog(self.log_path, KeyProvider())  # 无密钥
        sm2 = StateMachine(schema_path=_SCHEMA, event_log=nokey_el,
                           state_dir=os.path.join(self.root, "state2"), key=None)
        from event_log import SigningKeyUnavailable
        self.assertRaises(SigningKeyUnavailable,
                          sm2.transition_state, "c11", "DRAFT_STABLE", "STRUCTURE_STABLE",
                          "structure-stability-gate")


if __name__ == "__main__":
    unittest.main(verbosity=2)

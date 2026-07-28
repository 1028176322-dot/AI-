# -*- coding: utf-8 -*-
"""Twenty acceptance scenarios for the strict-v2 style pipeline."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for child in os.listdir(os.path.join(PLATFORM_ROOT, "scripts")):
    path = os.path.join(PLATFORM_ROOT, "scripts", child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import _gov
import author_learning
import broker
import capability
import chapter_publish
import chapter_rollback
import controlled_chapter_client
import manifest_build
import project_layout
import reader_panel
import reference_learning
import style_revise
import task_templates
from authorize import Authorizer, TaskContext


def _sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class StrictV2EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="strict_v2_e2e_")
        self.old_key = os.environ.get("FS_FINGERPRINT_KEY_DEFAULT")
        os.environ["FS_FINGERPRINT_KEY_DEFAULT"] = (
            "strict-v2-e2e-fingerprint-key")

    def tearDown(self):
        if self.old_key is None:
            os.environ.pop("FS_FINGERPRINT_KEY_DEFAULT", None)
        else:
            os.environ["FS_FINGERPRINT_KEY_DEFAULT"] = self.old_key
        shutil.rmtree(self.root, ignore_errors=True)

    def _next(self, task_type, event):
        return task_templates.next_types(task_type, event)

    def _publish_evidence(self):
        paths = {}
        bodies = {
            "draft": "沈砚推门入城。",
            "outline": "本章结果：沈砚入城。",
            "review": "verdict: pass\n",
        }
        for name, content in bodies.items():
            path = os.path.join(self.root, "%s.md" % name)
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(content)
            paths[name] = path
        manifest = manifest_build.build_manifest(
            "CH001", "RC1", "T-M", bodies["draft"],
            nkb_snapshot={"revision": "N1"},
            outline_text=bodies["outline"])["manifest"]
        paths["manifest"] = os.path.join(self.root, "manifest.yaml")
        _gov.dump_yaml(paths["manifest"], manifest)
        guidance = {
            "schema_version": "1.0.0",
            "style_guidance_sha256": "g" * 64,
            "effective_rules": [],
        }
        paths["guidance"] = os.path.join(self.root, "guidance.yaml")
        _gov.dump_yaml(paths["guidance"], guidance)
        sync = {
            "task_id": "T-SYNC",
            "status": "NKB_SYNC_PASSED",
            "nkb_revision": "N1",
            "nkb_snapshot_sha256": "n" * 64,
            "operation_manifest_sha256": "o" * 64,
            "created_at": "2026-07-28T00:00:00+08:00",
        }
        paths["sync"] = os.path.join(self.root, "sync.yaml")
        _gov.dump_yaml(paths["sync"], sync)
        regression = {
            "result": "FINAL_PASSED",
            "draft_sha256": hashlib.sha256(
                bodies["draft"].encode("utf-8")).hexdigest(),
            "nkb_revision": "N1",
            "nkb_snapshot_sha256": "n" * 64,
            "outline_sha256": _sha(paths["outline"]),
            "protected_manifest_sha256":
                manifest_build.manifest_sha256(manifest),
            "style_guidance_sha256": "g" * 64,
            "final_regression_config_version": "strict-v2.0.0",
            "final_regression_mode": "baseline",
            "chapter_review_report_sha256": _sha(paths["review"]),
        }
        paths["regression"] = os.path.join(
            self.root, "regression.json")
        with open(paths["regression"], "w", encoding="utf-8") as stream:
            json.dump(regression, stream)
        paths["approved"] = os.path.join(self.root, "approved.md")
        return paths, regression

    def test_01_clean_path_reaches_nkb_sync_and_publish(self):
        self.assertEqual(
            self._next("ai-diagnose", "on_clean"),
            ["final-regression"])
        self.assertEqual(
            self._next("final-regression", "on_pass"), ["nkb_update"])
        self.assertEqual(
            self._next("nkb_update", "on_submit"), ["nkb_sync"])
        self.assertEqual(
            self._next("nkb_sync", "on_pass"), ["chapter_publish"])

    def test_02_issue_path_contains_all_revision_gates(self):
        chain = [
            ("ai-diagnose", "on_issues", "style-revise"),
            ("style-revise", "on_complete", "fidelity-review"),
            ("fidelity-review", "on_pass", "style-quality-review"),
            ("style-quality-review", "on_pass",
             "chapter-apply-revision"),
            ("chapter-apply-revision", "on_complete",
             "final-regression"),
        ]
        for source, event, target in chain:
            self.assertIn(target, self._next(source, event))

    def test_03_quality_failure_enters_human_gate(self):
        self.assertEqual(
            self._next("style-quality-review", "on_fail"),
            ["human_gate"])
        self.assertEqual(
            self._next("human_gate", "on_complete"), ["style-revise"])

    def test_04_post_apply_failure_routes_to_rollback(self):
        self.assertEqual(
            self._next("final-regression", "on_fail_post_apply"),
            ["chapter-rollback-revision"])

    def test_05_rollback_conflict_blocks_automatic_restore(self):
        result = chapter_rollback.prepare_rollback(
            "CH001", "RC1", "T-RB", "旧稿",
            hashlib.sha256("应用稿".encode()).hexdigest(), "已被再改")
        self.assertEqual(result["result"], "ROLLBACK_CONFLICT")
        self.assertTrue(result["conflict_detected"])

    def test_06_manifest_conflict_blocks_diagnosis(self):
        result = manifest_build.build_manifest(
            "CH001", "RC1", "T-M", "纪年一三二七年。",
            nkb_snapshot={"revision": "N1"},
            nkb_hard_facts=[{
                "text": "一三二七年", "expected": "一三二六年"}])
        self.assertEqual(result["status"], "MANIFEST_CONFLICT")
        self.assertEqual(
            self._next("protected-manifest-build", "on_conflict"),
            ["human_gate"])

    def test_07_guidance_change_marks_old_candidate_stale(self):
        first = style_revise.ai_revise(
            "CH001", "RC1", "T-R", "沈砚入城。",
            style_guidance_sha256="a" * 64)
        second = style_revise.ai_revise(
            "CH001", "RC1", "T-R", "沈砚入城。",
            style_guidance_sha256="b" * 64,
            previous_result=first)
        self.assertTrue(second["stale"])

    def test_08_nkb_change_makes_publish_stale(self):
        paths, regression = self._publish_evidence()
        regression["nkb_revision"] = "N2"
        result = chapter_publish.execute_publish(
            self.root, "T-P", "CH001", "RC1",
            paths["draft"], paths["approved"], regression,
            paths["manifest"], paths["guidance"],
            paths["regression"], paths["sync"],
            paths["outline"], paths["review"])
        self.assertEqual(result["status"], "STALE")
        self.assertIn("nkb_sync_proof.nkb_revision", result["error"])

    def test_09_outline_change_makes_publish_stale(self):
        paths, regression = self._publish_evidence()
        with open(paths["outline"], "a", encoding="utf-8") as stream:
            stream.write("结果被更改。")
        result = chapter_publish.execute_publish(
            self.root, "T-P", "CH001", "RC1",
            paths["draft"], paths["approved"], regression,
            paths["manifest"], paths["guidance"],
            paths["regression"], paths["sync"],
            paths["outline"], paths["review"])
        self.assertEqual(result["status"], "STALE")
        self.assertIn("outline_sha256 changed", result["error"])

    def test_10_publish_without_final_passed_is_rejected(self):
        paths, regression = self._publish_evidence()
        regression["result"] = "FINAL_FAILED"
        result = chapter_publish.execute_publish(
            self.root, "T-P", "CH001", "RC1",
            paths["draft"], paths["approved"], regression,
            paths["manifest"], paths["guidance"],
            paths["regression"], paths["sync"],
            paths["outline"], paths["review"])
        self.assertEqual(result["status"], "STALE")
        self.assertIn("FINAL_PASSED", result["error"])

    def test_11_os_bypass_is_fail_closed_until_deployed(self):
        project_layout.scaffold_layout(self.root, "xuanhuan")
        deployment = _gov.load_yaml(os.path.join(
            self.root, "runtime", "learning",
            "broker-deployment.yaml"))
        self.assertEqual(
            deployment["deployment_state"], "BLOCKED_NOT_DEPLOYED")
        old_port = os.environ.pop("STYLE_BROKER_PORT", None)
        try:
            with self.assertRaisesRegex(
                    broker.BrokerError, "fail closed"):
                controlled_chapter_client.broker_write(
                    self.root, "missing", "chapter_write", [], "x")
        finally:
            if old_port is not None:
                os.environ["STYLE_BROKER_PORT"] = old_port

    def test_12_forged_task_context_is_not_trusted(self):
        writer = broker.ControlledWriter(
            self.root, key_vault=broker.BrokerKeyVault(key=b"k" * 32))
        server = broker.BrokerServer(writer)
        with self.assertRaisesRegex(broker.BrokerError, "task not found"):
            server._trusted_context({"identity": {
                "task_id": "FAKE", "session_id": "FAKE",
                "actor_id": "attacker", "actor_role": "administrator",
                "state": "PUBLISH_READY", "session_ready": True,
            }})

    def test_13_capability_replay_is_rejected(self):
        root = os.path.join(self.root, "p")
        os.makedirs(os.path.join(root, "chapters", "drafts"))
        os.makedirs(os.path.join(root, "chapters", "approved"))
        key = b"r" * 32
        writer = broker.ControlledWriter(
            root, key_vault=broker.BrokerKeyVault(key=key),
            strict_dependencies=False)
        target = os.path.join(root, "chapters", "drafts", "CH1.md")
        token = capability.issue(
            "T1", "S1", "A1", "chapter_write", [{
                "role": "target", "canonical_path": target,
                "expected_sha256": "absent"}],
            "p", key)
        writer._commit(token, "正文", "A1", "S1", "T1")
        with self.assertRaisesRegex(
                broker.BrokerError, "already consumed"):
            writer._commit(token, "重放", "A1", "S1", "T1")

    def test_14_cross_project_capability_is_rejected(self):
        p1 = os.path.join(self.root, "p1")
        p2 = os.path.join(self.root, "p2")
        for root in (p1, p2):
            os.makedirs(os.path.join(root, "chapters", "drafts"))
            os.makedirs(os.path.join(root, "chapters", "approved"))
        key = b"x" * 32
        target = os.path.join(p1, "chapters", "drafts", "CH1.md")
        token = capability.issue(
            "T1", "S1", "A1", "chapter_write", [{
                "role": "target", "canonical_path": target,
                "expected_sha256": "absent"}],
            "p", key)
        writer = broker.ControlledWriter(
            p2, key_vault=broker.BrokerKeyVault(key=key),
            strict_dependencies=False)
        with self.assertRaises(broker.PathEscalation):
            writer._commit(token, "正文", "A1", "S1", "T1")

    def test_15_subagent_context_is_rejected(self):
        target = os.path.join(
            self.root, "analysis", "style", "CH1", "RC1", "c.md")
        context = TaskContext(
            task_id="T1", actor_id="A1", session_ready=True,
            subagent_policy="allowed", lease_owner="A1",
            state="RUNNING")
        result = Authorizer().authorize(
            "candidate_create", context,
            resources=[{
                "role": "target", "canonical_path": target,
                "expected_sha256": "absent"}],
            env={"root": self.root})
        self.assertFalse(result.allowed)
        self.assertIn(
            "subagent_policy_denied",
            [row["check"] for row in result.failed])

    def test_16_legacy_project_keeps_legacy_flow(self):
        self.assertFalse(project_layout.is_style_strict(self.root))
        with open(os.path.join(
                PLATFORM_ROOT, "scripts", "learning",
                "chapter_write.py"), "r", encoding="utf-8") as stream:
            source = stream.read()
        self.assertIn("controlled_write.py", source)

    def test_17_reference_prose_never_enters_learning_artifact(self):
        source = os.path.join(self.root, "book.txt")
        secret_sentence = "独一无二的参考原句不可进入学习产物。"
        with open(source, "w", encoding="utf-8") as stream:
            stream.write("第一章\n" + secret_sentence)
        out = os.path.join(self.root, "out")
        path, report = reference_learning.analyze(
            source, "xuanhuan", out)
        self.assertFalse(report["raw_text_stored"])
        with open(path, "r", encoding="utf-8") as stream:
            profile_text = stream.read()
        self.assertNotIn(secret_sentence, profile_text)

    def test_18_source_withdrawal_recomputes_candidates(self):
        source_dir = os.path.join(self.root, "sources")
        output_dir = os.path.join(self.root, "learning")
        os.makedirs(source_dir)
        for index in range(4):
            with open(os.path.join(
                    source_dir, "book%d.txt" % index),
                    "w", encoding="utf-8") as stream:
                stream.write(
                    "第一章\n沈砚推门。冷风入室。“走。”他说。"
                    "第%d卷忽然结束。" % index)
        summary_path, summary = reference_learning.batch(
            source_dir, "xuanhuan", output_dir)
        self.assertEqual(summary["source_count"], 4)
        report_path, report = reference_learning.withdraw_source(
            summary_path, "book0")
        self.assertTrue(os.path.isfile(report_path))
        self.assertEqual(report["remaining_source_count"], 3)
        self.assertTrue(report["revoked_candidate_ids"])
        self.assertTrue(report["rebuilt_candidate_ids"])

    def test_19_author_feedback_below_three_never_promotes(self):
        store = os.path.join(self.root, "author-feedback")
        for index in range(2):
            author_learning.record_feedback(
                "CH001", 0, 2, "旧句", "新句",
                "偏好具体动作", task_id="T%d" % index,
                feedback_store=store)
        self.assertEqual(
            author_learning.generate_l4_candidates(store), [])
        author_learning.record_feedback(
            "CH002", 0, 2, "旧句二", "新句二",
            "偏好具体动作", task_id="T3",
            feedback_store=store)
        candidates = author_learning.generate_l4_candidates(store)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["lifecycle_state"], "EXTRACTED")

    def test_20_human_observation_never_impersonates_ai_panel(self):
        panel_path, _ = reader_panel.prepare_panel(
            self.root, "T-READER", "CH001")
        human_path = reader_panel.prepare_human_template(
            self.root, "T-READER")
        human = _gov.load_yaml(human_path)
        for index, participant in enumerate(human["participants"]):
            participant.update({
                "reader_id": "R%d" % index,
                "segment": "new" if index < 2 else "veteran",
                "independent": True,
                "dropoff_location": None,
            })
            participant["scores"] = {
                dimension: 80
                for dimension in reader_panel.HUMAN_DIMENSIONS}
        _gov.dump_yaml(human_path, human)
        _, report = reader_panel.ingest_human(
            self.root, "T-READER", human_path)
        panel = _gov.load_yaml(panel_path)
        self.assertEqual(
            report["evidence_mode"], "verified_human_input")
        self.assertEqual(
            panel["evidence_mode"],
            "ai_sequential_panel_not_human_feedback")
        self.assertEqual(
            panel["human_calibration"]["status"], "provided")


if __name__ == "__main__":
    unittest.main(verbosity=2)

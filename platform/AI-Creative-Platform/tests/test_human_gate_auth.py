# -*- coding: utf-8 -*-
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
import human_gate_auth
import task_engine


class HumanGateAuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="human_gate_auth_")
        for state in task_engine.STATES:
            os.makedirs(os.path.join(self.root, "tasks", state),
                        exist_ok=True)
        self.old_secret = os.environ.get(
            human_gate_auth.SECRET_ENV)
        os.environ[human_gate_auth.SECRET_ENV] = "s" * 64

    def tearDown(self):
        if self.old_secret is None:
            os.environ.pop(human_gate_auth.SECRET_ENV, None)
        else:
            os.environ[
                human_gate_auth.SECRET_ENV] = self.old_secret
        shutil.rmtree(self.root, ignore_errors=True)

    def _task(self, task_id, kind="quality_exception"):
        task = {
            "id": task_id,
            "type": "human_gate",
            "status": "running",
            "inputs": {
                "required": ["gate_context", "human_authorization"],
                "values": {
                    "gate_context": {
                        "schema": "human-gate-context@1.0.0",
                        "kind": kind,
                        "source_task": "SOURCE",
                        "source_event": "on_warning",
                    },
                },
            },
        }
        _gov.dump_yaml(os.path.join(
            self.root, "tasks", "running", "%s.yaml" % task_id), {
                "task": task})
        return task

    def _decision(self, task_id, context_hash, decision="pass"):
        path = os.path.join(
            self.root, "tasks", "running", task_id,
            "outputs", "gate-decision.yaml")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _gov.dump_yaml(path, {
            "decision": decision,
            "gate_context_sha256": context_hash,
        })
        return os.path.relpath(path, self.root)

    def test_signed_context_scoped_grant_passes(self):
        self._task("HG-1")
        grant_path, _ = human_gate_auth.authorize(
            self.root, ["HG-1"], "pass", "owner@example",
            "specific warning accepted")
        _, data = task_engine.load_task(self.root, "HG-1")
        task = data["task"]
        _, context_hash = human_gate_auth.gate_context(
            task, self.root)
        decision = self._decision("HG-1", context_hash)
        result = human_gate_auth.verify_task_authorization(
            self.root, task, {"gate_decision": decision}, "on_pass")
        self.assertTrue(result["authorization_id"].startswith("HGA-"))
        self.assertTrue(os.path.isfile(grant_path))

    def test_tampered_grant_is_rejected(self):
        self._task("HG-2")
        grant_path, _ = human_gate_auth.authorize(
            self.root, ["HG-2"], "pass", "owner@example", "reason")
        body = _gov.load_yaml(grant_path)
        body["human_authorization"]["decision"] = "reject"
        _gov.dump_yaml(grant_path, body)
        _, data = task_engine.load_task(self.root, "HG-2")
        task = data["task"]
        _, context_hash = human_gate_auth.gate_context(
            task, self.root)
        decision = self._decision("HG-2", context_hash)
        with self.assertRaisesRegex(
                human_gate_auth.HumanGateAuthorizationError,
                "signature"):
            human_gate_auth.verify_task_authorization(
                self.root, task,
                {"gate_decision": decision}, "on_pass")

    def test_reader_milestone_cannot_be_batch_authorized(self):
        self._task(
            "HG-READER",
            kind=human_gate_auth.READER_GATE_KIND)
        self._task("HG-QUALITY")
        with self.assertRaisesRegex(
                human_gate_auth.HumanGateAuthorizationError,
                "cannot be batch"):
            human_gate_auth.authorize(
                self.root, ["HG-READER", "HG-QUALITY"],
                "pass", "owner@example", "not allowed")

    def test_reader_milestone_cannot_pass_without_real_report(self):
        self._task(
            "HG-READER-ONLY",
            kind=human_gate_auth.READER_GATE_KIND)
        human_gate_auth.authorize(
            self.root, ["HG-READER-ONLY"], "pass",
            "owner@example", "reader milestone")
        _, data = task_engine.load_task(
            self.root, "HG-READER-ONLY")
        task = data["task"]
        _, context_hash = human_gate_auth.gate_context(
            task, self.root)
        decision = self._decision(
            "HG-READER-ONLY", context_hash)
        with self.assertRaisesRegex(
                human_gate_auth.HumanGateAuthorizationError,
                "human_reader_report"):
            human_gate_auth.verify_task_authorization(
                self.root, task,
                {"gate_decision": decision}, "on_pass")


if __name__ == "__main__":
    unittest.main(verbosity=2)

# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for child in os.listdir(os.path.join(PLATFORM_ROOT, "scripts")):
    path = os.path.join(PLATFORM_ROOT, "scripts", child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import chapter_author
import _gov


class ChapterAuthorContractTest(unittest.TestCase):
    def _response(self):
        return {
            "chapter_draft": "正文",
            "self_check": {
                "constitution": "pass",
                "planning": "pass",
                "context": "pass",
            },
            "writing_strategy_evidence": {
                "writing_strategy_evidence": {}},
            "candidate_facts": {"knowledge_delta": {}},
            "handoff": {"nkb_handoff": {}},
        }

    def test_complete_response_contract_passes(self):
        chapter_author._validate_response(self._response())

    def test_missing_semantic_evidence_is_rejected(self):
        with self.assertRaisesRegex(
                chapter_author.AuthorExecutorError,
                "writing_strategy_evidence root"):
                chapter_author._validate_response({
                "chapter_draft": "正文",
                "self_check": {
                    "constitution": "pass",
                    "planning": "pass",
                    "context": "pass",
                },
                "writing_strategy_evidence": {},
                "candidate_facts": {"knowledge_delta": {}},
                "handoff": {"nkb_handoff": {}},
            })

    def test_self_check_cannot_be_empty_or_claim_failure(self):
        with self.assertRaisesRegex(
                chapter_author.AuthorExecutorError,
                "self_check must pass"):
            chapter_author._validate_response({
                "chapter_draft": "正文",
                "self_check": {
                    "constitution": "pass",
                    "planning": "fail",
                    "context": "pass",
                },
                "writing_strategy_evidence": {
                    "writing_strategy_evidence": {}},
                "candidate_facts": {"knowledge_delta": {}},
                "handoff": {"nkb_handoff": {}},
            })

    def test_unconfigured_adapter_fails_closed(self):
        old = os.environ.pop(
            "AI_CREATIVE_AUTHOR_COMMAND_JSON", None)
        try:
            with self.assertRaisesRegex(
                    chapter_author.AuthorExecutorError,
                    "not configured"):
                chapter_author._command_from_config({
                    "transport": "command",
                    "command_env":
                        "AI_CREATIVE_AUTHOR_COMMAND_JSON",
                })
        finally:
            if old is not None:
                os.environ[
                    "AI_CREATIVE_AUTHOR_COMMAND_JSON"] = old

    def test_registry_empty_models_is_yaml_lite_compatible(self):
        config = chapter_author._load_config("model-strong")
        self.assertEqual("command", config["transport"])
        self.assertEqual(
            "AI_CREATIVE_AUTHOR_COMMAND_JSON",
            config["command_env"])

    def test_same_packet_retry_reuses_validated_response(self):
        root = tempfile.mkdtemp(prefix="chapter_author_cache_")
        try:
            request = {"schema": "chapter-author-request@1.0.0"}
            with mock.patch.object(
                    chapter_author, "_invoke",
                    return_value=self._response()) as invoke:
                first, reused = chapter_author._invoke_or_reuse(
                    ["adapter"], request, 10, root)
                second, reused_second = chapter_author._invoke_or_reuse(
                    ["adapter"], request, 10, root)
            self.assertFalse(reused)
            self.assertTrue(reused_second)
            self.assertEqual(first, second)
            self.assertEqual(1, invoke.call_count)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_running_interactive_task_cannot_be_hijacked(self):
        root = tempfile.mkdtemp(prefix="chapter_author_owner_")
        try:
            task_dir = os.path.join(root, "tasks", "running")
            os.makedirs(task_dir, exist_ok=True)
            _gov.dump_yaml(os.path.join(task_dir, "T-AUTHOR.yaml"), {
                "task": {
                    "id": "T-AUTHOR",
                    "type": "chapter_write",
                    "status": "running",
                    "owner": "AI-A",
                },
            })
            with self.assertRaisesRegex(
                    chapter_author.AuthorExecutorError,
                    "owned by AI-A"):
                chapter_author._arm_task(
                    root, "T-AUTHOR", "AI-B", "model-strong")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_interactive_agent_inherits_running_task_owner(self):
        root = tempfile.mkdtemp(prefix="chapter_author_inherit_")
        try:
            task_dir = os.path.join(root, "tasks", "running")
            os.makedirs(task_dir, exist_ok=True)
            _gov.dump_yaml(os.path.join(task_dir, "T-AUTHOR.yaml"), {
                "task": {
                    "id": "T-AUTHOR",
                    "type": "chapter_write",
                    "status": "running",
                    "owner": "橘子",
                },
            })
            self.assertEqual(
                "橘子",
                chapter_author._effective_agent(
                    root, "T-AUTHOR", requested_agent=None))
            self.assertEqual(
                "explicit-agent",
                chapter_author._effective_agent(
                    root, "T-AUTHOR",
                    requested_agent="explicit-agent"))
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

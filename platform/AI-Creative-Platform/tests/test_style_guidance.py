# -*- coding: utf-8 -*-
import os
import json
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
import style_guidance


class StyleGuidanceTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="style_guidance_")
        os.makedirs(os.path.join(self.root, "NKB"), exist_ok=True)
        os.makedirs(os.path.join(
            self.root, "sources", "outline"), exist_ok=True)
        os.makedirs(os.path.join(
            self.root, "memory", "project", "style-library"),
            exist_ok=True)
        _gov.dump_yaml(os.path.join(self.root, "project.yaml"), {
            "project": {"id": "P1", "type": "xuanhuan"},
            "paths": {"outline": "./sources/outline"},
        })
        _gov.dump_yaml(os.path.join(self.root, "NKB", "facts.yaml"), {
            "revision": "N1", "facts": ["主角姓沈"]})
        _gov.dump_yaml(os.path.join(
            self.root, "sources", "outline", "CH001.yaml"), {
                "chapter_id": "CH001", "outcome": "主角入城"})

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _card(self, relative, layer, rules):
        path = os.path.join(
            self.root, "memory", "project", "style-library", relative)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _gov.dump_yaml(path, {
            "card_id": "%s-CARD" % layer,
            "layer": layer,
            "style_preferences": rules,
            "style_targets": [],
            "project_constraints": [],
        })

    def test_same_inputs_produce_stable_hash(self):
        first = style_guidance.build(
            self.root, "CH001", "RC1", task_id="T1")
        second = style_guidance.build(
            self.root, "CH001", "RC1", task_id="T1")
        self.assertEqual(
            first["style_guidance_sha256"],
            second["style_guidance_sha256"])

    def test_l0_wins_same_field_and_scope(self):
        rule = {
            "rule_id": "R-L0", "field": "sentence_rhythm",
            "status": "ACTIVE",
            "scope": {"content_type": "narration"},
            "value": {"instruction": "稳健推进"},
        }
        self._card("project-style.card.yaml", "L0", [rule])
        lower = dict(rule)
        lower["rule_id"] = "R-L2"
        lower["value"] = {"instruction": "极短句"}
        self._card(
            os.path.join("scene", "battle.card.yaml"), "L2", [lower])
        guidance = style_guidance.build(
            self.root, "CH001", "RC1",
            scene_types=["battle"], task_id="T1")
        self.assertEqual(
            guidance["effective_rules"][0]["rule_id"], "R-L0")
        self.assertTrue(any(
            item.get("winner_rule_id") == "R-L0"
            for item in guidance["suppressed_rules"]))

    def test_l3_is_dialogue_only(self):
        self._card(
            os.path.join("character", "C1.card.yaml"), "L3", [{
                "rule_id": "VOICE-C1",
                "status": "ACTIVE",
                "scope": {
                    "content_type": "narration",
                    "character_ids": ["C1"],
                },
                "value": {"instruction": "寡言"},
            }])
        guidance = style_guidance.build(
            self.root, "CH001", "RC1",
            character_ids=["C1"], task_id="T1")
        rule = next(
            row for row in guidance["effective_rules"]
            if row["rule_id"] == "VOICE-C1")
        self.assertEqual(rule["scope"]["content_type"], "dialogue")

    def test_inactive_rules_never_enter_runtime(self):
        self._card("project-style.card.yaml", "L0", [
            {"rule_id": "ACTIVE", "status": "ACTIVE",
             "value": {"instruction": "有效"}},
            {"rule_id": "REVOKED", "status": "REVOKED",
             "value": {"instruction": "无效"}},
            {"rule_id": "PENDING", "status": "review_pending",
             "value": {"instruction": "未审"}},
        ])
        guidance = style_guidance.build(
            self.root, "CH001", "RC1", task_id="T1")
        ids = {
            row["rule_id"] for row in guidance["effective_rules"]}
        self.assertEqual(ids, {"ACTIVE"})

    def test_active_legacy_reference_rules_enter_l4_guidance(self):
        path = os.path.join(
            self.root, "memory", "project", "style-library",
            "style-cards.json")
        with open(path, "w", encoding="utf-8") as stream:
            json.dump([
                {
                    "candidate_id": "SRC-ACTIVE",
                    "rule_id": "REFERENCE-RHYTHM",
                    "status": "ACTIVE",
                    "scope": {
                        "content_type": "narration",
                        "scene_types": ["battle"],
                        "character_ids": [],
                    },
                    "value": {
                        "dimension": "syntactic_rhythm",
                        "instruction": "快慢句按行动压力切换",
                    },
                },
                {
                    "candidate_id": "SRC-PENDING",
                    "rule_id": "REFERENCE-PENDING",
                    "status": "EXTRACTED",
                    "scope": {"content_type": "narration"},
                    "value": {"instruction": "不得生效"},
                },
            ], stream, ensure_ascii=False)
        guidance = style_guidance.build(
            self.root, "CH001", "RC1",
            scene_types=["battle"], task_id="T1")
        ids = {
            row["rule_id"] for row in guidance["effective_rules"]}
        self.assertIn("REFERENCE-RHYTHM", ids)
        self.assertNotIn("REFERENCE-PENDING", ids)
        rule = next(
            row for row in guidance["effective_rules"]
            if row["rule_id"] == "REFERENCE-RHYTHM")
        self.assertEqual(rule["source_layer"], "L4")

    def test_legacy_lifecycle_revocation_overrides_stale_active_row(self):
        library = os.path.join(
            self.root, "memory", "project", "style-library")
        with open(os.path.join(
                library, "style-cards.json"),
                "w", encoding="utf-8") as stream:
            json.dump([{
                "candidate_id": "SRC-REVOKED",
                "rule_id": "STALE-ACTIVE",
                "status": "ACTIVE",
                "scope": {"content_type": "narration"},
                "value": {"instruction": "不得生效"},
            }], stream, ensure_ascii=False)
        with open(os.path.join(
                library, "SRC-REVOKED.lifecycle.json"),
                "w", encoding="utf-8") as stream:
            json.dump({
                "candidate_id": "SRC-REVOKED",
                "current_state": "REVOKED",
            }, stream)
        guidance = style_guidance.build(
            self.root, "CH001", "RC1", task_id="T1")
        self.assertNotIn(
            "STALE-ACTIVE",
            {row["rule_id"] for row in guidance["effective_rules"]})



if __name__ == "__main__":
    unittest.main(verbosity=2)

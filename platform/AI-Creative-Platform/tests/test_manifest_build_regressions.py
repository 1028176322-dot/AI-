# -*- coding: utf-8 -*-
import os
import sys
import unittest


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEARNING = os.path.join(PLATFORM_ROOT, "scripts", "learning")
if LEARNING not in sys.path:
    sys.path.insert(0, LEARNING)

import manifest_build


class ManifestBuildRegressionTest(unittest.TestCase):
    def _build(self, snapshot):
        return manifest_build.build_manifest(
            "CH-001", "RC-001", "TASK-001",
            "第一句。最后一句。", nkb_snapshot=snapshot,
            created_at=1)["manifest"]

    def test_top_level_revision(self):
        self.assertEqual(
            "NKB-R2",
            self._build({"revision": "NKB-R2"})["nkb_revision"])

    def test_nested_nkb_snapshot_id(self):
        self.assertEqual(
            "NKB-SNAPSHOT-002",
            self._build({
                "nkb": {"snapshot_id": "NKB-SNAPSHOT-002"},
                "components": {},
            })["nkb_revision"])

    def test_top_level_value_wins_for_compatible_layout(self):
        self.assertEqual(
            "NKB-R3",
            self._build({
                "revision": "NKB-R3",
                "nkb": {"snapshot_id": "NKB-OLD"},
            })["nkb_revision"])

    def test_nested_snapshot_revision(self):
        self.assertEqual(
            "NKB-R4",
            self._build({
                "nkb": {"snapshot": {"revision": "NKB-R4"}},
            })["nkb_revision"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

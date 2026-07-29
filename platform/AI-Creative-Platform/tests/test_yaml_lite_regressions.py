# -*- coding: utf-8 -*-
import os
import sys
import unittest


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMON = os.path.join(PLATFORM_ROOT, "scripts", "_common")
if COMMON not in sys.path:
    sys.path.insert(0, COMMON)

import _yaml_lite


class YamlLiteRegressionTest(unittest.TestCase):
    def test_folded_and_literal_block_scalars(self):
        body = _yaml_lite.load(
            "summary: >-\n"
            "  第一行\n"
            "  第二行\n"
            "\n"
            "  新段\n"
            "literal: |-\n"
            "  A\n"
            "  B\n")
        self.assertEqual("第一行 第二行\n新段", body["summary"])
        self.assertEqual("A\nB", body["literal"])

    def test_empty_mapping_round_trips_as_mapping(self):
        source = {"models": {}, "nested": {"empty": {}}, "rows": [{}]}
        dumped = _yaml_lite.dump(source)
        loaded = _yaml_lite.load(dumped)
        self.assertEqual(source, loaded)
        self.assertIsInstance(loaded["models"], dict)

    def test_first_mapping_key_keeps_nested_children(self):
        source = {
            "rows": [{
                "first": {
                    "nested_a": 1,
                    "nested_b": 2,
                },
                "second": "sibling",
            }]
        }
        dumped = _yaml_lite.dump(source)
        loaded = _yaml_lite.load(dumped)
        self.assertEqual(source, loaded)
        self.assertNotIn("nested_a", loaded["rows"][0])

    def test_multiline_dump_round_trips(self):
        source = {
            "summary": "第一行\n第二行",
            "rows": [{"evidence": "证据一\n证据二", "score": 80}],
            "notes": ["列表第一行\n列表第二行"],
        }
        self.assertEqual(source, _yaml_lite.load(_yaml_lite.dump(source)))


if __name__ == "__main__":
    unittest.main(verbosity=2)

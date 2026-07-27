# -*- coding: utf-8 -*-
"""#21 回归：参考风格规则提取的治理强制（style_extract）。"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM_ROOT = os.path.dirname(HERE)
for _c in ("learning", "logs"):
    _p = os.path.join(PLATFORM_ROOT, "scripts", _c)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import style_extract as se  # noqa: E402


def _sources(n, weight=None):
    out = []
    text = ("肖凡推开木门。冷风灌进来。他眯起眼，望向院中老槐。"
            "“走。”他只说了这一个字。夜色像潮水般漫过屋檐。")
    for i in range(n):
        out.append({
            "source_id": "SRC%d" % i,
            "text": text + (" 第%d卷的尾声里，风更冷了。" % i),
            "weight": (weight[i] if weight else 1.0 / n),
        })
    return out


class ExtractTest(unittest.TestCase):
    def test_produces_conformant_candidates(self):
        ex = se.StyleExtractor()
        cands = ex.extract(_sources(5), "RC1", "T1")
        self.assertTrue(len(cands) > 0)
        for c in cands:
            ok, errors = se.validate_candidate(c)
            self.assertTrue(ok, errors)
            self.assertIn(c["rule_type"], se.ALLOWED_RULE_TYPES)
            self.assertEqual(c["review_status"], "EXTRACTED")
            self.assertLessEqual(c["max_single_source_weight"], 0.4)
            self.assertGreaterEqual(c["source_count"], 3)

    def test_rejects_hard_constraint(self):
        def bad_fn(sources, config):
            return [{
                "rule_type": "hard_constraint",
                "scope": {"content_type": "all", "scene_types": [], "character_ids": [], "span_selector": "doc"},
                "value": {"constraint": "禁止任何模糊词", "confidence_source": {"computed": True}},
                "example_rules": [{"text": "系统生成例句", "example_origin": "system-generated"}],
                "source_ids": [s["source_id"] for s in sources],
            }]
        ex = se.StyleExtractor(extract_fn=bad_fn)
        with self.assertRaises(se.StyleExtractError):
            ex.extract(_sources(5), "RC1", "T1")

    def test_rejects_low_source_count(self):
        ex = se.StyleExtractor()
        with self.assertRaises(se.StyleExtractError):
            ex.extract(_sources(2), "RC1", "T1")

    def test_rejects_single_source_weight(self):
        # 3 来源但其一权重 0.5 > 0.4
        ex = se.StyleExtractor()
        with self.assertRaises(se.StyleExtractError):
            ex.extract(_sources(3, weight=[0.5, 0.25, 0.25]), "RC1", "T1")

    def test_requires_confidence_source(self):
        def no_cs(sources, config):
            return [{
                "rule_type": "style_preference",
                "scope": {"content_type": "dialogue", "scene_types": ["对白"], "character_ids": [], "span_selector": "d"},
                "value": {"preference": "短促对白"},
                "example_rules": [{"text": "系统生成例句", "example_origin": "system-generated"}],
                "source_ids": [s["source_id"] for s in sources],
            }]
        ex = se.StyleExtractor(extract_fn=no_cs)
        with self.assertRaises(se.StyleExtractError):
            ex.extract(_sources(5), "RC1", "T1")

    def test_requires_example_origin(self):
        def no_origin(sources, config):
            return [{
                "rule_type": "style_preference",
                "scope": {"content_type": "dialogue", "scene_types": ["对白"], "character_ids": [], "span_selector": "d"},
                "value": {"preference": "短促对白",
                          "confidence_source": {"computed": True, "cross_source_agreement": 0.8}},
                "example_rules": [{"text": "系统生成例句"}],
                "source_ids": [s["source_id"] for s in sources],
            }]
        ex = se.StyleExtractor(extract_fn=no_origin)
        with self.assertRaises(se.StyleExtractError):
            ex.extract(_sources(5), "RC1", "T1")

    def test_no_raw_reference_sentence_in_example(self):
        raw = "肖凡推开木门。冷风灌进来。"
        def copy_orig(sources, config):
            return [{
                "rule_type": "style_preference",
                "scope": {"content_type": "narrative", "scene_types": ["叙述"], "character_ids": [], "span_selector": "s"},
                "value": {"preference": "示例", "confidence_source": {"computed": True, "cross_source_agreement": 0.9}},
                "example_rules": [{"text": raw, "example_origin": "system-generated"}],
                "source_ids": [s["source_id"] for s in sources],
            }]
        ex = se.StyleExtractor(extract_fn=copy_orig)
        with self.assertRaises(se.StyleExtractError):
            ex.extract(_sources(5), "RC1", "T1")

    def test_no_raw_ngram_in_value(self):
        raw_sent = "肖凡推开木门。冷风灌进来。"
        def embed_ngram(sources, config):
            return [{
                "rule_type": "style_target",
                "scope": {"content_type": "narrative", "scene_types": ["叙述"], "character_ids": [], "span_selector": "s"},
                "value": {"target": {"note": raw_sent},  # 把原始句写进 value -> 禁
                          "confidence_source": {"computed": True, "cross_source_agreement": 0.9}},
                "example_rules": [{"text": "系统生成例句", "example_origin": "system-generated"}],
                "source_ids": [s["source_id"] for s in sources],
            }]
        ex = se.StyleExtractor(extract_fn=embed_ngram)
        with self.assertRaises(se.StyleExtractError):
            ex.extract(_sources(5), "RC1", "T1")

    def test_persist_candidates(self):
        root = tempfile.mkdtemp(prefix="ex_")
        ex = se.StyleExtractor()
        cands = ex.extract(_sources(5), "RC1", "T1")
        d = se.persist(cands, root, "CH1", "T1")
        self.assertTrue(os.path.isdir(d))
        self.assertIn("analysis", d.replace("\\", "/"))
        self.assertNotIn("chapters", d.replace("\\", "/"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

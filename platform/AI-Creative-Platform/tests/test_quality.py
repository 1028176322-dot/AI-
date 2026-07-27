# -*- coding: utf-8 -*-
import os as _os, sys as _sys
_PLAT2 = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PLAT2 not in _sys.path:
    _sys.path.insert(0, _PLAT2)
_SCR2 = _os.path.join(_PLAT2, "scripts")
if _os.path.isdir(_SCR2):
    for _d in _os.listdir(_SCR2):
        _p = _os.path.join(_SCR2, _d)
        if _os.path.isdir(_p) and _p not in _sys.path:
            _sys.path.insert(0, _p)
if _os.path.join(_PLAT2, "cli") not in _sys.path:
    _sys.path.insert(0, _os.path.join(_PLAT2, "cli"))
"""质量评分（Quality Score）e2e 回归测试 — Phase 2 系统 #2。

覆盖：
  T1 partial 评分（无审查报告）：仅拦截结构性 fatal，否则 proceed
  T2 fatal 拦截（logic C3 永熙>37）：gate=block
  T3 review 消费 -> caution（composite < target 80）
  T4 review 消费 -> block（composite < hard_floor 60）
  T5 review 消费 -> proceed（composite >= target 80）
  T6 报告落盘（write=True）到 analysis/quality/ 且可回读
  T7 契约结构：章节文件缺失 -> contract fatal -> block

所有临时项目建在 tempfile 下，不污染仓库。
"""
import os
import sys
import io
import tempfile
import shutil
import contextlib
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import quality_scorer as qs
import task_engine as te


PY = sys.executable


def _write_chapter(root, sub, fname, text):
    d = os.path.join(root, sub)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, fname)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def _write_review(root, es, ci, reader, pi):
    d = os.path.join(root, "analysis", "review")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "REV-%d.yaml" % int(es * 1000 + ci))
    with open(p, "w", encoding="utf-8") as f:
        f.write("meta:\n  project: qstest\nreview:\n"
                "  es: %d\n  ci: %d\n  reader_index: %d\n  pi: %d\n"
                % (es, ci, reader, pi))
    return p


CLEAN_CHAPTER = """《章名测试篇》

肖凡立身在清虚观后的石阶上，山风掠过松林，发出细碎的声响。他抬眼望向远处起伏的群山，
心中那点不安却迟迟未能散去。今日观中格外安静，连往常叽喳的雀鸟也都敛了声。

他缓步走下石阶，脚边一株野菊被风压得弯了腰，又很快弹直。这样的小景他见过许多回，
却总觉得每一次都有不同。远处的钟声悠悠传来，惊起一林飞鸟。

师父说过，习武先习心。肖凡虽年少，却已隐隐明白这话的分量。他收摄心神，
将杂念一一压下，只留山风与松涛在耳畔流动。

过了一刻，他转身回观，背影没入渐起的暮色里。
"""


class QualityScoreTest(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="qs_test_")
        # 注意：章节放 chapters/drafts/ 而非 approved/，避免冲击分析仪将目标判为"已发布章节"从而阻断 claim。
        self.ch99 = _write_chapter(self.root, "chapters/drafts", "第99章_测试.md", CLEAN_CHAPTER)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _score99(self, write=False):
        return qs.score(self.root, "chapter", "99", write=write, proposed_by="test")

    # T1 partial：无审查报告 -> proceed + review_consumed False
    def test_partial_no_review(self):
        rep = self._score99()
        self.assertEqual(rep["gate"]["decision"], "caution")
        self.assertFalse(rep["composite"]["review_consumed"])
        # 部分评分提示在理由里
        self.assertTrue(any("partial" in r for r in rep["gate"]["reasons"]))

    # T2 fatal：永熙三十八年 -> C3 -> block
    def test_fatal_year_overflow(self):
        _write_chapter(self.root, "approved", "第100章_越界.md",
                       "《章名越界篇》\n\n永熙三十八年，盛京城里起了波澜，各方势力暗流涌动。\n")
        rep = qs.score(self.root, "chapter", "100", write=False)
        self.assertEqual(rep["gate"]["decision"], "block")
        self.assertTrue(any(s["fatal"] for s in rep["signals"]))

    # T3 review 消费 -> caution
    def test_review_caution(self):
        _write_review(self.root, 65, 90, 60, 65)  # 71.5 < 80
        rep = self._score99()
        self.assertTrue(rep["composite"]["review_consumed"])
        self.assertEqual(rep["gate"]["decision"], "caution")
        self.assertLess(rep["composite"]["value"], 80)
        self.assertGreaterEqual(rep["composite"]["value"], 60)

    # T4 review 消费 -> block（极低分 < 60）
    def test_review_block_low(self):
        _write_review(self.root, 30, 30, 30, 30)  # 30 < 60
        rep = self._score99()
        self.assertTrue(rep["composite"]["review_consumed"])
        self.assertEqual(rep["gate"]["decision"], "block")

    # T5 review 消费 -> proceed（高分 >= 80）
    def test_review_proceed_high(self):
        _write_review(self.root, 95, 95, 95, 95)  # 95 >= 80
        rep = self._score99()
        self.assertTrue(rep["composite"]["review_consumed"])
        self.assertEqual(rep["gate"]["decision"], "proceed")

    # T6 报告落盘
    def test_write_report(self):
        rid = self._score99(write=True)["meta"].get("report_id")
        self.assertIsNotNone(rid)
        rd = os.path.join(self.root, "analysis", "quality", rid + ".yaml")
        self.assertTrue(os.path.isfile(rd))
        # 回读可解析
        back = qs._safe_load(rd)
        self.assertIsInstance(back, dict)
        self.assertEqual(back["gate"]["decision"], "caution")
        self.assertEqual(back["target"]["target_type"], "chapter")
        self.assertEqual(str(back["target"]["target_id"]), "99")

    # T7 章节文件缺失 -> contract fatal -> block
    def test_contract_missing_chapter(self):
        rep = qs.score(self.root, "chapter", "9999", write=False)
        contract = next(s for s in rep["signals"] if s["name"] == "contract")
        self.assertTrue(contract["fatal"])
        self.assertEqual(rep["gate"]["decision"], "block")

    # T8 契约必填段：meta/target/composite/gate 存在
    def test_report_schema_sections(self):
        rep = self._score99()
        for sec in ("meta", "target", "signals", "composite", "gate"):
            self.assertIn(sec, rep)
        self.assertIn("value", rep["composite"])
        self.assertIn("decision", rep["gate"])
        self.assertIn("scorer", rep["meta"])

    # ── 集成：submit 强制质量门禁 ──
    def _make_running_task(self, chapter_ref, fatal=False):
        if fatal:
            _write_chapter(self.root, "chapters/drafts", "第%s章_越界.md" % chapter_ref,
                           "《章名越界篇》\n\n永熙三十八年，盛京城里起了波澜，各方暗流涌动。\n")
        tid = "T-CH-%s" % chapter_ref
        te.create_task(self.root, {"task": {
            "id": tid, "type": "chapter_write", "chapter_ref": chapter_ref,
            "title": "写第%s章" % chapter_ref, "priority": "high"}})
        te.claim(self.root, tid, "agent-x", "writer")
        te.start(self.root, tid, "agent-x", "writer")
        return tid

    # T9 submit 门禁：fatal 章节 -> 阻断 submit（ValueError）
    def test_submit_gate_block(self):
        tid = self._make_running_task("100", fatal=True)
        with self.assertRaises(ValueError) as ctx:
            te.submit(self.root, tid, artifact="approved/第100章_越界.md")
        self.assertIn("质量评分 gate=block", str(ctx.exception))

    # T10 submit 门禁：干净章节 -> 放行 submit（返回 submitted）
    def test_submit_gate_proceed(self):
        tid = self._make_running_task("99", fatal=False)
        st, _ = te.submit(self.root, tid, artifact="approved/第99章_测试.md")
        self.assertEqual(st, "submitted")


if __name__ == "__main__":
    unittest.main(verbosity=2)

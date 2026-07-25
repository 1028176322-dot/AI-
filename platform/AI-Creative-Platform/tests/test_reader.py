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
"""读者模拟（Reader Simulation）端到端回归测试。Phase 2 系统 #3。

覆盖：proceed / caution / block / 落盘 / 契约 / submit 门禁拦截 / submit 放行 / 质量评分回退消费。
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import reader_simulator as rs
import quality_scorer as qs
import task_engine as te

PROCEED_CHAPTER = ("《烟雾篇》\n\n肖凡立于山门，心中忽生寒意。\n"
                   "\"你终于来了。\"黑影冷笑。\n剑光乍起，血溅三尺！\n"
                   "他竟未料到这般杀机。\n远处似有更深的阴谋正在酝酿，谁又能料到结局。\n")
BLOCK_CHAPTER = "《终章》\n\n一切皆已落幕。\n自此再无波澜，皆已了结。\n"
CAUTION_CHAPTER = ("《试探篇》\n\n肖凡心中一惊。\n"
                   "\"你究竟想怎样！\"他怒喝。\n风过山林，并无异样。\n"
                   "远处的雾气却渐渐散了，似有动静。\n")


def _write_chapter(root, sub, fname, text):
    d = os.path.join(root, sub)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, fname)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


class ReaderSimTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="reader_test_")
        _write_chapter(self.root, "chapters/drafts", "第88章_烟.md", PROCEED_CHAPTER)
        _write_chapter(self.root, "chapters/drafts", "第89章_终.md", BLOCK_CHAPTER)
        _write_chapter(self.root, "chapters/drafts", "第90章_探.md", CAUTION_CHAPTER)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    # T1 proceed
    def test_proceed_gate(self):
        rep = rs.simulate(self.root, "chapter", 88, write=False)
        self.assertEqual(rep["gate"]["decision"], "proceed")
        self.assertFalse(rep["fatal"])

    # T2 caution（PI<60）
    def test_caution_gate(self):
        rep = rs.simulate(self.root, "chapter", 90, write=False)
        self.assertEqual(rep["gate"]["decision"], "caution")
        self.assertFalse(rep["fatal"])
        self.assertLess(rep["pi"], 60)

    # T3 block（读者侧致命）
    def test_block_gate(self):
        rep = rs.simulate(self.root, "chapter", 89, write=False)
        self.assertEqual(rep["gate"]["decision"], "block")
        self.assertTrue(rep["fatal"])

    # T4 落盘 + report_id
    def test_write_report(self):
        rep = rs.simulate(self.root, "chapter", 88, write=True, proposed_by="reader-sim")
        self.assertIn("report_id", rep["meta"])
        d = os.path.join(self.root, "analysis", "reader")
        self.assertTrue(os.path.isdir(d))
        files = [f for f in os.listdir(d) if f.endswith(".yaml")]
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith("READ-chapter-88-"))

    # T5 契约段齐备 + gate 枚举
    def test_schema_sections(self):
        rep = rs.simulate(self.root, "chapter", 88, write=False)
        for sec in ("meta", "target", "signals", "reader_index", "pi", "fatal", "gate"):
            self.assertIn(sec, rep)
        self.assertIn(rep["gate"]["decision"], ("proceed", "caution", "block"))
        for k in ("rr01_first_impression", "rr02_fluency", "rr03_emotion",
                  "rr04_anticipation", "rr05_reward", "rr06_fatigue_raw",
                  "rr07_coolpoint", "rr08_info", "immersion", "emotion_curve", "persona"):
            self.assertIn(k, rep["signals"])

    # T6 submit 门禁拦截（reader block）
    def test_submit_blocked_by_reader(self):
        tid = self._make_running_task(89)
        with self.assertRaises(ValueError) as ctx:
            te.submit(self.root, tid, artifact="chapters/drafts/第89章_终.md")
        self.assertIn("读者模拟 gate=block", str(ctx.exception))

    # T7 submit 放行（reader proceed + quality proceed）
    def test_submit_allowed_when_reader_proceed(self):
        tid = self._make_running_task(88)
        state, _ = te.submit(self.root, tid, artifact="chapters/drafts/第88章_烟.md")
        self.assertEqual(state, "submitted")

    # T8 质量评分回退消费 reader 报告
    def test_quality_fallback_consumes_reader(self):
        rs.simulate(self.root, "chapter", 88, write=True, proposed_by="reader-sim")
        rep = qs.score(self.root, "chapter", 88, write=False)
        rev = next((s for s in rep["signals"] if s["name"] == "review"), None)
        self.assertIsNotNone(rev)
        self.assertTrue(rev["consumed"])
        self.assertIn("reader-only", rev["detail"])

    # ── helpers ──
    def _make_running_task(self, chapter_ref):
        tid = "T-CH-%s" % chapter_ref
        te.create_task(self.root, {"task": {
            "id": tid, "version": 1, "type": "chapter_write",
            "title": "写第%s章" % chapter_ref, "status": "ready",
            "priority": "normal", "chapter_ref": str(chapter_ref),
            "agent": {"required_role": "writer"},
        }}, author="test")
        te.claim(self.root, tid, "agent-x", "writer")
        te.start(self.root, tid, "agent-x", "writer")
        return tid


if __name__ == "__main__":
    unittest.main()

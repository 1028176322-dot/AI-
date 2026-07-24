# -*- coding: utf-8 -*-
"""资产管理 e2e 测试（Phase 2 #5）"""
import os
import sys
import shutil
import tempfile
import unittest
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

PLATFORM_ROOT = os.path.normpath(os.path.dirname(TOOLS))
if PLATFORM_ROOT not in sys.path:
    sys.path.insert(0, PLATFORM_ROOT)

import asset_manager


class TestAsset(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        for d in ("NKB", "txt", os.path.join("sources", "inbox"), "artifacts",
                  "analysis", "audit"):
            p = os.path.join(self.root, d)
            os.makedirs(p, exist_ok=True)
        with open(os.path.join(self.root, "project.yaml"), "w", encoding="utf-8") as f:
            f.write(
                "project:\n  id: t\n  name: t\n  type: xuanhuan\n"
                "paths:\n  nkb: ./NKB\n  chapters: ./txt\n  artifacts: ./artifacts\n"
            )

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _nkb(self, name, block):
        with open(os.path.join(self.root, "NKB", name), "w", encoding="utf-8") as f:
            f.write("schema_version: 1.2.0\nproject_id: t\nrecords:\n" + block)

    # ── 1. proceed（健康项目） ──
    def test_proceed(self):
        self._nkb("Characters.yaml", "")
        with open(os.path.join(self.root, "txt", "c1.md"), "w", encoding="utf-8") as f:
            f.write("正文")
        rep = asset_manager.govern(self.root, write=False)
        self.assertEqual(rep["gate"]["decision"], "proceed")
        self.assertFalse(rep["fatal"])
        self.assertEqual(rep["composite"]["health"], 100)

    # ── 2. missing → block（NKB 引用断裂） ──
    def test_missing_block(self):
        self._nkb("Characters.yaml",
                  "  - id: X\n    name: a\n    source: ./sources/missing.md\n")
        rep = asset_manager.govern(self.root, write=False)
        self.assertEqual(rep["gate"]["decision"], "block")
        self.assertTrue(rep["fatal"])
        self.assertTrue(rep["missing"])

    # ── 3. orphan → caution（inbox 未归类） ──
    def test_orphan_caution(self):
        with open(os.path.join(self.root, "sources", "inbox", "stray.md"),
                  "w", encoding="utf-8") as f:
            f.write("散落事实")
        rep = asset_manager.govern(self.root, write=False)
        self.assertEqual(rep["gate"]["decision"], "caution")
        self.assertIn("inbox 未归类", str(rep["orphans"]))

    # ── 4. duplicate → caution（同类型高度相似） ──
    def test_duplicate_caution(self):
        with open(os.path.join(self.root, "txt", "a.md"), "w", encoding="utf-8") as f:
            f.write("肖凡走到了山门前，风吹过松林。")
        with open(os.path.join(self.root, "txt", "b.md"), "w", encoding="utf-8") as f:
            f.write("肖凡走到了山门前，风吹过松林。")
        rep = asset_manager.govern(self.root, write=False)
        self.assertEqual(rep["gate"]["decision"], "caution")
        self.assertTrue(rep["duplicates"])

    # ── 5. 报告落盘 ──
    def test_report_write(self):
        asset_manager.govern(self.root, write=True)
        ap = os.path.join(self.root, "analysis", "asset")
        self.assertTrue(os.path.isdir(ap))
        self.assertTrue(any(f.startswith("AST-") for f in os.listdir(ap)))

    # ── 6. 契约字段齐全 ──
    def test_contract_fields(self):
        rep = asset_manager.govern(self.root, write=False)
        for k in ("meta", "target", "signals", "composite", "fatal", "gate",
                  "orphans", "missing", "duplicates", "dependency_graph",
                  "recommendations"):
            self.assertIn(k, rep)
        self.assertIn("health", rep["composite"])
        self.assertIn("decision", rep["gate"])
        self.assertIn("asset_summary", rep["target"])

    # ── 7. doctor 集成（资产 block → doctor FAIL → exit 1） ──
    def test_doctor_integration_block(self):
        ws = tempfile.mkdtemp()
        try:
            proj = os.path.join(ws, "proj")
            os.makedirs(os.path.join(proj, "NKB"))
            with open(os.path.join(proj, "project.yaml"), "w", encoding="utf-8") as f:
                f.write(
                    "project:\n  id: t\n  name: t\n  type: xuanhuan\n"
                    "requires:\n  platform: \">=2.1.0\"\n  nkb_schema: \">=1.2.0\"\n"
                    "  contracts: \">=1.0.0\"\n"
                    "template:\n  id: xuanhuan\n  version: 1.3.0\n"
                    "paths:\n  nkb: ./NKB\n  chapters: ./txt\n  artifacts: ./artifacts\n"
                )
            with open(os.path.join(proj, "NKB", "Characters.yaml"),
                      "w", encoding="utf-8") as f:
                f.write("schema_version: 1.2.0\nproject_id: t\nrecords:\n"
                        "  - id: X\n    name: a\n    source: ./sources/missing.md\n")
            with open(os.path.join(ws, "workspace.yaml"), "w", encoding="utf-8") as f:
                f.write("workspace:\n  platform: %s\n  projects:\n    - ./proj\n"
                        % PLATFORM_ROOT)
            import platform_cli
            with self.assertRaises(SystemExit) as cm:
                platform_cli.cmd_doctor(argparse.Namespace(workspace=ws))
            self.assertEqual(cm.exception.code, 1)
        finally:
            shutil.rmtree(ws, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

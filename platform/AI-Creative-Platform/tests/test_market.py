# -*- coding: utf-8 -*-
"""test_market.py — Phase 3-6 市场分析 e2e 测试（≥7 用例）"""
import os
import sys
import shutil
import tempfile
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.abspath(os.path.join(HERE, "..", "tools"))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
PLATFORM_ROOT = os.path.abspath(os.path.join(HERE, ".."))

import market as _mk


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class MarketTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.proj, "NKB"))
        mdir = os.path.join(self.proj, "sources", "research", "market")
        # 两个 xuanhuan 信号 + 一个 dushi
        _write(os.path.join(mdir, "trend-xh.yaml"),
               "genre: xuanhuan\n"
               "trend_score: 0.8\ncompetition: 0.4\nreader_demand: 0.7\n"
               "notes: 玄幻回暖\n")
        _write(os.path.join(mdir, "trend-xh2.yaml"),
               "genre: xuanhuan\n"
               "trend_score: 0.9\ncompetition: 0.3\nreader_demand: 0.8\n")
        _write(os.path.join(mdir, "trend-ds.yaml"),
               "genre: dushi\n"
               "trend_score: 0.5\ncompetition: 0.6\nreader_demand: 0.6\n")
        # 临时平台（无 market.yaml → 默认权重）
        self.plat = os.path.join(self.tmp, "plat")
        os.makedirs(os.path.join(self.plat, "registry"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── 1. ingest ──
    def test_ingest(self):
        sigs = _mk.ingest(self.proj)
        self.assertEqual(len(sigs), 3)
        genres = {s["genre"] for s in sigs}
        self.assertEqual(genres, {"xuanhuan", "dushi"})

    # ── 2. score by genre ──
    def test_score(self):
        scores = _mk.score(self.proj, self.plat)
        # xuanhuan: 均值 trend=0.85, comp=0.35, demand=0.75
        # opp = 0.4*0.85 + 0.3*(1-0.35) + 0.3*0.75 = 0.34+0.195+0.225 = 0.76
        self.assertAlmostEqual(scores["xuanhuan"], 0.76, places=2)
        self.assertIn("dushi", scores)

    # ── 3. brief：top opportunity ──
    def test_brief(self):
        b = _mk.brief(self.proj, self.plat)
        self.assertEqual(b["ingested_signals"], 3)
        self.assertIsNotNone(b["top_opportunity"])
        self.assertEqual(b["top_opportunity"]["genre"], "xuanhuan")
        self.assertGreaterEqual(b["top_opportunity"]["score"], b["per_genre_score"]["dushi"])

    # ── 4. sync_nkb 写入 NKB/Market.yaml ──
    def test_sync_nkb(self):
        res = _mk.sync_nkb(self.proj, self.plat, write=True)
        self.assertIn("written", res)
        p = os.path.join(self.proj, "NKB", "Market.yaml")
        self.assertTrue(os.path.isfile(p))
        import _yaml_lite
        d = _yaml_lite.load_file(p)
        self.assertIn("market_facts", d)
        self.assertGreaterEqual(len(d["market_facts"]), 2)

    # ── 5. govern：registry 缺失 → caution ──
    def test_govern_missing_caution(self):
        rep = _mk.govern(self.plat, self.proj, write=False)
        self.assertEqual(rep["gate"]["decision"], "caution")
        self.assertIn("未配置市场分析", rep["gate"]["reasons"][0])

    # ── 6. govern：registry 合法 → proceed ──
    def test_govern_present_proceed(self):
        _write(os.path.join(self.plat, "registry", "market.yaml"),
               "schema_version: 1.0.0\n"
               "weights:\n  trend_score: 0.4\n  competition: 0.3\n  reader_demand: 0.3\n"
               "thresholds:\n  opportunity_floor: 0.5\n")
        rep = _mk.govern(self.plat, self.proj, write=False)
        self.assertEqual(rep["gate"]["decision"], "proceed")

    # ── 7. govern：weights 和不为 1 → block ──
    def test_govern_broken_block(self):
        _write(os.path.join(self.plat, "registry", "market.yaml"),
               "schema_version: 1.0.0\n"
               "weights:\n  trend_score: 0.5\n  competition: 0.5\n  reader_demand: 0.5\n")
        rep = _mk.govern(self.plat, self.proj, write=False)
        self.assertEqual(rep["gate"]["decision"], "block")

    # ── 8. doctor 集成（临时 workspace + platform，含 sources → MarketGov 不阻断）──
    def test_doctor_integration(self):
        ws = tempfile.mkdtemp(prefix="mk_ws_")
        try:
            plat = os.path.join(ws, "platform")
            os.makedirs(os.path.join(plat, "registry"))
            with open(os.path.join(ws, "workspace.yaml"), "w", encoding="utf-8") as f:
                f.write("workspace:\n  name: t\n  platform: ./platform\n  projects: []\n")
            with open(os.path.join(plat, "registry", "versions.yaml"),
                      "w", encoding="utf-8") as f:
                f.write("core:\n  platform: 1.0.0\n")
            real_mem = os.path.join(PLATFORM_ROOT, "memory")
            if os.path.isdir(real_mem):
                shutil.copytree(real_mem, os.path.join(plat, "memory"))
            for f in ("models.yaml", "model-router.yaml", "experiments.yaml", "bi.yaml", "market.yaml"):
                src = os.path.join(PLATFORM_ROOT, "registry", f)
                if os.path.isfile(src):
                    shutil.copy(src, os.path.join(plat, "registry", f))
            # 临时项目（含 sources/research/market）
            proj = os.path.join(ws, "projects", "projA")
            os.makedirs(os.path.join(proj, "NKB"))
            mdir = os.path.join(proj, "sources", "research", "market")
            _write(os.path.join(mdir, "m.yaml"),
                   "genre: xuanhuan\ntrend_score: 0.8\ncompetition: 0.4\nreader_demand: 0.7\n")
            with open(os.path.join(plat, "registry", "projects.yaml"),
                      "w", encoding="utf-8") as f:
                f.write(
                    "schema_version: 1.0.0\n"
                    "projects:\n"
                    "  - id: proj-a\n"
                    "    name: 项目A\n"
                    "    path: ../projects/projA\n"
                    "    type: xuanhuan\n"
                    "    genre: xuanhuan\n"
                    "    status: active\n"
                    "    overrides:\n"
                    "      model_preference: null\n"
                )
            cli = os.path.join(TOOLS, "platform_cli.py")
            r = subprocess.run(
                ["C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe",
                 cli, "--workspace", ws, "doctor"],
                cwd=TOOLS, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, msg=r.stdout + r.stderr)
        finally:
            shutil.rmtree(ws, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

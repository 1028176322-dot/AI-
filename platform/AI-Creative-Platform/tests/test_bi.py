# -*- coding: utf-8 -*-
"""test_bi.py — Phase 3-4 BI 分析 e2e 测试（≥7 用例）"""
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

import bi as _bi


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class BITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # 项目根（含 synthetic quality/reader 数据）
        self.proj = os.path.join(self.tmp, "proj")
        qd = os.path.join(self.proj, "analysis", "quality")
        rd = os.path.join(self.proj, "analysis", "reader")
        _write(os.path.join(qd, "QUAL-c1.yaml"),
               "meta:\n  project: daofa\n  model: model-strong\n  scored_at: 2026-07-20T10:00:00\n"
               "target:\n  target_type: chapter\n  target_id: c1\n"
               "composite:\n  value: 85\n")
        _write(os.path.join(qd, "QUAL-c2.yaml"),
               "meta:\n  project: daofa\n  model: model-fast\n  scored_at: 2026-07-21T10:00:00\n"
               "target:\n  target_type: chapter\n  target_id: c2\n"
               "composite:\n  value: 90\n")
        _write(os.path.join(rd, "READ-c1.yaml"),
               "meta:\n  project: daofa\n  model: model-strong\n  simulated_at: 2026-07-20T11:00:00\n"
               "target:\n  target_type: chapter\n  target_id: c1\n"
               "reader_index: 70\npi: 65\n")
        _write(os.path.join(rd, "READ-c2.yaml"),
               "meta:\n  project: daofa\n  model: model-fast\n  simulated_at: 2026-07-21T11:00:00\n"
               "target:\n  target_type: chapter\n  target_id: c2\n"
               "reader_index: 80\npi: 75\n")
        # 平台根（含 synthetic experiment 样本）
        self.plat = os.path.join(self.tmp, "plat")
        exp_dir = os.path.join(self.plat, "analysis", "experiment")
        _write(os.path.join(exp_dir, "EXP-samples.yaml"),
               "schema_version: 1.0.0\nsamples:\n"
               "  - experiment_id: exp-1\n    unit_id: u1\n    variant: 0\n"
               "    metrics:\n      quality: 88\n      reader: 72\n      ci: 0.96\n      cost: 0.02\n"
               "  - experiment_id: exp-1\n    unit_id: u2\n    variant: 1\n"
               "    metrics:\n      quality: 82\n      reader: 68\n      ci: 0.94\n      cost: 0.03\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── 1. collect 回收记录数 ──
    def test_collect_counts(self):
        recs = _bi.collect(self.plat, self.proj)
        # 2 quality + 2 reader + 2 experiment = 6
        self.assertEqual(len(recs), 6)
        comps = {r["component"] for r in recs}
        self.assertEqual(comps, {"quality", "reader", "experiment"})

    # ── 2. rollup by model（quality 均值）──
    def test_rollup_by_model(self):
        recs = _bi.collect(self.plat, self.proj)
        res = _bi.rollup(recs, "model", "quality")
        self.assertAlmostEqual(res["model-strong"]["mean"], 85.0)
        self.assertAlmostEqual(res["model-fast"]["mean"], 90.0)
        self.assertEqual(res["model-strong"]["n"], 1)

    # ── 3. rollup by project ──
    def test_rollup_by_project(self):
        recs = _bi.collect(self.plat, self.proj)
        res = _bi.rollup(recs, "project", "reader")
        # reader: 70 + 80 = 150 /2 = 75
        self.assertAlmostEqual(res["daofa"]["mean"], 75.0)
        self.assertEqual(res["daofa"]["n"], 2)

    # ── 4. rollup by capability + filter ──
    def test_rollup_by_capability_filter(self):
        recs = _bi.collect(self.plat, self.proj)
        res = _bi.rollup(recs, "capability", "quality", filters={"model": "model-fast"})
        # 仅 model-fast 的 quality（c2=90）
        self.assertAlmostEqual(res["chapter"]["mean"], 90.0)
        self.assertEqual(res["chapter"]["n"], 1)

    # ── 5. time_series 按日 ──
    def test_time_series_by_day(self):
        recs = _bi.collect(self.plat, self.proj)
        series = _bi.time_series(recs, "quality", "day")
        buckets = {p["bucket"] for p in series}
        self.assertIn("2026-07-20", buckets)
        self.assertIn("2026-07-21", buckets)

    # ── 6. dashboard（读 bi.yaml 定义）──
    def test_dashboard_from_registry(self):
        reg_dir = os.path.join(self.plat, "registry")
        os.makedirs(reg_dir, exist_ok=True)
        _write(os.path.join(reg_dir, "bi.yaml"),
               "schema_version: 1.0.0\n"
               "dashboards:\n"
               "  - id: quality-overview\n"
               "    title: 质量总览\n"
               "    metrics: [quality, reader]\n"
               "    dimensions: [model]\n"
               "    filters: {}\n")
        recs = _bi.collect(self.plat, self.proj)
        out = _bi.dashboard(self.plat, self.proj, {
            "id": "quality-overview", "title": "质量总览",
            "metrics": ["quality", "reader"], "dimensions": ["model"], "filters": {}}, recs)
        self.assertEqual(out["id"], "quality-overview")
        self.assertIn("model", out["by_dimension"])
        self.assertEqual(out["record_count"], 6)

    # ── 7. govern：bi.yaml 缺失 → caution（非 fatal）──
    def test_govern_missing_caution(self):
        rep = _bi.govern(self.plat, write=False)
        self.assertEqual(rep["gate"]["decision"], "caution")
        self.assertIn("未配置 BI 仪表盘", rep["gate"]["reasons"][0])

    # ── 8. govern：bi.yaml 合法 → proceed ──
    def test_govern_present_proceed(self):
        reg_dir = os.path.join(self.plat, "registry")
        os.makedirs(reg_dir, exist_ok=True)
        _write(os.path.join(reg_dir, "bi.yaml"),
               "schema_version: 1.0.0\n"
               "dashboards:\n"
               "  - id: d1\n    title: t1\n    metrics: [quality]\n    dimensions: [model]\n    filters: {}\n")
        rep = _bi.govern(self.plat, write=False)
        self.assertEqual(rep["gate"]["decision"], "proceed")
        self.assertEqual(rep["response"]["dashboards"], 1)

    # ── 9. govern：bi.yaml 损坏（metrics 非法）→ block ──
    def test_govern_broken_block(self):
        reg_dir = os.path.join(self.plat, "registry")
        os.makedirs(reg_dir, exist_ok=True)
        _write(os.path.join(reg_dir, "bi.yaml"),
               "schema_version: 1.0.0\n"
               "dashboards:\n"
               "  - id: d1\n    title: t1\n    metrics: [bogus]\n    dimensions: [model]\n    filters: {}\n")
        rep = _bi.govern(self.plat, write=False)
        self.assertEqual(rep["gate"]["decision"], "block")

    # ── 10. doctor 集成（临时 workspace + platform，合规 → exit 0）──
    def test_doctor_integration(self):
        ws = tempfile.mkdtemp(prefix="bi_ws_")
        try:
            plat = os.path.join(ws, "platform")
            os.makedirs(os.path.join(plat, "registry"))
            with open(os.path.join(ws, "workspace.yaml"), "w", encoding="utf-8") as f:
                f.write("workspace:\n  name: t\n  platform: ./platform\n  projects: []\n")
            with open(os.path.join(plat, "registry", "versions.yaml"),
                      "w", encoding="utf-8") as f:
                f.write("core:\n  platform: 1.0.0\n")
            # 复制真实 memory/ + 全部带 gov 块的注册表
            real_mem = os.path.join(PLATFORM_ROOT, "memory")
            if os.path.isdir(real_mem):
                shutil.copytree(real_mem, os.path.join(plat, "memory"))
            for f in ("models.yaml", "model-router.yaml", "experiments.yaml", "bi.yaml"):
                src = os.path.join(PLATFORM_ROOT, "registry", f)
                if os.path.isfile(src):
                    shutil.copy(src, os.path.join(plat, "registry", f))
            # 临时项目（含 NKB）供 MultiProjGov + 采集空数据
            proj = os.path.join(ws, "projects", "projA")
            os.makedirs(os.path.join(proj, "NKB"))
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

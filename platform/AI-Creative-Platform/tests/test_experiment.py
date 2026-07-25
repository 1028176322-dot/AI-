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
"""test_experiment.py — Phase 3-3 实验系统 e2e 测试（≥7 用例）"""
import os
import sys
import json
import shutil
import tempfile
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.abspath(os.path.join(HERE, "..", "tools"))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
PLATFORM_ROOT = os.path.abspath(os.path.join(HERE, ".."))

import experiment as _exp


class ExperimentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        reg = os.path.join(self.tmp, "registry")
        os.makedirs(reg)
        # 真实 experiments.yaml 含一个合法 2-variant 实验 exp-prompt-warmup
        src = os.path.join(PLATFORM_ROOT, "registry", "experiments.yaml")
        if os.path.isfile(src):
            shutil.copy(src, os.path.join(reg, "experiments.yaml"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── 1. define 新实验 ──
    def test_define(self):
        ok, errs, eid = _exp.define(self.tmp, {
            "id": "exp-x", "name": "X", "variants": [{"model": "model-fast", "prompt": "a", "temp": 0.5}],
            "split": {"by": "random"}, "metrics": ["quality"], "min_samples": 4}, write=True)
        self.assertTrue(ok, errs)
        self.assertEqual(eid, "exp-x")
        self.assertIsNotNone(_exp.get_experiment(self.tmp, "exp-x"))

    # ── 2. 确定性分配（同 unit 同 variant）──
    def test_assign_deterministic(self):
        exp = _exp.get_experiment(self.tmp, "exp-prompt-warmup")
        v1 = _exp.assign_variant(exp, "ch-001")
        v2 = _exp.assign_variant(exp, "ch-001")
        self.assertEqual(v1, v2)
        # 2-variant ratio=0.5：ch-001 与 ch-002 大概率分不同（至少确定性）
        self.assertIn(v1, (0, 1))

    # ── 3. 回收样本 + 聚合 ──
    def test_record_and_aggregate(self):
        _exp.record_sample(self.tmp, "exp-prompt-warmup", "ch-001",
                          {"quality": 80, "reader": 70, "ci": 95, "cost": 1.0}, write=True)
        _exp.record_sample(self.tmp, "exp-prompt-warmup", "ch-002",
                          {"quality": 60, "reader": 50, "ci": 90, "cost": 2.0}, write=True)
        agg = _exp.aggregate(self.tmp, "exp-prompt-warmup")
        self.assertIsNotNone(agg)
        # 两个样本应分属两个 variant（ratio=0.5，ch-001/002 不同桶）
        total = sum(v.get("_n", 0) for v in agg.values())
        self.assertEqual(total, 2)

    # ── 4. 判定胜者（样本充足）──
    def test_decide_winner_enough_samples(self):
        eid = "exp-prompt-warmup"
        exp = _exp.get_experiment(self.tmp, eid)
        # 从大池中选 unit，确保两 variant 各获 >= min_samples 样本
        pool = ["unit-%03d" % i for i in range(300)]
        v0 = [u for u in pool if _exp.assign_variant(exp, u) == 0][:8]
        v1 = [u for u in pool if _exp.assign_variant(exp, u) == 1][:8]
        self.assertGreaterEqual(len(v0), 8)
        self.assertGreaterEqual(len(v1), 8)
        for u in v0:
            _exp.record_sample(self.tmp, eid, u,
                              {"quality": 90, "reader": 80, "ci": 99, "cost": 1.0}, write=True)
        for u in v1:
            _exp.record_sample(self.tmp, eid, u,
                              {"quality": 40, "reader": 30, "ci": 80, "cost": 1.0}, write=True)
        w = _exp.decide_winner(self.tmp, eid)
        self.assertIsNotNone(w)
        self.assertEqual(w["primary_metric"], "quality")
        self.assertEqual(w["winner"], 0)  # variant0 高分胜出

    # ── 5. 样本不足不判定 ──
    def test_decide_winner_insufficient(self):
        w = _exp.decide_winner(self.tmp, "exp-prompt-warmup")  # 0 样本
        self.assertIsNone(w)

    # ── 6. govern proceed / block ──
    def test_govern_proceed(self):
        rep = _exp.govern(self.tmp, write=False)
        self.assertEqual(rep["gate"]["decision"], "proceed")
        self.assertEqual(rep["composite"]["health"], 100)

    def test_govern_block_malformed(self):
        reg = os.path.join(self.tmp, "registry", "experiments.yaml")
        with open(reg, "w", encoding="utf-8") as f:
            f.write(
                "schema_version: \"1.0.0\"\n"
                "experiments:\n"
                "  - id: bad\n"
                "    variants: []\n"          # 无 variant → block
                "    split:\n"
                "      by: random\n"
                "    metrics: [quality]\n"
                "    min_samples: 4\n"
            )
        rep = _exp.govern(self.tmp, write=False)
        self.assertEqual(rep["gate"]["decision"], "block")

    # ── 7. doctor 集成（临时 workspace + platform，合规 → exit 0）──
    def test_doctor_integration(self):
        ws = tempfile.mkdtemp(prefix="exp_ws_")
        try:
            plat = os.path.join(ws, "platform")
            os.makedirs(os.path.join(plat, "registry"))
            with open(os.path.join(ws, "workspace.yaml"), "w", encoding="utf-8") as f:
                f.write("workspace:\n  name: t\n  platform: ./platform\n  projects: []\n")
            with open(os.path.join(plat, "registry", "versions.yaml"), "w", encoding="utf-8") as f:
                f.write("core:\n  platform: 1.0.0\n")
            real_mem = os.path.join(PLATFORM_ROOT, "memory")
            if os.path.isdir(real_mem):
                shutil.copytree(real_mem, os.path.join(plat, "memory"))
            for f in ("models.yaml", "model-router.yaml", "projects.yaml", "experiments.yaml"):
                src = os.path.join(PLATFORM_ROOT, "registry", f)
                if os.path.isfile(src):
                    shutil.copy(src, os.path.join(plat, "registry", f))
            os.makedirs(os.path.join(plat, "projX", "NKB"), exist_ok=True)
            with open(os.path.join(plat, "registry", "projects.yaml"), "w", encoding="utf-8") as f:
                f.write(
                    "schema_version: \"1.0.0\"\n"
                    "projects:\n"
                    "  - id: tmp-p\n"
                    "    name: tmp\n"
                    "    path: ./projX\n"
                    "    type: xuanhuan\n"
                    "    genre: xuanhuan\n"
                    "    status: active\n"
                    "    overrides:\n"
                    "      model_preference: null\n"
                )
            cli = os.path.join(_PLAT2, "cli", "platform.py")
            r = subprocess.run(
                ["C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe",
                 cli, "--workspace", ws, "doctor"],
                cwd=_PLAT2, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, msg=r.stdout + r.stderr)
        finally:
            shutil.rmtree(ws, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

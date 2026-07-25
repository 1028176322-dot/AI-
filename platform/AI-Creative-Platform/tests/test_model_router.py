#!/usr/bin/env python3
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
"""test_model_router.py — Phase 3-1 模型布线器 e2e 测试（≥7 用例）"""
import os
import sys
import json
import tempfile
import shutil
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.abspath(os.path.join(HERE, "..", "tools"))
sys.path.insert(0, TOOLS)
import model_router as _mr  # noqa: E402

PLATFORM_ROOT = os.path.abspath(os.path.join(HERE, ".."))

_MODELS = """schema_version: "1.0.0"
models:
  - id: model-fast
    endpoint: local://fast
    ctx_window: 32000
    cost_per_1k_in: 0.0
    cost_per_1k_out: 1.0
    quality_tier: 1
    modalities: [text]
    supports: [chapter_write, memory_gov, asset_mgmt, model_route]
    available: true
  - id: model-strong
    endpoint: local://strong
    ctx_window: 128000
    cost_per_1k_in: 0.0
    cost_per_1k_out: 10.0
    quality_tier: 3
    modalities: [text]
    supports: [chapter_write, chapter_review]
    available: true
  - id: model-cheap
    endpoint: local://cheap
    ctx_window: 8000
    cost_per_1k_in: 0.0
    cost_per_1k_out: 0.1
    quality_tier: 1
    modalities: [text]
    supports: [chapter_write, dialogue_expand]
    available: true
"""

_ROUTER = """schema_version: "1.0.0"
default: model-fast
rules:
  - match:
      role: writer
      quality_tier_min: 2
    primary: model-strong
    fallback: [model-fast]
  - match:
      role: fixer
    primary: model-fast
    fallback: [model-cheap]
  - match:
      capability: memory_gov
    primary: model-fast
    fallback: []
"""


class ModelRouterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.reg = os.path.join(self.tmp, "registry")
        os.makedirs(self.reg)
        with open(os.path.join(self.reg, "models.yaml"), "w", encoding="utf-8") as f:
            f.write(_MODELS)
        with open(os.path.join(self.reg, "model-router.yaml"), "w", encoding="utf-8") as f:
            f.write(_ROUTER)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_resolve_writer_primary_strong(self):
        r = _mr.resolve(self.tmp, role="writer", capability="chapter_write", quality_tier=3)
        self.assertIsNotNone(r)
        self.assertEqual(r["model_id"], "model-strong")

    def test_resolve_fallback_when_primary_unavailable(self):
        # 让 model-strong 不可用 → 回退 model-fast（用 model-strong 专属锚点，避免误命中 model-fast 的 available 行）
        models = _MODELS.replace(
            "    supports: [chapter_write, chapter_review]\n    available: true",
            "    supports: [chapter_write, chapter_review]\n    available: false")
        with open(os.path.join(self.reg, "models.yaml"), "w", encoding="utf-8") as f:
            f.write(models)
        r = _mr.resolve(self.tmp, role="writer", capability="chapter_write", quality_tier=3)
        self.assertIsNotNone(r)
        self.assertEqual(r["model_id"], "model-fast")

    def test_resolve_budget_chooses_cheap(self):
        # fixer 链: fast(1.0) 超预算 → cheap(0.1) 在预算内 → 选 model-cheap
        r = _mr.resolve(self.tmp, role="fixer", capability="chapter_write",
                        cost_budget=0.5)
        self.assertIsNotNone(r)
        self.assertEqual(r["model_id"], "model-cheap")

    def test_resolve_unknown_role_uses_default(self):
        r = _mr.resolve(self.tmp, role="planner", capability="memory_gov")
        self.assertIsNotNone(r)
        self.assertEqual(r["model_id"], "model-fast")

    def test_resolve_capability_falls_through(self):
        r = _mr.resolve(self.tmp, capability="memory_gov")
        self.assertIsNotNone(r)
        self.assertEqual(r["model_id"], "model-fast")
        self.assertIn("model-fast", r["decision_path"]["tried"])

    def test_govern_block_no_available(self):
        models = _MODELS.replace("available: true", "available: false")
        with open(os.path.join(self.reg, "models.yaml"), "w", encoding="utf-8") as f:
            f.write(models)
        rep = _mr.govern(self.tmp, write=False)
        self.assertEqual(rep["gate"]["decision"], "block")
        self.assertTrue(rep["gate"]["reasons"])

    def test_govern_caution_unknown_model(self):
        router = _ROUTER.replace("primary: model-strong", "primary: ghost-model")
        with open(os.path.join(self.reg, "model-router.yaml"), "w", encoding="utf-8") as f:
            f.write(router)
        rep = _mr.govern(self.tmp, write=False)
        self.assertEqual(rep["gate"]["decision"], "caution")
        self.assertIn("ghost-model", rep["gate"]["reasons"][0])

    def test_govern_proceed_real(self):
        rep = _mr.govern(self.tmp, write=False)
        self.assertEqual(rep["gate"]["decision"], "proceed")
        self.assertEqual(rep["composite"]["health"], 100)

    def test_report_write_readable(self):
        rep = _mr.govern(self.tmp, write=True)
        out_dir = os.path.join(self.tmp, "analysis", "model-router")
        files = [f for f in os.listdir(out_dir) if f.endswith(".yaml")]
        self.assertTrue(files)
        with open(os.path.join(out_dir, files[0]), "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["gate"]["decision"], "proceed")


if __name__ == "__main__":
    unittest.main(verbosity=2)

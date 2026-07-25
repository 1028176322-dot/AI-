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
"""test_multi_project.py — Phase 3-2 多项目管理 e2e 测试（≥7 用例）"""
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

import multi_project as _mp


class MultiProjectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        reg = os.path.join(self.tmp, "registry")
        os.makedirs(reg)
        # 复制 model-router + 实验 注册表（dispatch 协同 resolve / ExpGov 依赖）
        for f in ("models.yaml", "model-router.yaml", "experiments.yaml"):
            src = os.path.join(PLATFORM_ROOT, "registry", f)
            if os.path.isfile(src):
                shutil.copy(src, os.path.join(reg, f))
        # 一个真实项目目录（含 NKB），供隔离解析 / govern 使用
        self.proj = os.path.join(self.tmp, "projA")
        os.makedirs(os.path.join(self.proj, "NKB"))
        with open(os.path.join(reg, "projects.yaml"), "w", encoding="utf-8") as f:
            f.write(
                "schema_version: \"1.0.0\"\n"
                "projects:\n"
                "  - id: proj-a\n"
                "    name: 项目A\n"
                "    path: ./projA\n"
                "    type: xuanhuan\n"
                "    genre: xuanhuan\n"
                "    status: active\n"
                "    overrides:\n"
                "      model_preference: null\n"
            )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── 1. register + list ──
    def test_register_and_list(self):
        ok, errs, _ = _mp.register(self.tmp, {
            "id": "proj-b", "name": "项目B", "path": "./projB",
            "type": "dushi", "genre": "dushi", "status": "active"}, write=True)
        self.assertTrue(ok, errs)
        ids = [p["id"] for p in _mp.list_projects(self.tmp)]
        self.assertIn("proj-a", ids)
        self.assertIn("proj-b", ids)

    # ── 2. get_project ──
    def test_get_project(self):
        p = _mp.get_project(self.tmp, "proj-a")
        self.assertIsNotNone(p)
        self.assertEqual(p["type"], "xuanhuan")
        self.assertIsNone(_mp.get_project(self.tmp, "nope"))

    # ── 3. 隔离等级解析：global ──
    def test_isolation_global(self):
        r = _mp.resolve_isolation(self.tmp, "global")
        self.assertEqual(r["level"], "global")
        self.assertEqual(r["resolved_path"], "memory/global")
        self.assertIsNone(r["source_project"])

    # ── 4. 隔离等级解析：project ──
    def test_isolation_project(self):
        r = _mp.resolve_isolation(self.tmp, "project", project_id="proj-a")
        self.assertEqual(r["source_project"], "proj-a")
        self.assertIn("NKB", r["resolved_path"])

    # ── 5. 隔离等级解析：chapter（需 project） ──
    def test_isolation_chapter(self):
        r = _mp.resolve_isolation(self.tmp, "chapter", key="c1.md", project_id="proj-a")
        self.assertEqual(r["source_project"], "proj-a")
        self.assertIn("txt/c1.md", r["resolved_path"])
        # 缺 project_id → 无法解析
        r2 = _mp.resolve_isolation(self.tmp, "chapter")
        self.assertIsNone(r2["resolved_path"])

    # ── 6. dispatch 协同 model-router ──
    def test_dispatch_uses_model_router(self):
        r = _mp.dispatch(self.tmp, "proj-a", role="writer",
                         capability="chapter_write", quality_tier=3)
        self.assertIsNotNone(r)
        self.assertEqual(r["project_id"], "proj-a")
        self.assertIsNotNone(r["model_resolution"])
        self.assertEqual(r["model_resolution"]["model_id"], "model-strong")

    # ── 7. govern proceed ──
    def test_govern_proceed(self):
        rep = _mp.govern(self.tmp, write=False)
        self.assertEqual(rep["gate"]["decision"], "proceed")
        self.assertEqual(rep["composite"]["health"], 100)
        self.assertEqual(rep["response"]["projects"], 1)

    # ── 8. govern block：项目路径缺失 ──
    def test_govern_block_missing_path(self):
        # 改写 projects.yaml 指向不存在的目录
        reg = os.path.join(self.tmp, "registry", "projects.yaml")
        with open(reg, "w", encoding="utf-8") as f:
            f.write(
                "schema_version: \"1.0.0\"\n"
                "projects:\n"
                "  - id: proj-x\n"
                "    path: ./ghost\n"
                "    type: xuanhuan\n"
            )
        rep = _mp.govern(self.tmp, write=False)
        self.assertEqual(rep["gate"]["decision"], "block")
        self.assertTrue(rep["gate"]["reasons"])

    # ── 9. govern caution：项目存在但无 NKB ──
    def test_govern_caution_no_nkb(self):
        proj = os.path.join(self.tmp, "projNoNkb")
        os.makedirs(proj)  # 无 NKB 子目录
        reg = os.path.join(self.tmp, "registry", "projects.yaml")
        with open(reg, "w", encoding="utf-8") as f:
            f.write(
                "schema_version: \"1.0.0\"\n"
                "projects:\n"
                "  - id: no-nkb\n"
                "    path: ./projNoNkb\n"
                "    type: xuanhuan\n"
            )
        rep = _mp.govern(self.tmp, write=False)
        self.assertEqual(rep["gate"]["decision"], "caution")
        self.assertIn("无 NKB", rep["gate"]["reasons"][0])

    # ── 10. doctor 集成（临时 workspace + platform，合规 → exit 0）──
    def test_doctor_integration(self):
        ws = tempfile.mkdtemp(prefix="mp_ws_")
        try:
            plat = os.path.join(ws, "platform")
            os.makedirs(os.path.join(plat, "registry"))
            with open(os.path.join(ws, "workspace.yaml"), "w", encoding="utf-8") as f:
                f.write("workspace:\n  name: t\n  platform: ./platform\n  projects: []\n")
            with open(os.path.join(plat, "registry", "versions.yaml"),
                      "w", encoding="utf-8") as f:
                f.write("core:\n  platform: 1.0.0\n")
            # 复制真实 memory/（真实平台 MemoryGov 健康分100，保证有效）+ 全部带 gov 块的注册表
            # 注意：doctor 含 MemoryGov/ModelGov/MultiProjGov/ExpGov 四块，缺一即 block → exit 1
            real_mem = os.path.join(PLATFORM_ROOT, "memory")
            if os.path.isdir(real_mem):
                shutil.copytree(real_mem, os.path.join(plat, "memory"))
            for f in ("models.yaml", "model-router.yaml", "experiments.yaml"):
                src = os.path.join(PLATFORM_ROOT, "registry", f)
                if os.path.isfile(src):
                    shutil.copy(src, os.path.join(plat, "registry", f))
            # 临时项目（含 NKB）供多项目注册表指向
            proj = os.path.join(ws, "projects", "projA")
            os.makedirs(os.path.join(proj, "NKB"))
            with open(os.path.join(plat, "registry", "projects.yaml"),
                      "w", encoding="utf-8") as f:
                f.write(
                    "schema_version: \"1.0.0\"\n"
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

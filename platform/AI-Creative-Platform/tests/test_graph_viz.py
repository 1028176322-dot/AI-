# -*- coding: utf-8 -*-
"""test_graph_viz.py — Phase 3-5 图谱可视化 e2e 测试（≥7 用例）"""
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

import graph_viz as _gv


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class GraphVizTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "proj")
        nkb = os.path.join(self.proj, "NKB")
        os.makedirs(nkb)
        # Characters：肖凡→沈括(relationship)，肖凡→清虚观(faction)
        _write(os.path.join(nkb, "Characters.yaml"),
               "schema_version: 1.2.0\nproject_id: t\nrecords:\n"
               "  - id: xiaofan\n    name: 肖凡\n    relationships:\n"
               "      - target: shenkuo\n        kind: 师徒\n"
               "    faction: 清虚观\n"
               "  - id: shenkuo\n    name: 沈括\n")
        # Events：灭门案 participants=[xiaofan, shenkuo]
        _write(os.path.join(nkb, "Events.yaml"),
               "schema_version: 1.2.0\nproject_id: t\nrecords:\n"
               "  - id: case-47\n    name: 灭门案\n    participants: [xiaofan, shenkuo]\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── 1. build：character + 关系边 ──
    def test_build_characters(self):
        g = _gv.build_graph(self.proj)
        ids = {n["id"] for n in g["nodes"]}
        self.assertIn("xiaofan", ids)
        self.assertIn("shenkuo", ids)
        self.assertIn("faction:清虚观", ids)  # 阵营归属节点
        kinds = {e["kind"] for e in g["edges"]}
        self.assertIn("师徒", kinds)
        self.assertIn("affiliation", kinds)

    # ── 2. build：event + participant 边 ──
    def test_build_events(self):
        g = _gv.build_graph(self.proj)
        ev_edges = [e for e in g["edges"] if e["kind"] == "participant"]
        self.assertEqual(len(ev_edges), 2)  # 灭门案 → 肖凡/沈括
        srcs = {e["source"] for e in ev_edges}
        self.assertIn("case-47", srcs)

    # ── 3. build：空 NKB → 0 节点/0 边 ──
    def test_build_empty(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(os.path.join(empty, "NKB"))
        g = _gv.build_graph(empty)
        self.assertEqual(len(g["nodes"]), 0)
        self.assertEqual(len(g["edges"]), 0)

    # ── 4. render：HTML 含 svg + 节点标签 ──
    def test_render_html(self):
        g = _gv.build_graph(self.proj)
        html = _gv.render_html(g, title="测试图谱")
        self.assertIn("<svg", html)
        self.assertIn("肖凡", html)
        self.assertIn("清虚观", html)

    # ── 5. govern：悬空边 → caution ──
    def test_govern_dangling_caution(self):
        nkb = os.path.join(self.proj, "NKB")
        _write(os.path.join(nkb, "Characters.yaml"),
               "schema_version: 1.2.0\nrecords:\n"
               "  - id: a\n    name: A\n    relationships:\n      - {target: ghost, kind: 敌对}\n")
        rep = _gv.govern(self.proj, write=False)
        self.assertEqual(rep["gate"]["decision"], "caution")
        self.assertIn("悬空边", rep["gate"]["reasons"][0])

    # ── 6. govern：空图 → proceed ──
    def test_govern_empty_proceed(self):
        empty = os.path.join(self.tmp, "empty2")
        os.makedirs(os.path.join(empty, "NKB"))
        rep = _gv.govern(empty, write=False)
        self.assertEqual(rep["gate"]["decision"], "proceed")
        self.assertEqual(rep["response"]["nodes"], 0)

    # ── 7. doctor 集成（临时 workspace + platform，含 NKB → GraphGov 不阻断）──
    def test_doctor_integration(self):
        ws = tempfile.mkdtemp(prefix="gv_ws_")
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
            for f in ("models.yaml", "model-router.yaml", "experiments.yaml", "bi.yaml"):
                src = os.path.join(PLATFORM_ROOT, "registry", f)
                if os.path.isfile(src):
                    shutil.copy(src, os.path.join(plat, "registry", f))
            # 临时项目（含 NKB，空）→ GraphGov proceed
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

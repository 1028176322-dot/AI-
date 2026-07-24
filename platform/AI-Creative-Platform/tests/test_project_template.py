# -*- coding: utf-8 -*-
"""test_project_template.py — Phase 3-7 项目模板 e2e 测试（≥7 用例）"""
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

import project_template as _pt
import _yaml_lite

PY = "C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe"

_BASE_NKB = ["Canon", "Characters", "Timeline", "WorldState", "Events",
             "Foreshadow", "Assets", "Terminology", "StoryState",
             "ReaderState", "Graph"]


def _write_workspace(ws_root, projects=None):
    projects = projects or []
    with open(os.path.join(ws_root, "workspace.yaml"), "w", encoding="utf-8") as f:
        f.write("workspace:\n  name: t\n  platform: ./platform\n  projects: %s\n"
                % (projects if projects else "[]"))


def _make_template(platform_root, genre="xuanhuan", schema_version="1.3.0"):
    td = os.path.join(platform_root, "templates", genre)
    os.makedirs(td, exist_ok=True)
    with open(os.path.join(td, "profile.yaml"), "w", encoding="utf-8") as f:
        f.write(
            'schema_version: "%s"\n'
            "genre: %s\n"
            "display_name: 测试类型\n" % (schema_version, genre))
    with open(os.path.join(td, "nkb-schema-extension.yaml"), "w", encoding="utf-8") as f:
        f.write('schema_version: "%s"\nadd_fields: {}\n' % schema_version)


class ProjectTemplateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.plat = os.path.join(self.tmp, "platform")
        self.ws = os.path.join(self.tmp, "ws")
        os.makedirs(self.plat)
        os.makedirs(self.ws)
        _write_workspace(self.ws)
        _make_template(self.plat)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── 1. scaffold → project.yaml ──
    def test_scaffold_creates_project_yaml(self):
        ok, errs, proot = _pt.scaffold(self.plat, self.ws, "小说B", "xuanhuan", write=True)
        self.assertTrue(ok, errs)
        py = os.path.join(proot, "project.yaml")
        self.assertTrue(os.path.isfile(py))
        d = _yaml_lite.load_file(py)
        self.assertEqual(d["project"]["id"], "novel-b")
        self.assertEqual(d["project"]["name"], "小说B")
        self.assertEqual(d["project"]["type"], "xuanhuan")
        self.assertEqual(d["requires"]["templates"]["xuanhuan"], ">=1.3.0")

    # ── 2. scaffold → 空 NKB（基础 11 组件 + 索引 + Derived）──
    def test_scaffold_creates_nkb(self):
        ok, _, proot = _pt.scaffold(self.plat, self.ws, "小说B", "xuanhuan", write=True)
        self.assertTrue(ok)
        nkb = os.path.join(proot, "NKB")
        self.assertTrue(os.path.isdir(nkb))
        for c in _BASE_NKB:
            self.assertTrue(os.path.isfile(os.path.join(nkb, "%s.yaml" % c)),
                            "缺 NKB 组件 %s" % c)
        self.assertTrue(os.path.isfile(os.path.join(nkb, "NKB.md")))
        self.assertTrue(os.path.isfile(os.path.join(nkb, "Derived.yaml")))

    # ── 3. scaffold → 市场钩子（sources/research/market/）──
    def test_scaffold_market_hook(self):
        ok, _, proot = _pt.scaffold(self.plat, self.ws, "小说B", "xuanhuan", write=True)
        self.assertTrue(ok)
        md = os.path.join(proot, "sources", "research", "market")
        self.assertTrue(os.path.isdir(md))
        self.assertTrue(os.path.isfile(os.path.join(md, "README.md")))
        ex = os.path.join(md, "TEMPLATE-xuanhuan.yaml.example")
        self.assertTrue(os.path.isfile(ex))
        # 模板为 .example，不应被 market.ingest 的 *.yaml glob 命中
        self.assertFalse(ex.endswith(".yaml"))

    # ── 4. register → 写 registry/projects.yaml ──
    def test_register_writes_projects_yaml(self):
        ok, _, proot = _pt.scaffold(self.plat, self.ws, "小说B", "xuanhuan", write=True)
        self.assertTrue(ok)
        rok, rerrs, entry = _pt.register_multi_project(
            self.plat, self.ws, "小说B", "xuanhuan", proot=proot, write=True)
        self.assertTrue(rok, rerrs)
        reg = _yaml_lite.load_file(os.path.join(self.plat, "registry", "projects.yaml"))
        ids = [p["id"] for p in reg["projects"]]
        self.assertIn("novel-b", ids)

    # ── 5. register 幂等：重复 id 拒绝且不重复写入 ──
    def test_register_idempotent(self):
        ok, _, proot = _pt.scaffold(self.plat, self.ws, "小说B", "xuanhuan", write=True)
        self.assertTrue(ok)
        _pt.register_multi_project(self.plat, self.ws, "小说B", "xuanhuan",
                                   proot=proot, write=True)
        rok2, _, _ = _pt.register_multi_project(
            self.plat, self.ws, "小说B", "xuanhuan", proot=proot, write=True)
        self.assertFalse(rok2, "重复注册应被拒绝")
        reg = _yaml_lite.load_file(os.path.join(self.plat, "registry", "projects.yaml"))
        n = sum(1 for p in reg["projects"] if p["id"] == "novel-b")
        self.assertEqual(n, 1, "不应重复写入")

    # ── 6. scaffold 幂等：目录已存在则拒绝（不覆盖）──
    def test_scaffold_idempotent(self):
        ok1, _, proot = _pt.scaffold(self.plat, self.ws, "小说B", "xuanhuan", write=True)
        self.assertTrue(ok1)
        sentinel = os.path.join(proot, "SENTINEL.txt")
        with open(sentinel, "w", encoding="utf-8") as f:
            f.write("keep")
        ok2, errs2, _ = _pt.scaffold(self.plat, self.ws, "小说B", "xuanhuan", write=True)
        self.assertFalse(ok2, "目录已存在应拒绝脚手架")
        self.assertTrue(os.path.isfile(sentinel), "既有项目不应被覆盖")

    # ── 7. govern caution：templates/ 缺失 ──
    def test_govern_missing_template_caution(self):
        # 用无模板的 platform
        bare = os.path.join(self.tmp, "bare")
        os.makedirs(bare)
        rep = _pt.govern(bare, write=False)
        self.assertEqual(rep["gate"]["decision"], "caution")
        self.assertTrue(rep["gate"]["reasons"])

    # ── 8. govern proceed：模板齐备且注册项目 genre 有对应模板 ──
    def test_govern_present_proceed(self):
        # 注册一个 xuanhuan 项目（路径无需真实存在，TemplateGov 只校验 genre↔模板）
        import multi_project as _mp
        _mp.register(self.plat, {
            "id": "proj-x", "name": "X", "path": "./x",
            "type": "xuanhuan", "genre": "xuanhuan", "status": "active"}, write=True)
        rep = _pt.govern(self.plat, write=False)
        self.assertEqual(rep["gate"]["decision"], "proceed")
        self.assertEqual(rep["response"]["templates"], 1)

    # ── 9. doctor 集成（临时 workspace + platform，合规 → exit 0）──
    def test_doctor_integration(self):
        ws = tempfile.mkdtemp(prefix="pt_ws_")
        try:
            plat = os.path.join(ws, "platform")
            os.makedirs(os.path.join(plat, "registry"))
            _write_workspace(ws)
            with open(os.path.join(plat, "registry", "versions.yaml"),
                      "w", encoding="utf-8") as f:
                f.write("core:\n  platform: 1.0.0\n")
            # 复制真实 memory/（MemoryGov 健康分100）+ 全部带 gov 块的注册表
            real_mem = os.path.join(PLATFORM_ROOT, "memory")
            if os.path.isdir(real_mem):
                shutil.copytree(real_mem, os.path.join(plat, "memory"))
            for f in ("models.yaml", "model-router.yaml", "experiments.yaml",
                      "bi.yaml", "market.yaml"):
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
            # 模板（P3-7）
            _make_template(plat)
            cli = os.path.join(TOOLS, "platform_cli.py")
            r = subprocess.run(
                [PY, cli, "--workspace", ws, "doctor"],
                cwd=TOOLS, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, msg=r.stdout + r.stderr)
            self.assertIn("TemplateGov", r.stdout)
            self.assertIn("PASS", r.stdout)
        finally:
            shutil.rmtree(ws, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

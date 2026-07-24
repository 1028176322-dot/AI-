"""内存治理（Memory Governance）e2e 回归测试 · Phase 2 #4

覆盖：ok(proceed) / block(SC2 level↔dir) / block(SC3 status↔位置)
     / caution(SC4 晋升门槛) / caution(SC5 重复) / 落盘 / 契约 / doctor 集成。
"""
import os
import sys
import tempfile
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import memory_governor as mg

VALID_GLOBAL = """id: MEM-G-001
level: global
problem: 修复人物 OOC 后造成剧情链断裂
root_cause: 修改人物决策但未重算后续因果
action:
  - 重审人物动机
  - 重审当前场景因果
  - 重审后续剧情依赖
validated_projects: 3
confidence: 0.93
status: active
"""

VALID_GENRE = """id: MEM-XH-014
level: genre
genre: xuanhuan
problem: 连续升级导致爽感疲劳
root_cause: 同类奖励密集触发，边际递减
action:
  - 两次能力升级之间插入外部冲突
  - 第三次同类升级前更换奖励类型
validated_projects: 2
confidence: 0.85
status: active
"""


def _write(fp, content):
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        f.write(content)


def _mk_valid_mem(root):
    """构造一份合规的 memory/ 四层（global+genre 有效，含 README）。"""
    mem = os.path.join(root, "memory")
    _write(os.path.join(mem, "global", "MEM-G-001.yaml"), VALID_GLOBAL)
    _write(os.path.join(mem, "global", "README.md"), "# Global\n")
    gdir = os.path.join(mem, "genre", "xuanhuan")
    _write(os.path.join(gdir, "MEM-XH-014.yaml"), VALID_GENRE)
    _write(os.path.join(gdir, "README.md"), "# xuanhuan\n")
    _write(os.path.join(mem, "rejected", "README.md"), "# Rejected\n")
    return mem


class TestMemoryGov(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="mem_test_")
        self.mem = _mk_valid_mem(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_ok_proceed(self):
        rep = mg.govern(self.root, write=False)
        self.assertEqual(rep["gate"]["decision"], "proceed")
        self.assertEqual(rep["composite"]["health"], 100)
        self.assertFalse(rep["fatal"])

    def test_block_sc2_level_dir(self):
        # 把 level=genre 的文件放到 global/ → SC2 结构错配 → block
        _write(os.path.join(self.mem, "global", "MEM-XH-999.yaml"),
               VALID_GENRE.replace("MEM-XH-014", "MEM-XH-999"))
        rep = mg.govern(self.root, write=False)
        self.assertEqual(rep["gate"]["decision"], "block")
        self.assertTrue(rep["fatal"])

    def test_block_sc3_status_pos(self):
        # status=deprecated 却不在 rejected/ → SC3 结构错配 → block
        bad = VALID_GLOBAL.replace("status: active", "status: deprecated")
        _write(os.path.join(self.mem, "global", "MEM-G-002.yaml"), bad)
        rep = mg.govern(self.root, write=False)
        self.assertEqual(rep["gate"]["decision"], "block")
        self.assertTrue(rep["fatal"])

    def test_caution_sc4_promotion(self):
        # genre 级但 validated_projects=1 (<2) → caution（软问题）
        weak = VALID_GENRE.replace("MEM-XH-014", "MEM-XH-015").replace(
            "validated_projects: 2", "validated_projects: 1")
        _write(os.path.join(self.mem, "genre", "xuanhuan", "MEM-XH-015.yaml"), weak)
        rep = mg.govern(self.root, write=False)
        self.assertEqual(rep["gate"]["decision"], "caution")
        self.assertFalse(rep["fatal"])
        self.assertTrue(any("validated_projects" in r for r in rep["gate"]["reasons"]))

    def test_caution_sc5_dedup(self):
        # 同 genre 内两份 problem 归一后几乎相同 → caution + duplicates
        dup = VALID_GENRE.replace("MEM-XH-014", "MEM-XH-016").replace(
            "连续升级导致爽感疲劳", "连续升级导致爽感疲劳。")
        _write(os.path.join(self.mem, "genre", "xuanhuan", "MEM-XH-016.yaml"), dup)
        rep = mg.govern(self.root, write=False)
        self.assertEqual(rep["gate"]["decision"], "caution")
        self.assertTrue(len(rep["duplicates"]) >= 1)
        self.assertTrue(rep["duplicates"][0]["similarity"] >= 0.85)

    def test_write_report(self):
        rep = mg.govern(self.root, write=True, proposed_by="test", model="t")
        self.assertIn("report_id", rep["meta"])
        out = os.path.join(self.root, "analysis", "memory")
        self.assertTrue(os.path.isdir(out))
        files = [f for f in os.listdir(out) if f.endswith(".yaml")]
        self.assertEqual(len(files), 1)

    def test_schema_contract_sections(self):
        rep = mg.govern(self.root, write=False)
        self.assertIn("signals", rep)
        names = [s["name"] for s in rep["signals"]]
        for sc in ("SC1_schema", "SC2_level_dir", "SC3_status_pos",
                   "SC4_promotion", "SC5_dedup", "SC6_reference", "SC7_readme"):
            self.assertIn(sc, names)

    def test_doctor_integration(self):
        # 构造临时 workspace + platform，跑 doctor：合规 memory → exit 0
        ws = tempfile.mkdtemp(prefix="mem_ws_")
        try:
            plat = os.path.join(ws, "platform")
            os.makedirs(os.path.join(plat, "registry"))
            with open(os.path.join(ws, "workspace.yaml"), "w", encoding="utf-8") as f:
                f.write("workspace:\n  name: t\n  platform: ./platform\n  projects: []\n")
            with open(os.path.join(plat, "registry", "versions.yaml"), "w", encoding="utf-8") as f:
                f.write("core:\n  platform: 1.0.0\n")
            # 复用已构造的合规 memory/
            shutil.copytree(self.mem, os.path.join(plat, "memory"))
            cli = os.path.join(TOOLS, "platform_cli.py")
            r = subprocess.run(
                ["C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe",
                 cli, "--workspace", ws, "doctor"],
                cwd=TOOLS, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, msg=r.stdout + r.stderr)

            # 引入结构错配 → doctor 应 exit 1
            _write(os.path.join(plat, "memory", "global", "MEM-XH-998.yaml"),
                   VALID_GENRE.replace("MEM-XH-014", "MEM-XH-998"))
            r2 = subprocess.run(
                ["C:/Users/Administrator/.workbuddy/binaries/python/versions/3.13.12/python.exe",
                 cli, "--workspace", ws, "doctor"],
                cwd=TOOLS, capture_output=True, text=True)
            self.assertEqual(r2.returncode, 1, msg=r2.stdout + r2.stderr)
        finally:
            shutil.rmtree(ws, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

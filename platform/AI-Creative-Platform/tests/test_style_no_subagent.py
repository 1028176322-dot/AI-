# -*- coding: utf-8 -*-
"""#19 回归：执行层禁子 Agent 静态扫描 + 受控写防御扫描。

其中 test_disabled_subagent_invocation_in_execution_layer 为「5 项禁用测试」第 5 项。
"""
import os
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM_ROOT = os.path.dirname(HERE)
for _child in os.listdir(os.path.join(PLATFORM_ROOT, "scripts")):
    _p = os.path.join(PLATFORM_ROOT, "scripts", _child)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import scan_no_subagent as sna  # noqa: E402
import scan_controlled_write as scw  # noqa: E402


class ScanTest(unittest.TestCase):
    def test_scan_clean_on_runtime(self):
        """真实运行时（scripts/logs、scripts/learning）不得出现子 Agent 派生。"""
        self.assertEqual(sna.scan_dirs(sna._default_scan_dirs(PLATFORM_ROOT),
                                        allow_files={os.path.normpath(sna.__file__)}), [])

    def test_controlled_write_scan_clean_on_runtime(self):
        """真实运行时除受信 Broker 外不得直写受控根。"""
        broker = os.path.normpath(os.path.join(PLATFORM_ROOT, "scripts", "logs", "broker.py"))
        v = scw.scan_dirs(scw._default_scan_dirs(PLATFORM_ROOT),
                          allow_files={broker, os.path.normpath(scw.__file__)})
        self.assertEqual(v, [])

    def test_disabled_subagent_invocation_in_execution_layer(self):
        """执行层若出现子 Agent 派生，扫描器必须告警（不可绕过防线）。"""
        d = tempfile.mkdtemp(prefix="scan_bad_")
        try:
            bad = os.path.join(d, "evil_writer.py")
            with open(bad, "w", encoding="utf-8") as f:
                f.write(textwrap.dedent(
                    "def run():\n"
                    "    a = Agent(tool='write')   # 执行层派生子 Agent\n"
                    "    a.spawn_subagent('do it')\n"))
            v = sna.scan_dirs([d])
            self.assertTrue(v, "scanner must flag subagent invocation")
            patterns = [x[2] for x in v]
            self.assertTrue(any("Agent(" in p for p in patterns))
            self.assertTrue(any("subagent" in p for p in patterns))
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_controlled_write_scan_flags_rogue_writer(self):
        """非 Broker 模块若直写受控根，防御扫描必须告警。"""
        d = tempfile.mkdtemp(prefix="scan_cw_")
        try:
            bad = os.path.join(d, "rogue.py")
            with open(bad, "w", encoding="utf-8") as f:
                f.write("open('chapters/drafts/CH1.md', 'w').write('hacked')\n")
            v = scw.scan_dirs([d])
            self.assertTrue(v, "scanner must flag rogue direct write")
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

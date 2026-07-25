"""txt<->md 同步校验（SyncGov CI 检查）单元测试。"""
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))
import sync_check as sc


class TestSyncCheck(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.vol = os.path.join(self.root, '第一卷_道生')
        self.txtvol = os.path.join(self.root, 'txt', '第一卷_道生')
        os.makedirs(self.vol)
        os.makedirs(self.txtvol)
        self.md = os.path.join(self.vol, '第001章_遗弃.md')
        self.txt = os.path.join(self.txtvol, '第001章_遗弃.txt')
        # 含 markdown 结构标记，验证 normalizer 能对齐 md 与 txt
        self.body = ('# 第一卷 道生\n\n## 第一章 遗弃\n\n'
                     '*永熙三年，冬。*\n\n风雪锁山。\n\n（本章完）\n')

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write_pair(self, txt):
        with open(self.md, 'w', encoding='utf-8') as f:
            f.write(self.body)
        with open(self.txt, 'w', encoding='utf-8') as f:
            f.write(txt)

    def test_in_sync_proceed(self):
        self._write_pair(self.body)
        rep = sc.check_txt_md_sync(self.root)
        self.assertEqual(rep['gate']['decision'], 'proceed')
        self.assertEqual(rep['composite']['health'], 100)
        self.assertEqual(rep['response']['divergent'], [])
        self.assertEqual(rep['response']['drift'], [])

    def test_divergent_caution(self):
        self._write_pair(self.body.replace('风雪锁山', '烈日当空，蝉鸣震耳'))
        rep = sc.check_txt_md_sync(self.root)
        self.assertEqual(rep['gate']['decision'], 'caution')
        self.assertTrue(rep['response']['divergent'])

    def test_drift_detected(self):
        # 单字漂移（前生 -> 前世 型）：应使用率仍高，但应被 drift 捕获
        self._write_pair(self.body.replace('风雪锁山。', '风雪锁山。。'))
        rep = sc.check_txt_md_sync(self.root)
        self.assertNotEqual(rep['gate']['decision'], 'proceed')
        self.assertTrue(rep['response']['drift'])

    def test_missing_txt_is_info_not_caution(self):
        with open(self.md, 'w', encoding='utf-8') as f:
            f.write(self.body)
        rep = sc.check_txt_md_sync(self.root)
        # 无 txt 导出：不触发 caution（仅 info 记录），doctor 仍 proceed
        self.assertEqual(rep['gate']['decision'], 'proceed')
        self.assertEqual(rep['response']['missing'], ['第001章_遗弃.md'])
        self.assertEqual(rep['response']['checked'], 0)

    def test_normalize_strips_markdown(self):
        md = '# 标题\n\n---\n\n*斜体文字*\n\n正文。\n\n（本章完）\n'
        self.assertEqual(sc._normalize(md), '标题斜体文字正文。')


if __name__ == '__main__':
    unittest.main()

# [Phase2-path] 把 scripts 各分组目录加入 sys.path，保持跨组裸名 import 可用
import os as _os, sys as _sys
_H0 = _os.path.dirname(_os.path.abspath(__file__))
_SCR0 = _os.path.dirname(_H0)
if _os.path.isdir(_SCR0):
    for _d in _os.listdir(_SCR0):
        _p = _os.path.join(_SCR0, _d)
        if _os.path.isdir(_p) and _p not in _sys.path:
            _sys.path.insert(0, _p)
"""txt<->md 源同步校验（CI 检查）。

平台审查体系依赖 `txt/` 导出物作为机检输入：reader_simulator / quality_scorer
的 `_find_chapter_file` 只搜 approved/chapters/drafts/txt 五个目录，实际读到的是
`txt/<卷>/第NNN章_*.txt` 导出物（非 `第一卷_道生/*.md` 源）。

风险：若作者只改了 md 源、忘了重导出 txt，机检会读取过期内容，导致审查失真。
本模块提供 check_txt_md_sync(project_root)，供 `platform_cli doctor` 的 SyncGov
块调用，把 md↔txt 一致性做成 CI 健康检查。

决策语义（与平台“报告式门禁”一致）：
  proceed  : 所有已导出的 txt 与源 md 一致
  caution  : 存在 txt 与 md 不一致（divergent / drift）—— CI 软警告，WARN，不阻断
  block    : 本检查不主动 block（不同步不破坏平台运行能力）
"""
import os
import re
import glob
import difflib


def _normalize(raw):
    """去掉 markdown 结构标记（标题/分隔线/斜体/本章完），折叠空白，返回连续串。"""
    out = []
    for ln in raw.splitlines():
        s = ln.strip()
        if not s:
            continue
        plain_heading = s.lstrip('#').strip()
        if re.match(r"^第[0-9一二三四五六七八九十百千]+章(?:\s|$)", plain_heading):
            # 标题中的分隔符（如 “童年·道心”）在纯文本导出中
            # 可能被简化；同步门禁只比较正文。
            continue
        if s.startswith('#'):          # 标题行：去 # 保留标题文字（与 txt 纯文本对齐）
            s = s.lstrip('#').strip()
            if not s:
                continue
            # 卷目录的 Markdown 源含卷标题，而章节 txt 导出只保留
            # 章节标题。卷标题是容器元数据，不属于正文差异。
            if re.match(r"^第.+卷(?:\s|$)", s):
                continue
            out.append(s)
            continue
        if re.fullmatch(r'-{3,}', s):  # 分隔线 ---
            continue
        if s in ('（本章完）', '(本章完)'):
            continue
        s = s.strip('*').strip()        # 去掉斜体标记（如 *永熙三年，冬。*）
        if not s:
            continue
        out.append(s)
    return ''.join(out)


def _find_source_chapters(project_root):
    """返回 [(md_path, txt_path), ...]。覆盖卷目录嵌套与根目录直放两种布局。

    txt 导出物路径 = txt/<相对卷目录>/<同名>.txt（扩展名由 .md 换为 .txt）。
    """
    pairs = []
    for pattern in (os.path.join(project_root, '*', '第*章*.md'),
                   os.path.join(project_root, '第*章*.md')):
        for md in glob.glob(pattern):
            rel = os.path.relpath(md, project_root)          # 第一卷_道生/第001章_遗弃.md
            d = os.path.dirname(rel)
            b = os.path.basename(rel)
            name = b[:-3] if b.endswith('.md') else b
            txt_rel = os.path.join('txt', d, name + '.txt')  # txt/第一卷_道生/第001章_遗弃.txt
            txt = os.path.join(project_root, txt_rel)
            pairs.append((md, txt))
    return pairs


def check_txt_md_sync(project_root, threshold=0.97):
    """检查 project_root 下所有源章节 md 与其 txt 导出物的同步状态。

    返回报告 dict：
      gate.decision     : proceed | caution
      gate.reasons      : [str]
      composite.health  : int 0-100
      response          : {sources, checked, missing[], divergent[], drift[]}
    """
    pairs = _find_source_chapters(project_root)
    total = len(pairs)
    missing = []
    divergent = []
    drift = []
    checked = 0

    for md, txt in pairs:
        name = os.path.basename(md)
        if not os.path.isfile(txt):
            missing.append(name)
            continue
        checked += 1
        try:
            with open(md, encoding='utf-8') as md_file:
                md_text = _normalize(md_file.read())
            with open(txt, encoding='utf-8') as txt_file:
                tx_text = _normalize(txt_file.read())
        except Exception as _e:
            drift.append('%s (读取失败: %s)' % (name, _e))
            continue
        if md_text == tx_text:
            continue
        ratio = difflib.SequenceMatcher(None, md_text, tx_text).ratio()
        if ratio < threshold:
            divergent.append('%s (相似度 %.3f)' % (name, ratio))
        else:
            # 高相似但非完全相等：细微用词漂移（如前生/前世单字替换）
            drift.append('%s (细微漂移 相似度 %.3f)' % (name, ratio))

    # 仅“已导出但不同步”才触发 caution；从未导出的章节只作 info，不惩罚
    issues = divergent + drift
    if issues:
        decision = 'caution'
        clean = checked - len(issues)
        health = round(100 * clean / checked) if checked else 100
        reasons = []
        if divergent:
            reasons.append('内容迥异(未重导出) %d 个: %s' % (
                len(divergent), '; '.join(d[:50] for d in divergent[:5])))
        if drift:
            reasons.append('细微漂移 %d 个: %s' % (
                len(drift), '; '.join(dd[:5] for dd in drift[:5])))
    else:
        decision = 'proceed'
        health = 100
        reasons = []

    return {
        'gate': {'decision': decision, 'reasons': reasons},
        'composite': {'health': health},
        'response': {
            'sources': total,
            'checked': checked,
            'missing': missing,
            'divergent': divergent,
            'drift': drift,
        },
    }


if __name__ == '__main__':
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else '.'
    rep = check_txt_md_sync(root)
    print('decision :', rep['gate']['decision'])
    print('health   :', rep['composite']['health'])
    print('sources  :', rep['response']['sources'], '| checked:', rep['response']['checked'])
    print('missing  :', len(rep['response']['missing']))
    print('divergent:', rep['response']['divergent'])
    print('drift    :', rep['response']['drift'])
    if rep['gate']['reasons']:
        print('reasons  :', ' | '.join(rep['gate']['reasons']))

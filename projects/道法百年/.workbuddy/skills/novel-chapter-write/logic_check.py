#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
logic_check.py — 《道士也玩火力覆盖》章节正文·机械逻辑校验
隶属 novel-chapter-write 四阶段流程（阶段三强制机械校验，GATE-3 门槛之一）。

设计目的：把"逻辑自查"从"AI 凭记忆回忆约束"升级为"对照权威索引机械比对"。
覆盖**结构性、可机检**的硬逻辑问题（C1–C6、C8、C11、C18、C19、C20 为 HARD 阻断；C7/C9/C10/C12/C13/C14/C15/C16/C17/C21/C22 为 WARN 级辅助提示，
不阻断流程，须由流程文档「逻辑一致性防御矩阵 L9」做语义确认。语义类（认知边界/物品
位置/因果链/手法适配）由 AI 矩阵覆盖，本脚本不重复。

捕获项（HARD=阻断FAIL / WARN=提示须 L 级显式确认）：
  C1 同音/异体陷阱(HARD)   —— 正文出现 萧凡/柯岚/柯砚/沈砚/苏霜/苏莫凝 等错名
  C2 禁复活/已死出场(HARD) —— 正文出现 禁复活名单/已死角色（萧沛/沈括等）
  C3 年号越界(HARD)        —— 永熙 + 数字 > 37（已定 永熙≤1404=37年）
  C4 占位残留(HARD)        —— 待统稿定/名号待统稿定/待定 等未回填占位
  C5 写作备注混入(HARD)    —— （节拍…）/（R数字：…）/（章末钩子…）等作者备注括号行
  C6 FB 编号(HARD)         —— 正文 FB-xxx 未登记 / 落在空号 FB-104~109 / 超范围 >185
  C7 空间/位置(WARN)       —— C7a 锚点缺失；C7b 互斥地点冲突
  C8 章节命名唯一性(HARD)  —— 本章《章名》与同卷其他章重名（防 P0-1 撞名/重复突破）
  C9 跨章/同章段落雷同(WARN) —— 跨章连续≥5行相同；同章重复块≥3行（防 P0-2 复制粘贴）
  C10 火器必藏设定(WARN)   —— 出现开火动作但无『藏/暗/武籍』缓冲（防 P0-3 断设定）
  C11 编辑残留/第四面墙(HARD)—— 第X章那回 / 幕X的 / 他将图收起 / （注： 等（防 P0-4 破墙）
  C12 纪年年龄自洽(WARN)   —— 仅核验「肖凡当前年龄」与 永熙年 偏差>1（行须含肖凡/他+当前词；排除追述/他人年龄，防误报）
  C13 前世口头禅频次(WARN) —— 『前世』>8次 或 『前世那人说过/常讲』框架词（防 P1-4）
  C14 角色命名冲突(WARN)   —— 同章易混对：硬编码 庆和×钱万山 + 动态扫 IDX_CHARACTER「易混」标记名（防 P1-3 混淆）
  C15 台词现代词(WARN)     —— 引号内台词出现现代实物名词/网络梗（R19 红线：主角现代词仅限内心独白，台词/旁白须古风，内心独白豁免）
  C16 字数达标(WARN)       —— 纯汉字数不在 2500–3000（Stage2 字数门规）
  C17 章名≥4字(WARN)       —— 本章《章名》不足4字（第7章起执行；1–6章祖父化豁免）
  C18 FB规划码泄漏(HARD)    —— 正文 prose 出现 FB-xxx（规划码泄漏出戏；C6 仅验登记有效性，不拦已登记码入正文）
  C19 七境分层回归(HARD)    —— 凡俗武道(铜骨/金身/化罡)误入七境谱；七境之巅误作通神(应为归元)（依 062/063/064 铁锚）
  C20 引荐信来源冲突(HARD)  —— 引荐信/信 被记为「故交所塞/所托」，与 FB-007(无为子授、致玄尘子)冲突
  C21 同章段落精确重复(WARN)—— 单段/多段去空白≥20字完全相同（C9 仅拦≥3行块，补漏 P1 复制粘贴）
  C22 章内句级重复(WARN) —— 同一句子(去标点空白≥10字)在≤15行内重复出现≥2次，捕获生成伪影(如相邻重复句，防 117 章类硬伤)；属生成 artifact 建议必修

用法：python logic_check.py <章节md路径> [治理目录]
返回：0=全通过，1=有 FAIL，2=参数错误
"""
import re, sys, os

def _repo_root():
    """脚本位于 <repo_root>/.workbuddy/skills/novel-chapter-write/logic_check.py，
    上溯 3 级定位仓库根；跨盘/跨目录均可移植。"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))


DEFAULT_GOV = None  # 运行时由 check() 按仓库根自动探测 docs/governance

# 已知地点名词（R11 空间锚点候选；用于 C7a 缺失检测）
KNOWN_LOCS = ["清虚观", "盛京", "京城", "中都", "北境", "赤乌", "玉虚", "玄妙观",
              "边关", "江南", "虞国", "听雨阁", "西市", "狄族", "长生观",
              "镇抚司", "内卫府", "朔州", "云中", "大晟", "州府", "通州"]

# 互斥地点对（用于 C7b：同章无过渡同现须 L9 确认）
MUTEX_PAIRS = [
    ("盛京", "北境"), ("盛京", "赤乌"), ("京城", "北境"), ("京城", "赤乌"),
    ("中都", "北境"), ("中都", "赤乌"), ("清虚观", "北境"), ("清虚观", "赤乌"),
    ("江南", "北境"), ("虞国", "北境"), ("玉虚", "北境"), ("玉虚", "赤乌"),
]

# 场景切换过渡词（C7b 判定"已交代位移"的白名单）
TRANSITION_WORDS = ["启程", "赶往", "前往", "传讯", "飞书", "次日", "旬后", "经年",
                    "闭关", "一路", "领兵", "出征", "北上", "西去", "南归", "东进",
                    "行了几日", "行了数日", "兼程", "星夜", "旬日", "月余", "次年",
                    "翌日", "半日后", "隔日", "不多时便到", "赶回", "转道"]

# 正名 -> 错误写法（同音/异体陷阱）
WRONG_VARIANTS = {
    "肖凡": ["萧凡"],
    "苏墨凝": ["苏莫凝"],
    "柯铮": ["柯岚"],
    "沈舟": ["柯砚", "沈砚"],
    "苏晚": ["苏霜"],
}
FORBIDDEN_TOKENS = set()
for _v in WRONG_VARIANTS.values():
    FORBIDDEN_TOKENS.update(_v)

# 正文严禁的占位残留
PLACEHOLDER = ["待统稿定", "名号待统稿定", "名号待统稿复核", "待定", "名号待"]

# 禁复活角色的分章阈值：角色仅在「章节号 > 阈值」时才视为已死、提及即违规。
# 萧沛为大晟三皇子，卷一至卷三为在世隐藏大反派，第212章（书院查封）方退场禁复活；
# 此前章节提及其名属正常在世描写，不应误判为复活。
# 漕帮赵管事：第028章首现（肖凡探底漕帮结构），第028/029/037章为在世正常出场，
# 第046章被借官面查办（落网）方退场；故章节号 ≤ 46 的出场/提及均属合法，不应误判为复活。
DEAD_THRESHOLD = {"萧沛": 212, "漕帮赵管事": 46}

# 作者写作备注括号行模式（只应存在于大纲/手法调度表，绝不进正文）
# 注意：合法的章末标记「（本章完）」不在匹配范围内
NOTE_PAT = re.compile(r'（(?:节拍\d*|R\d+|章末钩子|悬念钩子|手法|红线|FB-\d+)[^）]*）')

# 年号越界：永熙 + 数字（阿拉伯或中文）> 37
YEAR_PAT = re.compile(r'永熙\s*?([0-9零一二三四五六七八九十百]+)')

_CN = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6,
       '七': 7, '八': 8, '九': 9, '零': 0}


def cn2int(s):
    """简易中文数字转 int（覆盖 1–120，如 八十一/四十三/一百二十）。"""
    r, t = 0, 0
    for ch in s:
        if ch in _CN:
            t = _CN[ch]
        elif ch == '十':
            t = (t * 10) if t else 10
            r += t
            t = 0
        elif ch == '百':
            t = (t if t else 1) * 100
            r += t
            t = 0
    return r + t


def year_value(tok):
    return int(tok) if tok.isdigit() else cn2int(tok)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def parse_dead_chars(char_text):
    """提取禁复活/已死名单：硬编码已知 canon + 动态扫描 IDX_CHARACTER 表中带
    禁复活/已死标记的行（取每行首列角色名），两者取并集。"""
    # 硬编码已知 canon（稳定，若禁复活名单变更须同步此行）
    strong = ["萧沛"]  # 禁复活，仅余党裴琰承线出场
    mention = ["沈括", "黑虎帮二当家", "漕帮赵管事"]
    # 动态：扫描 IDX_CHARACTER 表格行，首列为角色名
    for line in char_text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 3:
            continue
        name = cells[1]
        if not name or name.startswith("角色") or name in ("—", "-"):
            continue
        if "禁复活" in line:
            if name not in strong:
                strong.append(name)
        elif "已死" in line or "已退场" in line:
            if name not in mention and name not in strong:
                mention.append(name)
    return strong, mention


def parse_conflict_names(char_text):
    """提取 C14 易混名对：扫描 IDX_CHARACTER 表格行中含「易混/混淆」标记的角色名
    （取首列角色名），返回所有两两组合；同章共现即预警。"""
    names = []
    for line in char_text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 3:
            continue
        name = cells[1]
        if not name or name.startswith("角色") or name in ("—", "-"):
            continue
        if "易混" in line or "混淆" in line:
            if name not in names:
                names.append(name)
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            pairs.append((names[i], names[j]))
    return pairs


def parse_registered_fb(fb_text):
    return {int(m) for m in re.findall(r'FB-(\d+)', fb_text)}


def discover_gov(chapter_path):
    """定位 docs/governance：优先从章节文件所在目录上溯（跨盘/跨副本均可），
    其次 CWD，最后回退到脚本所在仓库根。保证 E 盘/C 盘副本均能找到治理目录。"""
    candidates = []
    if chapter_path:
        candidates.append(os.path.dirname(os.path.abspath(chapter_path)))
    try:
        candidates.append(os.getcwd())
    except Exception:
        pass
    candidates.append(os.path.dirname(os.path.abspath(__file__)))
    for base in candidates:
        cur = os.path.abspath(base)
        for _ in range(8):
            if os.path.isfile(os.path.join(cur, "docs", "governance", "IDX_CHARACTER.md")):
                return os.path.join(cur, "docs", "governance")
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
    return os.path.join(_repo_root(), "docs", "governance")


def check(chapter_path, gov=None):
    if gov is None:
        gov = discover_gov(chapter_path)
    char_text = read_text(os.path.join(gov, "IDX_CHARACTER.md"))
    set_text = read_text(os.path.join(gov, "IDX_SETTING.md"))
    fb_text = read_text(os.path.join(gov, "IDX_FORESHADOW.md"))
    chapter = read_text(chapter_path)
    lines = chapter.splitlines()

    # 当前章节号（用于禁复活分章阈值判断）
    _m = re.search(r'第(\d+)章', os.path.basename(chapter_path))
    cur_ch = int(_m.group(1)) if _m else 0

    fails, passes = [], []

    # C1 同音/异体陷阱
    c1 = [(i, t) for i, ln in enumerate(lines, 1) for t in FORBIDDEN_TOKENS if t in ln]
    if c1:
        fails.append(("C1 同音/异体陷阱", c1))
    else:
        passes.append("C1 同音/异体陷阱：无 萧凡/柯岚/柯砚/沈砚/苏霜/苏莫凝")

    # C2 禁复活/已死出场
    strong, mention = parse_dead_chars(char_text)
    # 已死角色的"死亡/追述语境"关键词：含此类词或为「案/冤」等追述后缀时，
    # 属合法追述（非复活），放行；真正复活/出场（无死亡语境、作行为主体）才拦。
    DEATH_CTX = ["死", "亡", "故", "逝", "灭", "殉", "被害", "冤", "案",
                 "旧案", "知州", "满门", "一夜", "当年", "昔日", "旧"]
    c2 = []
    for i, ln in enumerate(lines, 1):
        if re.match(r'^\s*[《#]', ln):  # 跳过章节标题/小节标题行（死者名入标题属正常引用，非复活）
            continue
        for nm in strong + mention:
            if nm and nm in ln:
                # 分章阈值：角色在世章节内提及属正常，不误判为复活
                # （IDX_CHARACTER 角色名列可能带「三皇子」等前缀，故按子串匹配）
                if any(K in nm and cur_ch <= DEAD_THRESHOLD[K] for K in DEAD_THRESHOLD):
                    continue
                if nm in mention:
                    _safe = any(dc in ln for dc in DEATH_CTX) or \
                            re.search(rf'{re.escape(nm)}(?:案|灭门|的冤|旧案|冤|旧)', ln)
                    if _safe:
                        continue
                tag = "禁复活(强)" if nm in strong else "已死(提及需确认非复活)"
                c2.append((i, f"{nm}（{tag}）"))
    if c2:
        fails.append(("C2 禁复活/已死角色出现", c2))
    else:
        passes.append("C2 禁复活/已死角色：正文未出现")

    # C3 年号越界
    c3 = []
    for i, ln in enumerate(lines, 1):
        for m in YEAR_PAT.finditer(ln):
            tok = m.group(1)
            try:
                n = year_value(tok)
            except Exception:
                continue
            if n > 37:
                c3.append((i, f"永熙{tok}（={n}>37 越界）"))
    if c3:
        fails.append(("C3 年号越界(永熙>37)", c3))
    else:
        passes.append("C3 年号：无 永熙>37 越界")

    # C4 占位残留
    c4 = [(i, ph) for i, ln in enumerate(lines, 1) for ph in PLACEHOLDER if ph in ln]
    if c4:
        fails.append(("C4 占位残留", c4))
    else:
        passes.append("C4 占位残留：无 待统稿定/待定 等")

    # C5 写作备注混入
    c5 = []
    for i, ln in enumerate(lines, 1):
        mm = NOTE_PAT.search(ln)
        if mm:
            c5.append((i, mm.group(0)))
    if c5:
        fails.append(("C5 写作备注混入正文", c5))
    else:
        passes.append("C5 写作备注：正文纯净")

    # C6 FB 编号校验
    registered = parse_registered_fb(fb_text)
    c6 = []
    for i, ln in enumerate(lines, 1):
        for m in re.findall(r'FB-(\d+)', ln):
            num = int(m)
            if num not in registered:
                c6.append((i, f"FB-{num}（未登记）"))
            elif 104 <= num <= 109:
                c6.append((i, f"FB-{num}（空号未定义）"))
            elif num > 185:
                c6.append((i, f"FB-{num}（超范围>185）"))
    if c6:
        fails.append(("C6 FB编号 未登记/空号/超范围", c6))
    else:
        passes.append("C6 FB编号：均登记且在有效号段")

    # C7 空间/位置（WARN 级，不计入硬 FAIL，须 L9 语义确认）
    warns = []
    has_loc = any(any(loc in ln for loc in KNOWN_LOCS) for ln in lines)
    if not has_loc:
        warns.append(("C7a 空间锚点缺失", [(0, "全章未出现任何已知地点名词，疑似违反 R11 空间锚点")]))
    c7b = []
    for i, ln in enumerate(lines, 1):
        for a, b in MUTEX_PAIRS:
            if a in ln and b in ln:
                c7b.append((i, f"{a} 与 {b} 同段出现"))
    if c7b:
        has_trans = any(any(tw in ln for tw in TRANSITION_WORDS) for ln in lines)
        if not has_trans:
            warns.append(("C7b 互斥地点冲突(无过渡词)", c7b))

    # C8 章节命名唯一性（HARD）
    c8 = []
    _cn = scan_chapter_names(chapter_path)
    _cur_name_m = re.search(r'《([^》]+)》', lines[0]) if lines else None
    if _cur_name_m:
        _nm = _cur_name_m.group(1)
        if _nm in _cn:
            c8.append((0, f"章节名《{_nm}》与 {_cn[_nm]} 重名"))
    if c8:
        fails.append(("C8 章节命名唯一性", c8))
    else:
        passes.append("C8 章节命名唯一性：无重名")

    # C9 跨章/同章段落雷同（WARN）
    c9 = [(i, f"与其他章 {fn} 连续5行雷同") for i, fn in find_cross_dup(lines, chapter_path)]
    c9 += [(i, "同章内重复块（≥3行相同出现2+次，疑似复制粘贴）") for i, _ in find_intra_dup(lines)]
    if c9:
        warns.append(("C9 跨章/同章段落雷同(疑似复制粘贴)", c9))
    else:
        passes.append("C9 跨章/同章段落雷同：无")

    # C10 火器必藏设定（WARN）：开火动作前后 ±2 行须有『藏/暗/武籍』类缓冲词，
    # 否则疑似违背火器必藏(R17)；以局部窗口判定，避免全章任意『藏』字误判通过。
    c10 = []
    for i, ln in enumerate(lines):
        if any(fa in ln for fa in FIRE_ACT):
            _win = lines[max(0, i - 2):i + 3]
            _buf_near = any(any(fb in w for fb in FIRE_BUFFER) for w in _win)
            if not _buf_near:
                c10.append((i + 1, f"开火动作（{ln.strip()[:18]}…）前后±2行无『藏/暗/武籍』缓冲，疑似违背火器必藏(R17)"))
    if c10:
        warns.append(("C10 火器必藏设定一致", c10))
    else:
        passes.append("C10 火器必藏：开火动作均有缓冲/或本章无开火")

    # C11 编辑残留/第四面墙（HARD）
    c11 = []
    for i, ln in enumerate(lines, 1):
        for _pat in EDIT_RESIDUE:
            if _pat.search(ln):
                c11.append((i, _pat.pattern))
                break
    if c11:
        fails.append(("C11 编辑残留/第四面墙", c11))
    else:
        passes.append("C11 编辑残留/第四面墙：无")

    # C12 纪年年龄自洽（WARN）：仅核验「肖凡当前年龄」与章内当前年号是否一致（年龄=永熙年−3）。
    # 多层排除（防真实文本误报）：① 出生年引用（永熙Y年 同行含 生/出生/降生/诞 → 非当前年）
    # ② 追述表述（自X岁起/X岁时/忆起…/当年/幼时…）③ 其他角色/寿命框架（>100岁，肖凡卷一≤20）
    # ④ 行内须含「肖凡」或「他+当前词(今年/如今/现年/这年/当下/年满/现在)」。
    c12 = []
    _birth_marks = ["生", "出生", "降生", "诞", "呱"]
    _years = []
    for m in AGE_YEAR_PAT.finditer(chapter):
        _ctx = chapter[max(0, m.start() - 15):m.end() + 15]
        if any(bm in _ctx for bm in _birth_marks):
            continue  # 出生年引用，非当前年
        if any(rg in _ctx for rg in ("至", "到", "—", "–", "~")):
            continue  # 年号处于「X至Y」跨度内，非当前年
        _years.append(year_value(m.group(1)))
    if _years:
        _exp = _years[0] - 3  # 以章内首个「非出生年」年号为准
        _cur_markers = ["今年", "如今", "现年", "这年", "当下", "年满", "现在"]
        _retro_words = ["当年", "昔日", "昔年", "幼时", "少时", "小时候", "从前", "儿时", "那年", "昔", "忆起", "想起", "记得"]
        _retro_re = re.compile(r'自[^，。、]{0,6}岁|岁[^，。]{0,8}时')
        for i, ln in enumerate(lines, 1):
            has_xf = "肖凡" in ln
            has_he_cur = ("他" in ln) and any(cm in ln for cm in _cur_markers)
            if not (has_xf or has_he_cur):
                continue
            if any(rw in ln for rw in _retro_words) or _retro_re.search(ln):
                continue  # 追述/他人，跳过
            for _am in AGE_PAT.finditer(ln):
                try:
                    _X = year_value(_am.group(1))
                except Exception:
                    continue
                if _X > 100:  # 肖凡卷一≤20，>100为寿命框架/他人年龄
                    continue
                if abs(_X - _exp) > 1:
                    c12.append((i, f"永熙{_years[0]}年肖凡应约{_exp}岁，正文写{_X}岁（偏差>1）"))
    if c12:
        warns.append(("C12 纪年年龄自洽", c12))
    else:
        passes.append("C12 纪年年龄自洽：无偏差")

    # C13 前世口头禅频次（WARN）
    c13 = []
    _prev = sum(ln.count("前世") for ln in lines)
    if _prev > 8:
        c13.append((0, f"『前世』出现{_prev}次，超8次预警，建议部分改为动作/感知呈现(show)"))
    for i, ln in enumerate(lines, 1):
        if re.search(r'前世那人(?:说过|常讲|总说|讲过)', ln):
            c13.append((i, "『前世那人说过/常讲』框架词，建议改为当下心境/动作呈现"))
    if c13:
        warns.append(("C13 前世口头禅频次", c13))
    else:
        passes.append("C13 前世口头禅：未超阈值")

    # C14 角色命名冲突（WARN）：硬编码基线对 + 动态扫 IDX_CHARACTER「易混」标记名
    c14 = []
    if any("庆和" in ln for ln in lines) and any("钱万山" in ln for ln in lines):
        c14.append((0, "同章出现『庆和(酒行)』与『钱万山』，二者非同一人，须明确区分避免混淆"))
    _conflict_names = parse_conflict_names(char_text)
    for a, b in _conflict_names:
        if any(a in ln for ln in lines) and any(b in ln for ln in lines):
            c14.append((0, f"同章出现易混对『{a}』与『{b}』（IDX_CHARACTER 标记易混），须明确区分"))
    if c14:
        warns.append(("C14 角色命名冲突", c14))
    else:
        passes.append("C14 角色命名冲突：无同章易混对")

    # C15 台词现代词（WARN）：仅检测引号内台词，内心独白（无引号第三人称自由间接）豁免。
    # 依据用户纠正：主角是现代灵魂，内心独白可/需说现代词（R19 仅约束台词/旁白零现代词）。
    c15 = []
    for i, ln in enumerate(lines, 1):
        for q in QUOTE_PAT.findall(ln):
            ql = q.lower()
            for t in MODERN_TERMS:
                if t in ALLOWED_BUSINESS_TERMS:
                    continue
                if t.lower() in ql:
                    c15.append((i, f"引号内台词出现现代词「{t}」（R19：现代词仅限主角内心独白，台词须古风）"))
                    break
    if c15:
        warns.append(("C15 台词现代词(R19)", c15))
    else:
        passes.append("C15 台词现代词：引号内台词无现代实物名词/网络梗（经营理念现代词按 R19 例外放行，见 ALLOWED_BUSINESS_TERMS）")

    # C16 字数达标（WARN）：纯汉字 2500–3000（Stage2 字数门规）
    han = count_han(chapter)
    if han < 2500 or han > 3000:
        warns.append(("C16 字数达标", [(0, f"纯汉字 {han} 字，不在 2500–3000 区间")]))
    else:
        passes.append(f"C16 字数达标：纯汉字 {han} 字（2500–3000）")

    # C17 章名≥4字（WARN）：第7章起执行，1–6章祖父化豁免
    c17 = []
    if _cur_name_m:
        _nm = _cur_name_m.group(1)
        if cur_ch > 6 and len(_nm) < 4:
            c17.append((0, f"章名《{_nm}》仅 {len(_nm)} 字，不足4字（第7章起须≥4字）"))
    if c17:
        warns.append(("C17 章名≥4字", c17))
    else:
        passes.append("C17 章名≥4字：合规")

    # C18 FB 规划码泄漏（HARD）：正文 prose 出现 FB-xxx 即出戏（C6 只验登记有效性）
    c18 = []
    for i, ln in enumerate(lines, 1):
        m = FB_LEAK.search(ln)
        if m:
            c18.append((i, m.group(0)))
    if c18:
        fails.append(("C18 FB规划码泄漏(正文)", c18))
    else:
        passes.append("C18 FB规划码：正文无 FB-xxx 泄漏")

    # C19 七境分层回归（HARD）：凡俗武道误入七境谱 / 七境之巅误作通神(应为归元)
    c19 = []
    for i, ln in enumerate(lines, 1):
        for _pat in C19_QJ:
            if _pat.search(ln):
                c19.append((i, _pat.pattern))
                break
    if c19:
        fails.append(("C19 七境分层回归", c19))
    else:
        passes.append("C19 七境分层：凡俗武道(铜骨/金身/化罡)未误入七境谱，之巅为归元")

    # C20 引荐信来源冲突（HARD）：信被记为故交所塞/所托，与 FB-007(无为子授/致玄尘子)冲突
    c20 = []
    for i, ln in enumerate(lines, 1):
        for _pat in C20_INTRO:
            if _pat.search(ln):
                c20.append((i, _pat.pattern))
                break
    if c20:
        fails.append(("C20 引荐信来源冲突(FB-007)", c20))
    else:
        passes.append("C20 引荐信来源：与 FB-007(无为子授/致玄尘子)一致")

    # C21 同章段落精确重复（WARN）：单段/多段去空白≥20字完全相同（补漏 C9 仅拦≥3行块）
    c21 = [(i, f"与第{first}段完全相同的段落（疑似复制粘贴，P1）") for i, first in find_exact_dup_paras(lines)]
    if c21:
        warns.append(("C21 同章段落精确重复", c21))
    else:
        passes.append("C21 同章段落精确重复：无")

    # C22 章内句级重复(WARN)：同一句子(去标点空白≥10字)在≤15行内重复≥2次，捕获生成伪影
    c22 = [(i, msg) for i, msg in find_sentence_dup(lines)]
    if c22:
        warns.append(("C22 章内句级重复(生成伪影)", c22))
    else:
        passes.append("C22 章内句级重复：无")

    # 报告
    print("=" * 64)
    print(f"逻辑机械校验：{os.path.basename(chapter_path)}")
    print("=" * 64)
    for p in passes:
        print(f"  [PASS] {p}")
    for name, items in fails:
        print(f"  [FAIL] {name}：")
        for it in items[:25]:
            if len(it) == 2:
                print(f"      L{it[0]}: {it[1]}")
            else:
                print(f"      L{it[0]}: {it[1]}")
    for name, items in warns:
        print(f"  [WARN] {name}：")
        for it in items[:25]:
            print(f"      L{it[0]}: {it[1]}")
    print("=" * 64)
    total = sum(len(v) for _, v in fails)
    if fails:
        print(f"结论：[FAIL] 发现 {total} 处结构问题，须回阶段二修订后重检")
        return 1
    if warns:
        wtotal = sum(len(v) for _, v in warns)
        print(f"结论：[OK] 硬校验通过；[WARN] {wtotal} 处空间 WARN（C7，须 L9 语义确认，不阻断）")
    else:
        print("结论：[OK] 机械校验全通过（结构性逻辑无问题；语义类见 AI 矩阵）")
    return 0


# ---------- 防复发扩展 C8–C14（依据读者审读报告 P0/P1 修复追加 2026-07-21）----------

# C8 章节命名唯一性：扫描同卷目录其他章首行《章名》
def scan_chapter_names(cur_path):
    vol_dir = os.path.dirname(os.path.abspath(cur_path))
    names = {}
    for fn in os.listdir(vol_dir):
        if not (fn.endswith(".md") and re.match(r'第\d+章', fn)):
            continue
        fp = os.path.abspath(os.path.join(vol_dir, fn))
        if fp == os.path.abspath(cur_path):
            continue
        try:
            with open(fp, encoding="utf-8") as f:
                first = f.readline().strip()
        except Exception:
            continue
        m = re.search(r'《([^》]+)》', first)
        if m:
            names.setdefault(m.group(1), []).append(fn)
    return names


# C9 跨章段落雷同：本章连续 DUP_WINDOW 行完全相同出现在其他章
def find_cross_dup(lines, cur_path, window=5):
    vol_dir = os.path.dirname(os.path.abspath(cur_path))
    min_chars = 30  # 短行组成的 signature 不比对，防误报
    other_sigs = {}
    for fn in os.listdir(vol_dir):
        if not (fn.endswith(".md") and re.match(r'第\d+章', fn)):
            continue
        fp = os.path.abspath(os.path.join(vol_dir, fn))
        if fp == os.path.abspath(cur_path):
            continue
        try:
            olines = open(fp, encoding="utf-8").read().splitlines()
        except Exception:
            continue
        for i in range(len(olines) - window + 1):
            sig = "\n".join(olines[i:i + window])
            if len(re.sub(r'\s', '', sig)) >= min_chars:
                other_sigs.setdefault(sig, fn)
    dups = []
    for i in range(len(lines) - window + 1):
        sig = "\n".join(lines[i:i + window])
        if len(re.sub(r'\s', '', sig)) >= min_chars and sig in other_sigs:
            dups.append((i + 1, other_sigs[sig]))
    return dups[:10]


# C9 同章内重复块检测：同一连续块（≥3行，去空白≥30字）在章内出现 2+ 次
def find_intra_dup(lines, window=3):
    min_chars = 30
    seen = {}  # sig -> 首次出现行(0-based)；-1 表示已上报过重复
    dups = []
    for i in range(len(lines) - window + 1):
        sig = "\n".join(lines[i:i + window])
        if len(re.sub(r'\s', '', sig)) < min_chars:
            continue
        if sig in seen:
            if seen[sig] >= 0:
                dups.append((i + 1, seen[sig] + 1))
                seen[sig] = -1
        else:
            seen[sig] = i
    return dups[:10]


# C21 同章段落精确重复：按空行分段，去空白后完全相同（≥20字）即视为重复段（补漏 C9 仅拦≥3行块）
def find_exact_dup_paras(lines, min_chars=20):
    paras = []
    cur = []
    for ln in lines:
        if ln.strip() == "":
            if cur:
                paras.append("\n".join(cur))
                cur = []
        else:
            cur.append(ln)
    if cur:
        paras.append("\n".join(cur))
    seen = {}
    dups = []
    for idx, p in enumerate(paras):
        s = re.sub(r'\s', '', p)
        if len(s) < min_chars:
            continue
        if s in seen:
            if seen[s] >= 0:
                dups.append((idx + 1, seen[s] + 1))
                seen[s] = -1
        else:
            seen[s] = idx
    return dups[:10]


# C22 章内句级重复：同一句子(去标点空白≥min_chars)在≤window行内重复≥2次。
# 捕获生成伪影(如 117 章相邻重复句「苏墨凝这日来报，神色比往常沉。」出现两遍)。
# 仅 WARN(非 HARD)：极个别合法重复(角色强调重复台词)不误阻断；由审查对话判定是否必修。
def find_sentence_dup(lines, window=15, min_chars=10):
    PUNCT = r'[\s，。！？；：、""\'\'（）()—–…·]'
    sent_map = []  # (行号, 归一化句)
    for i, ln in enumerate(lines, 1):
        for p in re.split(r'[。！？；\n]', ln):
            s = re.sub(PUNCT, '', p)
            if len(s) >= min_chars:
                sent_map.append((i, s))
    last = {}
    dups = []
    for li, s in sent_map:
        if s in last and (li - last[s]) <= window:
            dups.append((li, f"与L{last[s]}重复句：「{s[:18]}…」(C22 章内句级重复·生成伪影)"))
        last[s] = li
    return dups[:10]


# C10 火器必藏设定一致
FIRE_ACT = ["开枪", "扣扳机", "击发", "枪响", "扣动扳机", "放枪", "开火",
            "射击", "走火", "扣了扳机", "扣下扳机"]
FIRE_BUFFER = ["藏", "暗藏", "不露", "不显", "暗", "隐", "武籍", "私藏",
               "悄悄", "未露", "藏着", "藏拙", "不教人知"]

# C11 编辑残留 / 第四面墙
EDIT_RESIDUE = [
    re.compile(r'第\d+章那回'),
    re.compile(r'第\d+章那回的'),
    re.compile(r'幕[一二三四五六七八九十]的'),
    re.compile(r'他将图收起'),
    re.compile(r'（注[:：]'),
    re.compile(r'(?<!案)卷[一二三四五六七八九十]'),     # 卷X结构词（第四面墙破墙）；(?<!案)避"案卷一"误判
    re.compile(r'本卷'),                         # 作者结构语（第四面墙破墙）
    re.compile(r'这卷的'),                       # 作者结构语（第四面墙破墙）；"这卷"+的 才判，避"这卷宗/这卷呈"等卷宗误报
    re.compile(r'幕[一二三四五六七八九十]'),     # 幕三/幕五等（补"幕X走"类无"的"后缀）
    re.compile(r'章末'),                         # 第四面墙破墙：章末的钩子/章末的念想落定 等作者结构语
]

# C18 FB 规划码泄漏（正文中出现 FB-xxx 即出戏；与 C6 不同，C6 仅验登记有效性，不拦已登记码入正文）
FB_LEAK = re.compile(r'FB-[0-9]+')

# C19 七境分层回归（依据 062/063/064 已立铁锚：七境=凝灵→化精→易筋→淬体→洗髓→通神→归元；
# 凡俗武道横练=铁皮→铜骨→金身、内家=气感→周天→化罡，不在七境图谱内）
C19_QJ = [
    re.compile(r'七境之巅.{0,6}通神'),                 # 之巅须为归元，非通神
    re.compile(r'七境的(?:第三|第四|第五|第六|第七)[阶]*[、，][^。]{0,25}(铜骨|金身|化罡)'),  # 七境枚举中把凡俗武道阶列为七境步（铜骨非七境阶，不可作七境第X阶；合法"第六阶通神/第七阶归元"不误判）
    re.compile(r'铜骨.{0,3}(收尾|是七境|乃七境|为七境|属七境)'),  # 明示铜骨入七境谱
]

# C20 引荐信来源冲突（FB-007 铁锚：信=师父无为子所授、专程致国师玄尘子）
C20_INTRO = [
    re.compile(r'(?:引荐信|这封信|那封信|这信|那信).{0,12}故交'),
    re.compile(r'故交.{0,12}(?:塞给|塞来|交到|交来|所托|引荐信|这封信|那封信|这信|那信)'),
]

# C12 纪年年龄自洽（1370=永熙三年=0岁 → 年龄=永熙年-3）
# 年号/年龄均支持阿拉伯数字与中文数字（正文用「永熙十八年」「十五岁」等中文数字）
AGE_YEAR_PAT = re.compile(r'永熙\s*?([0-9零一二三四五六七八九十百]+)\s*年')
AGE_PAT = re.compile(r'([0-9零一二三四五六七八九十百]+)\s*岁')


# ---------- 扩展 C15–C17（依据用户纠正"主角现代灵魂内心独白可/需说现代词"追加 2026-07-22）----------

# C15 台词现代词：仅检引号内台词，内心独白（无引号第三人称自由间接）豁免
QUOTE_PAT = re.compile(r'[\u201c\u201d\u2018\u2019]([^\u201c\u201d\u2018\u2019\n]+)[\u201c\u201d\u2018\u2019]')
MODERN_TERMS = {
    # 现代科技实物
    "手机", "电脑", "计算机", "平板", "电视", "冰箱", "洗衣机", "空调", "汽车", "卡车",
    "飞机", "火车", "地铁", "高铁", "摩托车", "自行车", "互联网", "网络", "网站", "微信",
    "支付宝", "淘宝", "视频", "直播", "主播", "WIFI", "wifi", "蓝牙", "键盘", "屏幕",
    "显示器", "电池", "电灯", "电话", "收音机", "录音机", "相机", "照片", "电影", "游戏",
    "软件", "硬件", "代码", "数据", "芯片", "发动机", "马达", "轮胎", "加油站",
    "红绿灯", "斑马线", "轮船",
    # 网络梗 / 现代口语
    "躺平", "内卷", "打工人", "社畜", "绝绝子", "yyds", "YYDS", "破防", "emo", "EMO",
    "凡尔赛", "韭菜", "996", "007", "摸鱼", "种草", "拔草", "带货", "网红",
    "UP主", "up主", "弹幕", "梗", "佛系", "鸡娃", "双减", "内耗",
    "社死", "显眼包", "搭子", "听劝", "治愈", "平替", "智商税", "剁手", "秒杀", "上分",
    "下头", "上头", "整顿职场",
    # 现代制度 / 商业
    "公司", "股份", "股票", "股市", "银行", "超市", "便利店", "快递", "外卖", "身份证",
    "驾照", "驾驶证", "警察", "武警", "公务员",
}

# C15 放行白名单（R19 经营理念现代词例外，仅限肖凡语境；与 IDX_PERSONA.md 锁词表同步）
# 用户裁定 2026-07-23：现代商业/管理概念词放行（品牌/口碑/供应链/护城河/引流/转化/留存/
# 复购/差异化/定位/溢价/规模效应/边际成本/降维/赛道/痛点/刚需/招商/联营/加盟/用户/客户/私域/
# 品控/客流/广告/促销/流量…）。这些词不触发 C15 警告；现代实物名词/网络梗/现代制度实体仍禁。
# 注意：白名单为机械放行（C15 无法区分说话人），native 角色自主台词出现仍由人工审查剔除。
ALLOWED_BUSINESS_TERMS = {
    "品牌", "口碑", "供应链", "物流", "仓储", "客流", "人气", "引流", "转化", "留存",
    "复购", "私域", "公域", "品控", "溢价", "定价", "定位", "差异化", "护城河", "规模效应",
    "边际成本", "商业模式", "降维", "降维打击", "赛道", "痛点", "刚需", "下沉", "招商",
    "联营", "加盟", "用户", "客户", "心智", "份额", "壁垒", "杠杆", "复利", "现金流",
    "账期", "毛利", "净利", "产能", "成本", "利润", "市占", "竞品", "品类", "调性",
    "闭环", "抓手", "赋能", "复盘", "对齐", "颗粒度", "组合拳", "基本盘", "长尾", "好评",
    "差评", "爆款", "客单价", "复购率", "转化率", "坪效", "人效", "SKU", "ROI", "KPI",
    "广告", "促销", "流量",
}


def count_han(text):
    """统计不含标点的纯汉字数（用于 C16 字数门规 2500–3000）。"""
    return len(re.findall(r'[\u4e00-\u9fff]', text))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python logic_check.py <章节md路径> [治理目录]")
        sys.exit(2)
    cp = sys.argv[1]
    gv = sys.argv[2] if len(sys.argv) > 2 else None
    sys.exit(check(cp, gv))

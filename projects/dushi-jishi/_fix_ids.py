# -*- coding: utf-8 -*-
"""将 design 域(非 _ 目录)下 39 个设计文档 ID 统一转为 NKB 要求的大写格式，
   并修正 reader-state-001.fact_id 悬空引用。仅做确定性 token 替换，保留其余内容。"""
import os, re

ROOT = r"D:\AI-Workspace\projects\dushi-jishi\sources\design"

# 旧(小写) -> 新(大写) 映射
MAPPING = {
    "char-protagonist-001": "CHAR-PROTAGONIST-001",
    "char-lujingshan-001": "CHAR-LUJINGSHAN-001",
    "char-luzheng-001": "CHAR-LUZHENG-001",
    "char-beijing-scion-001": "CHAR-BEIJING-SCION-001",
    "world-lingang-001": "WORLD-LINGANG-001",
    "canon-no-abuse-protagonist-001": "CANON-NO-ABUSE-PROTAGONIST-001",
    "canon-no-campus-001": "CANON-NO-CAMPUS-001",
    "canon-no-melodrama-romance-001": "CANON-NO-MELODRAMA-ROMANCE-001",
    "canon-no-supernatural-001": "CANON-NO-SUPERNATURAL-001",
    "canon-realism-001": "CANON-REALISM-001",
    "ability-armed-ops-001": "ABILITY-ARMED-OPS-001",
    "ability-commercial-build-001": "ABILITY-COMMERCIAL-BUILD-001",
    "ability-prison-skills-001": "ABILITY-PRISON-SKILLS-001",
    "item-evidence-001": "ITEM-EVIDENCE-001",
    "loc-border-001": "LOC-BORDER-001",
    "loc-prison-001": "LOC-PRISON-001",
    "faction-beijing-top-001": "FACTION-BEIJING-TOP-001",
    "faction-dingfeng-001": "FACTION-DINGFENG-001",
    "org-prison-001": "ORG-PRISON-001",
    "org-protagonist-commercial-001": "ORG-PROTAGONIST-COMMERCIAL-001",
    "org-protagonist-force-001": "ORG-PROTAGONIST-FORCE-001",
    "org-protagonist-intel-001": "ORG-PROTAGONIST-INTEL-001",
    "world-state-opening-001": "WORLD-STATE-OPENING-001",
    "foreshadow-behind-lu-001": "FORESHADOW-BEHIND-LU-001",
    "foreshadow-family-001": "FORESHADOW-FAMILY-001",
    "foreshadow-insider-001": "FORESHADOW-INSIDER-001",
    "foreshadow-lookalike-001": "FORESHADOW-LOOKALIKE-001",
    "term-dingzui-001": "TERM-DINGZUI-001",
    "term-jingwai-001": "TERM-JINGWAI-001",
    "term-shenfen-001": "TERM-SHENFEN-001",
    "term-sihuan-001": "TERM-SIHUAN-001",
    "term-toudu-001": "TERM-TOUDU-001",
    "arc-protagonist-001": "ARC-PROTAGONIST-001",
    "conflict-inner-001": "CONFLICT-INNER-001",
    "conflict-prison-survival-001": "CONFLICT-PRISON-SURVIVAL-001",
    "conflict-protagonist-group-001": "CONFLICT-PROTAGONIST-GROUP-001",
    "conflict-ultimate-001": "CONFLICT-ULTIMATE-001",
    "reader-state-001": "READER-STATE-001",
    "story-core-001": "STORY-CORE-001",
}

# 构建按长度降序的正则，避免短 id 误替长 id 子串
old_ids = sorted(MAPPING.keys(), key=len, reverse=True)
pat = re.compile(
    r"(?<![-\w])(%s)(?![-\w])" % "|".join(re.escape(k) for k in old_ids))

changed_files = 0
for dp, dirs, fs in os.walk(ROOT):
    dirs[:] = [d for d in dirs if not d.startswith("_")]
    for f in fs:
        if not f.endswith((".yaml", ".yml")):
            continue
        path = os.path.join(dp, f)
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        new = pat.sub(lambda m: MAPPING[m.group(1)], text)
        if new != text:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new)
            changed_files += 1
            print("uppercased ids: %s" % os.path.relpath(path, ROOT))

# 修正 reader-state-001.fact_id 悬空引用
rs_path = os.path.join(ROOT, "reader_state", "reader-state-001.yaml")
if os.path.isfile(rs_path):
    with open(rs_path, "r", encoding="utf-8") as fh:
        t = fh.read()
    t2 = t.replace("fact_id: fact-opening", "fact_id: world-state-opening-001")
    if t2 != t:
        with open(rs_path, "w", encoding="utf-8") as fh:
            fh.write(t2)
        print("fixed reader-state fact_id -> world-state-opening-001")

print("total changed files: %d" % changed_files)

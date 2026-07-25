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
"""冲击分析仪端到端验证（Phase 2 #1）。覆盖 proceed/caution/block 三态 + 索引 + 任务预检拦截 + CLI 委托。"""
import os, sys, shutil, datetime, subprocess

HERE = _os.path.dirname(_os.path.abspath(__file__))
sys.path.insert(0, HERE)
import impact_analyzer as IA
import task_engine as TE

TS = datetime.datetime.now().strftime("%H%M%S")
ROOT = r"E:/AI-Workspace/projects/_lc_tmp/impact_test_%s" % TS
if os.path.exists(ROOT):
    shutil.rmtree(ROOT)
for d in ("NKB", "approved", "chapters/drafts", "tasks"):
    os.makedirs(os.path.join(ROOT, d))

open(os.path.join(ROOT, "project.yaml"), "w", encoding="utf-8").write(
    "project:\n  id: impact-test\n  name: 冲击测试\nrequires:\n  platform: \">=2.1.0\"\n  contracts: \">=1.0.0\"\n")

open(os.path.join(ROOT, "NKB", "Characters.yaml"), "w", encoding="utf-8").write(
    "schema_version: 1.2.0\nproject_id: impact-test\nrecords:\n"
    "  - id: c1\n    name: 萧咤\n    relations: [\"Events/政变\"]\n"
    "  - id: c2\n    name: 沈括\n    relations: []\n")
open(os.path.join(ROOT, "NKB", "Events.yaml"), "w", encoding="utf-8").write(
    "schema_version: 1.2.0\nproject_id: impact-test\nrecords:\n"
    "  - id: 政变\n    name: 永熙政变\n    participants: [\"Characters/c1\"]\n")
open(os.path.join(ROOT, "NKB", "Foreshadow.yaml"), "w", encoding="utf-8").write(
    "schema_version: 1.2.0\nproject_id: impact-test\nrecords:\n"
    "  - id: FB-033\n    name: 阵营伏笔\n    targets: [\"Characters/c1\"]\n")

open(os.path.join(ROOT, "approved", "第042章_xxx.txt"), "w", encoding="utf-8").write("萧咤站在盛京城头。")
open(os.path.join(ROOT, "chapters/drafts", "第043章_yyy.txt"), "w", encoding="utf-8").write("沈括回到书房。")

fails = []
def check(name, cond):
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)

# 1) 索引构建
idx = IA.render_index(ROOT)
idxmap = {i["chapter"]: i for i in idx.get("index", [])}
check("索引 042->萧咤", "Characters/c1" in (idxmap.get("042", {}).get("entities") or []))
check("索引 043->沈括", "Characters/c2" in (idxmap.get("043", {}).get("entities") or []))

# 2) 改萧咤 -> block（影响已发布 042）
rep = IA.analyze(ROOT, "nkb", "Characters/c1")
check("改萧咤 gate=block", rep["gate"]["decision"] == "block")
check("改萧咤 影响 approved 042", any(a["id"] == "chapter/42" for a in rep["affected"]))
check("改萧咤 报告已落盘", os.path.isfile(os.path.join(ROOT, "analysis/impact",
      (rep["meta"].get("report_id") or "x") + ".yaml")))

# 3) 改沈括 -> caution（仅命中 drafts 043，非高优）
rep = IA.analyze(ROOT, "nkb", "Characters/c2")
check("改沈括 gate!=block", rep["gate"]["decision"] != "block")
check("改沈括 影响 043", any(a["id"] == "chapter/43" for a in rep["affected"]))

# 4) 改章节 043（新章未发布）-> 非 block
rep = IA.analyze(ROOT, "chapter", "043")
check("改043 非 block", rep["gate"]["decision"] != "block")

# 5) 任务 claim 已发布 042 -> 被预检拦截
TE._ensure(ROOT)
def mk_task(tid, ch):
    TE.create_task(ROOT, {"task": {"id": tid, "version": 1, "project": "impact-test",
        "type": "chapter_write", "title": "写%s" % ch, "status": "ready", "priority": "high",
        "chapter_ref": ch, "created_by": "planner", "agent": {"required_role": "writer"},
        "inputs": {"required": []}, "acceptance": {"criteria": []},
        "permissions": {"read": ["chapters/*"], "write": ["chapters/drafts/*"], "forbidden": ["core/*"]}}})
mk_task("CH042-WRITE", "042")
blocked = False
try:
    TE.claim(ROOT, "CH042-WRITE", "w1", "writer")
except ValueError as e:
    blocked = "gate=block" in str(e)
check("claim 042 被预检拦截", blocked)

# 6) 任务 claim drafts 043 -> 放行（proceed）
mk_task("CH043-WRITE", "043")
ok = False
try:
    st = TE.claim(ROOT, "CH043-WRITE", "w2", "writer")
    ok = (st == "claimed")
except ValueError:
    ok = False
check("claim 043 放行成功", ok)

# 7) CLI 委托（platform impact ...）
pc = _os.path.join(_PLAT2, "cli", "platform.py")
out = subprocess.run([sys.executable, pc, "impact", "--project-root", ROOT, "analyze",
                      "--target-type", "nkb", "--target-id", "Characters/c1"],
                     capture_output=True, text=True)
check("CLI impact analyze 返回 门禁：block", "门禁：block" in out.stdout)
if out.returncode != 0:
    print("  CLI stderr:", out.stderr[:300])

print("\n结果：", "全部 PASS" if not fails else ("FAIL -> " + ", ".join(fails)))
shutil.rmtree(ROOT, ignore_errors=True)
sys.exit(1 if fails else 0)

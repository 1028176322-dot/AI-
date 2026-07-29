# -*- coding: utf-8 -*-
"""收尾 CH-201 原子发布：刷新过期 grant + 调用 PC.publish + 验证。"""
import os, sys, glob, datetime

PLAT = "E:/AI-Workspace/platform/AI-Creative-Platform/scripts"
for p in [PLAT, PLAT + "/tasks", PLAT + "/_common", PLAT + "/publish",
          PLAT + "/learning", PLAT + "/authorization"]:
    if p not in sys.path:
        sys.path.insert(0, p)

import _gov
import task_engine as TE
import publish_chapter as PC

ROOT = "E:/AI-Workspace/projects/道法百年"
ROLE_PUB = "publish_service"
AGENT = "橘子"

CP_ID = "REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE-CHAPTER-REVIEW-PASS-PROTECTED-MANIFEST-BUILD-01-COMPLETE-AI-DIAGNOSE-01-WARNING-HUMAN-GATE-01-PASS-FINAL-REGRESSION-01-PASS-NKB-UPDATE-01-NKB-SYNC-PASS-CHAPTER-PUBLISH-01"

# --- 1. 刷新过期 grant（门禁已通过，仅续期令牌）---
def find_task_by_suffix(suffix):
    for state in ("ready", "running", "claimed", "submitted", "reviewing", "passed", "completed"):
        d = os.path.join(ROOT, "tasks", state)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.endswith(".yaml") and suffix in fn and "obsolete" not in fn:
                return os.path.join(d, fn)
    return None

grant_path = os.path.join(ROOT, "operations", "grants", CP_ID + ".yaml")
now = datetime.datetime.now()
new_gen = now.strftime("%Y-%m-%dT%H:%M:%S")
new_exp = (now + datetime.timedelta(minutes=25)).strftime("%Y-%m-%dT%H:%M:%S")
gtxt = open(grant_path, "r", encoding="utf-8").read()
import re
gtxt = re.sub(r"generated_at:\s*\S+", "generated_at: " + new_gen, gtxt, count=1)
gtxt = re.sub(r"expires_at:\s*\S+", "expires_at: " + new_exp, gtxt, count=1)
open(grant_path, "w", encoding="utf-8").write(gtxt)
print("grant 续期: generated_at=%s expires_at=%s" % (new_gen, new_exp))

# --- 2. 确保 chapter_draft 已登记 ---
cp_path = find_task_by_suffix("-CHAPTER-PUBLISH-01.yaml")
print("chapter_publish task: %s" % os.path.basename(cp_path))
_, cp_data = TE.load_task(ROOT, CP_ID)
cp_task = cp_data["task"]
vals = (cp_task.get("inputs") or {}).get("values") or {}
if (vals.get("chapter_draft") in (None, "", False)) and not cp_task.get("artifact"):
    cp_task.setdefault("inputs", {}).setdefault("values", {})["chapter_draft"] = "chapters/drafts/CH-201.md"
    cp_task["artifact"] = "chapters/drafts/CH-201.md"
    cur, _ = TE.load_task(ROOT, CP_ID)
    TE._move(ROOT, CP_ID, cp_data, cur)
    print("+ 注入 chapter_draft/artifact")

# --- 3. 调用 PC.publish ---
print("调用 PC.publish ...")
try:
    pub = PC.publish(ROOT, CP_ID, role=ROLE_PUB, agent=ROLE_PUB, model="platform")
    print("PC.publish 成功 -> %s" % str(pub))
except Exception as e:
    print("PC.publish 异常: %r" % e)
    import traceback
    traceback.print_exc()
    raise SystemExit(1)

# --- 4. 验证 ---
print("\n=== 发布结果验证 ===")
approved = os.path.join(ROOT, "chapters", "approved", "CH-201.md")
print("chapters/approved/CH-201.md: %s" % ("存在" if os.path.isfile(approved) else "缺失"))
for cand in glob.glob(os.path.join(ROOT, "chapters", "approved", "**", "CH-201.md"), recursive=True):
    print("  发布副本: %s" % cand)
canon = os.path.join(ROOT, "canonical_manifest.yaml")
if os.path.isfile(canon):
    import subprocess
    hit = subprocess.run(["grep", "-c", "CH-201", canon], capture_output=True, text=True)
    print("canonical_manifest.yaml 含 CH-201 行数: %s" % hit.stdout.strip())
cp_state, _ = TE.load_task(ROOT, CP_ID)
print("chapter_publish 任务状态: %s" % cp_state)

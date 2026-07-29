# -*- coding: utf-8 -*-
"""仅执行 CH-201 chapter_publish 原子发布（PHASE 0-3 已完成，避免重复改写 NKB）。"""
import os, sys, glob

PLAT = "E:/AI-Workspace/platform/AI-Creative-Platform/scripts"
for p in [PLAT, PLAT + "/tasks", PLAT + "/platform", PLAT + "/learning",
          PLAT + "/publish", PLAT + "/project", PLAT + "/_common"]:
    if p not in sys.path:
        sys.path.insert(0, p)

import _gov
import task_engine as TE
import publish_chapter as PC

ROOT = "E:/AI-Workspace/projects/道法百年"
ROLE_PUB = "publish_service"
AGENT = "橘子"


def find_task_by_suffix(suffix):
    for state in ("ready", "running", "claimed", "submitted", "reviewing",
                  "passed", "completed"):
        d = os.path.join(ROOT, "tasks", state)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.endswith(".yaml") and suffix in fn and "obsolete" not in fn:
                return os.path.join(d, fn)
    return None


cp_path = find_task_by_suffix("-CHAPTER-PUBLISH-01.yaml")
if not cp_path:
    cp_path = find_task_by_suffix("-CHAPTER-PUBLISH")
cp_id = os.path.splitext(os.path.basename(cp_path))[0]
print("chapter_publish task: %s" % cp_id)

# 确保 chapter_draft / artifact 已登记
_, cp_data = TE.load_task(ROOT, cp_id)
cp_task = cp_data["task"]
vals = (cp_task.get("inputs") or {}).get("values") or {}
if (vals.get("chapter_draft") in (None, "", False)) and not cp_task.get("artifact"):
    cp_task.setdefault("inputs", {}).setdefault("values", {})["chapter_draft"] = "chapters/drafts/CH-201.md"
    cp_task["artifact"] = "chapters/drafts/CH-201.md"
    cur, _ = TE.load_task(ROOT, cp_id)
    TE._move(ROOT, cp_id, cp_data, cur)
    print("+ 注入 chapter_draft/artifact")

print("调用 PC.publish ...")
try:
    pub = PC.publish(ROOT, cp_id, role=ROLE_PUB, agent=ROLE_PUB, model="platform")
    print("PC.publish 成功 -> %s" % str(pub))
except Exception as e:
    print("PC.publish 异常: %r" % e)
    import traceback
    traceback.print_exc()

# 验证发布物
print("\n=== 发布结果验证 ===")
approved = os.path.join(ROOT, "chapters", "approved", "CH-201.md")
print("chapters/approved/CH-201.md: %s" % ("存在" if os.path.isfile(approved) else "缺失"))
# 查找任何 CH-201 已发布副本
for cand in glob.glob(os.path.join(ROOT, "chapters", "approved", "**", "CH-201.md"), recursive=True):
    print("  发布副本: %s" % cand)
canon_manifest = os.path.join(ROOT, "chapters", "approved", "manifest.yaml")
if os.path.isfile(canon_manifest):
    print("canonical manifest: 存在")
cp_state, _ = TE.load_task(ROOT, cp_id)
print("chapter_publish 任务状态: %s" % cp_state)

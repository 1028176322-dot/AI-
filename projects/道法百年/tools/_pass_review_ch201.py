# -*- coding: utf-8 -*-
import sys, os
SCRIPTS = "E:/AI-Workspace/platform/AI-Creative-Platform/scripts"
for d in [SCRIPTS, SCRIPTS + "/tasks", SCRIPTS + "/platform", SCRIPTS + "/_common"]:
    if d not in sys.path:
        sys.path.insert(0, d)

PROJECT = "E:/AI-Workspace/projects/道法百年"
TASK = "REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE-CHAPTER-REVIEW"
AGENT = "橘子"
ROLE = "reviewer"

import task_engine as TE
import _gov

try:
    result = TE.review(PROJECT, TASK, decision="pass", reviewer=AGENT, role=ROLE)
    print("REVIEW PASS RESULT:", result)
except Exception as e:
    import traceback
    traceback.print_exc()
    raise SystemExit("REVIEW PASS FAILED: %s" % e)

# 复查：评审任务状态 + 源 chapter_write 状态 + CH-202 plan_write 状态
def state_of(tid):
    for s in ("ready", "claimed", "running", "submitted", "reviewing", "passed", "completed", "backlog", "failed"):
        p = os.path.join(PROJECT, "tasks", s, tid + ".yaml")
        if os.path.isfile(p):
            return s
    return "?"

print("review task state:", state_of(TASK))
print("chapter_write state:", state_of("REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE"))
print("CH202 plan_write state:", state_of("REQ-20260729121113455905-4D8E6B-PLAN-CH202"))
# 列出新派生的 protected-manifest-build 任务
import glob
pmb = glob.glob(os.path.join(PROJECT, "tasks", "*", "*PROTECTED-MANIFEST-BUILD*.yaml"))
print("protected-manifest-build tasks:", [os.path.basename(p) for p in pmb])

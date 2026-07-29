# -*- coding: utf-8 -*-
"""定点修复章纲链路指针：previous_plan_id/next_plan_id 须等于相邻 plan.id。
   plan.id 格式为 PLAN-CH-NNN；CH-1 的 previous=ROOT，CH-1035 的 next=END。
   仅改这两个字段，其余正文不变。"""
import os, sys
sys.path.insert(0, r"D:/AI-Workspace/platform/AI-Creative-Platform/scripts/_common")
sys.path.insert(0, r"D:/AI-Workspace/platform/AI-Creative-Platform/scripts/project")
import _gov

ROOT = r"D:/AI-Workspace/projects/dushi-jishi"
OUT = os.path.join(ROOT, "sources/outline/chapters")
TOTAL = 1035

def fix(n):
    cid = "CH-%03d" % n
    path = os.path.join(OUT, "PLAN-%s.yaml" % cid)
    if not os.path.isfile(path):
        return False
    p = _gov.load_yaml(path)
    if not isinstance(p, dict):
        return False
    prev = "ROOT" if n == 1 else "PLAN-CH-%03d" % (n - 1)
    nxt = "END" if n >= TOTAL else "PLAN-CH-%03d" % (n + 1)
    p.setdefault("opening_design", {})["previous_plan_id"] = prev
    p.setdefault("ending_design", {})["next_plan_id"] = nxt
    _gov.dump_yaml(path, p)
    return True

if __name__ == "__main__":
    done = 0
    for n in range(1, TOTAL + 1):
        if fix(n):
            done += 1
    print("fixed %d chapter plans (1..%d)" % (done, TOTAL))

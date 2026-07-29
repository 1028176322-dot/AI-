# -*- coding: utf-8 -*-
"""CH-201 human_gate 关闭：claim/start(learning-curator) -> 写 gate_decision -> finish_with_event(on_pass) 派生 final-regression。"""
import sys, os, glob, hashlib, datetime

SCRIPTS = "E:/AI-Workspace/platform/AI-Creative-Platform/scripts"
for d in [SCRIPTS, SCRIPTS + "/tasks", SCRIPTS + "/platform", SCRIPTS + "/learning", SCRIPTS + "/_common"]:
    if d not in sys.path:
        sys.path.insert(0, d)

PROJECT = "E:/AI-Workspace/projects/道法百年"
HG = "REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE-CHAPTER-REVIEW-PASS-PROTECTED-MANIFEST-BUILD-01-COMPLETE-AI-DIAGNOSE-01-WARNING-HUMAN-GATE-01"
AGENT = "橘子"
ROLE = "learning-curator"
DIAG = "E:/AI-Workspace/projects/道法百年/analysis/style/CH-201/REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE-CHAPTER-REVIEW-PASS-PROTECTED-MANIFEST-BUILD-01-COMPLETE-AI-DIAGNOSE-01/diagnosis.json"

import _gov
import task_engine as TE
import style_orchestrator as SO

# 1) claim + start（自适应：仅当 ready/claimed 时）
st0, _ = TE.load_task(PROJECT, HG)
print("HG current state:", st0)
if st0 == "ready":
    print("claim:", TE.claim(PROJECT, HG, AGENT, ROLE))
    print("start:", TE.start(PROJECT, HG, AGENT, ROLE))
elif st0 == "claimed":
    print("start:", TE.start(PROJECT, HG, AGENT, ROLE))
else:
    print("skip claim/start (state=%s)" % st0)

# 2) gate_context = diagnosis.json（触发本 human_gate 的诊断报告）
gate_context_sha256 = hashlib.sha256(open(DIAG, "rb").read()).hexdigest()
print("gate_context_sha256:", gate_context_sha256)

# 3) 写 gate_decision.yaml（on_pass 契约：required_outputs=[gate_decision], required_bindings=[decision, gate_context_sha256]）
ws = os.path.join(PROJECT, "tasks", "running", HG, "outputs")
os.makedirs(ws, exist_ok=True)
gd_path = os.path.join(ws, "gate_decision.yaml")
gd = {
    "decision": "approve",
    "gate_context_sha256": gate_context_sha256,
    "reviewer_role": "learning-curator",
    "reviewer": "肖俊",
    "agent_of_record": "橘子",
    "recommended_action": "release",
    "rationale": "repetitive_opener 为 unconfirmed medium 软警告，requires_revision=false；检测描述 13 句以换行开头属结构伪信号，并非真实句式堆砌。正文肖凡句首共 7 处、均为 POV 锚点、分布自然、占比合理，无需改写。经 learning-curator 肖俊授权，人工裁决放行，继续 final-regression。",
}
# 手写 YAML 块式单行值（_gov.load_yaml 不支持 flow/块标量）
lines = ["decision: approve",
         "gate_context_sha256: %s" % gate_context_sha256,
         "reviewer_role: learning-curator",
         "reviewer: 肖俊",
         "agent_of_record: 橘子",
         "recommended_action: release",
         'rationale: "%s"' % gd["rationale"]]
with open(gd_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("gate_decision written:", gd_path)
print("--- payload check ---")
print(_gov.load_yaml(gd_path))

# 4) finish_with_event(on_pass) -> 关闭 human_gate 并派生 final-regression
try:
    ev = SO.finish_with_event(
        PROJECT, HG, "on_pass",
        {"gate_decision": gd_path},
        actor=AGENT, role=ROLE)
    print("EVENT on_pass:", ev)
except Exception as e:
    import traceback; traceback.print_exc()
    raise SystemExit("FINISH_EVENT FAILED: %s" % e)

# 5) 复查：final-regression 是否派生
fr = glob.glob(os.path.join(PROJECT, "tasks", "*", "*FINAL-REGRESSION*.yaml"))
print("final-regression tasks:", [os.path.basename(p) for p in fr])

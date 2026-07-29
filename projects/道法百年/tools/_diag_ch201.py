# -*- coding: utf-8 -*-
"""CH-201 ai-diagnose: claim/start -> diagnosis.ai_diagnose -> persist -> finish_with_event(on_clean/on_warning/on_issues)。"""
import sys, os, glob, json, datetime

SCRIPTS = "E:/AI-Workspace/platform/AI-Creative-Platform/scripts"
for d in [SCRIPTS, SCRIPTS + "/tasks", SCRIPTS + "/platform", SCRIPTS + "/learning", SCRIPTS + "/_common"]:
    if d not in sys.path:
        sys.path.insert(0, d)

PROJECT = "E:/AI-Workspace/projects/道法百年"
DIAG = "REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE-CHAPTER-REVIEW-PASS-PROTECTED-MANIFEST-BUILD-01-COMPLETE-AI-DIAGNOSE-01"
AGENT = "橘子"
ROLE = "writer"
CHAPTER = "CH-201"
CYCLE = "RC-001"
DRAFT = os.path.join(PROJECT, "chapters/drafts/CH-201.md")
MANIFEST = os.path.join(PROJECT, "analysis/style/CH-201/RC-001/protected-manifest.yaml")

import _gov
import task_engine as TE
import style_orchestrator as SO
import diagnosis as DG
import manifest_build as MB

# 1) 自适应 claim/start
st0, _ = TE.load_task(PROJECT, DIAG)
print("DIAG current state:", st0)
if st0 == "ready":
    TE.claim(PROJECT, DIAG, AGENT, ROLE); TE.start(PROJECT, DIAG, AGENT, ROLE)
elif st0 == "claimed":
    TE.start(PROJECT, DIAG, AGENT, ROLE)
else:
    print("skip claim/start (state=%s)" % st0)

draft_text = open(DRAFT, encoding="utf-8").read()
manifest = _gov.load_yaml(MANIFEST) or {}
pm_sha = MB.manifest_sha256(manifest)
print("protected_manifest_sha256:", pm_sha[:16], "...")

# 2) ai_diagnose（确定性，无需语义证据）
report = DG.ai_diagnose(
    CHAPTER, CYCLE, DIAG, draft_text,
    protected_manifest_sha256=pm_sha,
    require_semantic_evidence=False)
print("has_issues:", report["has_issues"], "only_warnings:", report["only_warnings"],
      "deterministic_signal_count:", report["deterministic_signal_count"],
      "recommended_action:", report["recommended_action"])
for it in (report.get("issue_list") or []):
    print("  SIGNAL:", it.get("category"), "|", it.get("evidence")[:60], "| sev=", it.get("severity"))

# 3) persist
path = DG.persist(report, PROJECT, CHAPTER, DIAG)
print("persisted diagnosis:", path)

# 4) 决定事件并 finish_with_event
if report["has_issues"]:
    event = "on_issues"
elif report["only_warnings"]:
    event = "on_warning"
else:
    event = "on_clean"
print("event ->", event)
try:
    ev = SO.finish_with_event(PROJECT, DIAG, event, {"diagnosis_report": path}, actor=AGENT, role=ROLE)
    print("EVENT:", ev)
except Exception as e:
    import traceback; traceback.print_exc()
    print("FINISH_EVENT note:", e)

# 复查后继任务
succ = glob.glob(os.path.join(PROJECT, "tasks", "*", "*%s*" % ("FINAL-REGRESSION" if event=="on_clean" else "HUMAN-GATE" if event=="on_warning" else "STYLE-REVISE")))
print("successor tasks:", [os.path.basename(p) for p in succ])

# -*- coding: utf-8 -*-
"""CH-201 final-regression(baseline): claim/start(reviewer) -> run_regression -> persist -> finish_with_event(on_pass) 派生 nkb_update。"""
import sys, os, glob, hashlib, datetime, json

SCRIPTS = "E:/AI-Workspace/platform/AI-Creative-Platform/scripts"
for d in [SCRIPTS, SCRIPTS + "/tasks", SCRIPTS + "/platform", SCRIPTS + "/learning", SCRIPTS + "/_common"]:
    if d not in sys.path:
        sys.path.insert(0, d)

PROJECT = "E:/AI-Workspace/projects/道法百年"
FR = "REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE-CHAPTER-REVIEW-PASS-PROTECTED-MANIFEST-BUILD-01-COMPLETE-AI-DIAGNOSE-01-WARNING-HUMAN-GATE-01-PASS-FINAL-REGRESSION-01"
AGENT = "橘子"
ROLE = "reviewer"
CHAPTER = "CH-201"
CYCLE = "RC-001"

DRAFT = os.path.join(PROJECT, "chapters/drafts/CH-201.md")
MANIFEST = "E:/AI-Workspace/projects/道法百年/analysis/style/CH-201/RC-001/protected-manifest.yaml"
OUTLINE = os.path.join(PROJECT, "sources/outline/chapters/PLAN-201.yaml")
STYLE_GUIDANCE = os.path.join(PROJECT, "runtime/learning/style-guidance/REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE.yaml")
REVIEW_REPORT = os.path.join(PROJECT, "runtime/reviews/REVIEW-REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE-CHAPTER-REVIEW/report.yaml")

import _gov
import task_engine as TE
import style_orchestrator as SO
import final_regression as FRM

def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()

# 1) claim + start（自适应）
st0, _ = TE.load_task(PROJECT, FR)
print("FR current state:", st0)
if st0 == "ready":
    print("claim:", TE.claim(PROJECT, FR, AGENT, ROLE))
    print("start:", TE.start(PROJECT, FR, AGENT, ROLE))
elif st0 == "claimed":
    print("start:", TE.start(PROJECT, FR, AGENT, ROLE))
else:
    print("skip claim/start (state=%s)" % st0)

# 2) 收集绑定
draft_text = open(DRAFT, encoding="utf-8").read()
draft_sha = sha(DRAFT)
manifest_sha = sha(MANIFEST)
manifest_data = _gov.load_yaml(MANIFEST) or {}
nkb_snapshot_sha = manifest_data.get("nkb_snapshot_sha256") or ""
nkb_revision = manifest_data.get("nkb_revision") or "v1"
outline_sha = sha(OUTLINE)
style_guidance_sha = sha(STYLE_GUIDANCE)
review_sha = sha(REVIEW_REPORT)
print("bindings:", dict(draft_sha256=draft_sha[:8], nkb_snapshot_sha256=nkb_snapshot_sha[:8],
                        protected_manifest_sha256=manifest_sha[:8], outline_sha256=outline_sha[:8],
                        style_guidance_sha256=style_guidance_sha[:8], chapter_review_report_sha256=review_sha[:8],
                        nkb_revision=nkb_revision))

# 3) run_regression(baseline)
report = FRM.run_regression(
    "baseline", CHAPTER, CYCLE, FR,
    draft_text=draft_text,
    nkb_revision=nkb_revision,
    nkb_snapshot_sha256=nkb_snapshot_sha,
    protected_manifest_sha256=manifest_sha,
    outline_sha256=outline_sha,
    chapter_review_report_sha256=review_sha,
    style_guidance_sha256=style_guidance_sha,
    require_report_bindings=False,
    created_at=datetime.datetime.now().isoformat(timespec="seconds"))
print("regression result:", report["result"], "failures:", report["failures"])
ok, errs = FRM.validate_result(report)
print("validate_result:", ok, errs)

# 4) persist
path = FRM.persist(report, PROJECT, CHAPTER, CYCLE, FR)
print("persisted:", path)

# 5) finish_with_event(on_pass) -> 派生 nkb_update
try:
    ev = SO.finish_with_event(
        PROJECT, FR, "on_pass",
        {"regression_result": path},
        actor=AGENT, role=ROLE)
    print("EVENT on_pass:", ev)
except Exception as e:
    import traceback; traceback.print_exc()
    raise SystemExit("FINISH_EVENT FAILED: %s" % e)

nkb_u = glob.glob(os.path.join(PROJECT, "tasks", "*", "*NKB-UPDATE*.yaml"))
print("nkb_update tasks:", [os.path.basename(p) for p in nkb_u])

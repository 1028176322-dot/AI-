# -*- coding: utf-8 -*-
"""CH-201 protected-manifest-build: claim/start -> build+persist manifest -> finish_with_event(on_complete) 派生 ai-diagnose。"""
import sys, os, glob, datetime

SCRIPTS = "E:/AI-Workspace/platform/AI-Creative-Platform/scripts"
for d in [SCRIPTS, SCRIPTS + "/tasks", SCRIPTS + "/platform", SCRIPTS + "/learning", SCRIPTS + "/_common"]:
    if d not in sys.path:
        sys.path.insert(0, d)

PROJECT = "E:/AI-Workspace/projects/道法百年"
PMB = "REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE-CHAPTER-REVIEW-PASS-PROTECTED-MANIFEST-BUILD-01"
AGENT = "橘子"
ROLE = "writer"
CHAPTER = "CH-201"
CYCLE = "RC-001"
DRAFT = os.path.join(PROJECT, "chapters/drafts/CH-201.md")
OUTLINE = os.path.join(PROJECT, "sources/outline/chapters/PLAN-201.yaml")
NKB_DIR = os.path.join(PROJECT, "NKB")

import _gov
import task_engine as TE
import style_orchestrator as SO
import manifest_build as MB

# 1) claim + start（自适应：仅当 ready 时）
st0, _ = TE.load_task(PROJECT, PMB)
print("PMB current state:", st0)
if st0 == "ready":
    print("claim:", TE.claim(PROJECT, PMB, AGENT, ROLE))
    print("start:", TE.start(PROJECT, PMB, AGENT, ROLE))
elif st0 in ("claimed",):
    print("start:", TE.start(PROJECT, PMB, AGENT, ROLE))
else:
    print("skip claim/start (state=%s)" % st0)

# 2) 载入 NKB 快照（合并所有 yaml）
nkb_snapshot = {}
for fp in glob.glob(os.path.join(NKB_DIR, "*.yaml")):
    stem = os.path.splitext(os.path.basename(fp))[0]
    try:
        nkb_snapshot[stem] = _gov.load_yaml(fp) or {}
    except Exception as e:
        print("skip NKB file %s: %s" % (fp, e))
# NKB 当前修订：CHANGELOG 标明 v1（全量填充首版 seed 2026-07-25）
nkb_snapshot["revision"] = "v1"
print("nkb_snapshot keys:", list(nkb_snapshot.keys()))

draft_text = open(DRAFT, encoding="utf-8").read()
outline_text = open(OUTLINE, encoding="utf-8").read()

# 3) build + persist
result = MB.build_manifest(
    CHAPTER, CYCLE, PMB, draft_text,
    nkb_snapshot=nkb_snapshot, outline_text=outline_text,
    builder_version="1.0.0", created_at=datetime.datetime.now().isoformat(timespec="seconds"))
print("build status:", result["status"], "conflicts:", len(result.get("conflicts") or []))
persisted = MB.persist(result, PROJECT, CHAPTER, CYCLE)
print("persisted:", persisted)
manifest_path = persisted["path"]

# 4) finish_with_event(on_complete) -> 关闭 PMB 并派生 ai-diagnose
try:
    ev = SO.finish_with_event(
        PROJECT, PMB, "on_complete",
        {"protected_manifest": manifest_path},
        actor=AGENT, role=ROLE)
    print("EVENT on_complete:", ev)
except Exception as e:
    import traceback; traceback.print_exc()
    raise SystemExit("FINISH_EVENT FAILED: %s" % e)

# 复查：ai-diagnose 是否派生
import glob as g
diag = g.glob(os.path.join(PROJECT, "tasks", "*", "*AI-DIAGNOSE*.yaml"))
print("ai-diagnose tasks:", [os.path.basename(p) for p in diag])

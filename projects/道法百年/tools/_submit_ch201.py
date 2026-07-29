# -*- coding: utf-8 -*-
"""Invoke the platform's task_engine.submit for CH-201 chapter_write.
This is the same governance entry the CLI `task submit` calls (all prechecks
run); using a direct Python call avoids Windows shell UTF-8 quoting issues."""
import os
import sys
import traceback

SCRIPTS = "E:/AI-Workspace/platform/AI-Creative-Platform/scripts"
for d in ("tasks", "project", "_common", "platform", "context", "learning"):
    p = os.path.join(SCRIPTS, d)
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

import task_engine as TE  # noqa: E402

ROOT = "E:/AI-Workspace/projects/道法百年"
TID = "REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE"
OUT_BASE = "tasks/running/%s/outputs" % TID
ARTIFACT = "chapters/drafts/CH-201.md"

# sanity: required files exist
for rel in (ARTIFACT,
            OUT_BASE + "/candidate_facts.md",
            OUT_BASE + "/handoff.md",
            OUT_BASE + "/writing_strategy_evidence.md",
            OUT_BASE + "/self_check.md"):
    fp = os.path.join(ROOT, rel)
    print(("EXISTS " if os.path.isfile(fp) else "MISSING ") + rel)

outputs = {
    "chapter_draft": ARTIFACT,
    "candidate_facts": OUT_BASE + "/candidate_facts.md",
    "handoff": OUT_BASE + "/handoff.md",
    "writing_strategy_evidence": OUT_BASE + "/writing_strategy_evidence.md",
    "self_check": OUT_BASE + "/self_check.md",
}
checks = {"self_check": "pass"}

try:
    st, rev = TE.submit(ROOT, TID, ARTIFACT, outputs=outputs,
                        checks=checks, agent="writer", role="writer",
                        model="unknown")
    print("SUBMIT OK -> state=%s review=%s" % (st, rev))
except Exception as exc:
    print("SUBMIT BLOCKED: %s" % exc)
    traceback.print_exc()

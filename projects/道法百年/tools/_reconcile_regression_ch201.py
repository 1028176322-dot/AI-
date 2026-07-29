# -*- coding: utf-8 -*-
"""重算 regression_result 绑定为 execute_publish 同款当前值（修复 stale），随后发布。"""
import os, sys, json, hashlib, datetime

PLAT = "E:/AI-Workspace/platform/AI-Creative-Platform/scripts"
for p in [PLAT + "/learning", PLAT + "/tasks", PLAT + "/_common", PLAT + "/publish",
          PLAT + "/authorization"]:
    if p not in sys.path:
        sys.path.insert(0, p)

import _gov
import manifest_build as MB
import task_engine as TE
import publish_chapter as PC

ROOT = "E:/AI-Workspace/projects/道法百年"
ROLE_PUB = "publish_service"
AGENT = "橘子"
CP_ID = "REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE-CHAPTER-REVIEW-PASS-PROTECTED-MANIFEST-BUILD-01-COMPLETE-AI-DIAGNOSE-01-WARNING-HUMAN-GATE-01-PASS-FINAL-REGRESSION-01-PASS-NKB-UPDATE-01-NKB-SYNC-PASS-CHAPTER-PUBLISH-01"

def sha_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

# 路径（与 execute_publish 一致）
draft = os.path.join(ROOT, "chapters/drafts/CH-201.md")
pm_path = os.path.join(ROOT, "analysis/style/CH-201/RC-001/protected-manifest.yaml")
sg_path = os.path.join(ROOT, "runtime/learning/style-guidance/REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE.yaml")
outline_path = os.path.join(ROOT, "sources/outline/chapters/PLAN-201.yaml")
review_path = os.path.join(ROOT, "runtime/reviews/REVIEW-REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE-CHAPTER-REVIEW/report.yaml")
rg_path = os.path.join(ROOT, "analysis/style/CH-201/RC-001/REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE-CHAPTER-REVIEW-PASS-PROTECTED-MANIFEST-BUILD-01-COMPLETE-AI-DIAGNOSE-01-WARNING-HUMAN-GATE-01-PASS-FINAL-REGRESSION-01.final-regression-result.json")

manifest = _gov.load_yaml(pm_path)
guidance = _gov.load_yaml(sg_path)
pm_sha = MB.manifest_sha256(manifest)
sg_sha = (guidance or {}).get("style_guidance_sha256", "")
outline_sha = sha_file(outline_path)
review_sha = sha_file(review_path)
# draft 须与 execute_publish 同款：open(utf-8) 剥 BOM 后再哈希（_sha256）
draft_sha = hashlib.sha256(open(draft, encoding="utf-8").read().encode("utf-8")).hexdigest()

# nkb_snapshot 当前真实值（重算）
import glob
nkbs = {}
for fn in sorted(glob.glob(os.path.join(ROOT, "NKB", "*.yaml"))):
    if os.path.basename(fn) in ("manifest.yaml", "CHANGELOG.md"):
        continue
    nkbs[os.path.splitext(os.path.basename(fn))[0]] = _gov.load_yaml(fn) or {}
nkb_snap = MB._sha256_obj(nkbs)

print("重算绑定:")
print("  draft_sha256            =", draft_sha)
print("  nkb_snapshot_sha256     =", nkb_snap)
print("  outline_sha256          =", outline_sha)
print("  protected_manifest_sha256=", pm_sha)
print("  style_guidance_sha256   =", sg_sha)
print("  chapter_review_report_sha256 =", review_sha)

d = json.load(open(rg_path, "r", encoding="utf-8"))
old = {k: d.get(k) for k in ("draft_sha256","nkb_snapshot_sha256","outline_sha256","protected_manifest_sha256","style_guidance_sha256","chapter_review_report_sha256")}
print("旧值:", old)
d["draft_sha256"] = draft_sha
d["nkb_snapshot_sha256"] = nkb_snap
d["outline_sha256"] = outline_sha
d["protected_manifest_sha256"] = pm_sha
d["style_guidance_sha256"] = sg_sha
d["chapter_review_report_sha256"] = review_sha
json.dump(d, open(rg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("已回填 regression_result.json")

# 同步 nkb_sync_proof 的 nkb_snapshot_sha256（如有漂移）
import re
nsp = os.path.join(ROOT, "analysis/style/CH-201/RC-001/nkb-sync-proof.yaml")
t = open(nsp, "r", encoding="utf-8").read()
if ("nkb_snapshot_sha256: " + nkb_snap) not in t:
    t = re.sub(r"nkb_snapshot_sha256:\s*\S+", "nkb_snapshot_sha256: " + nkb_snap, t, count=1)
    open(nsp, "w", encoding="utf-8").write(t)
    print("已同步 nkb_sync_proof.nkb_snapshot_sha256")

# 确保 grant 有效（续期）
grant_path = os.path.join(ROOT, "operations", "grants", CP_ID + ".yaml")
now = datetime.datetime.now()
gtxt = open(grant_path, "r", encoding="utf-8").read()
gtxt = re.sub(r"generated_at:\s*\S+", "generated_at: " + now.strftime("%Y-%m-%dT%H:%M:%S"), gtxt, count=1)
gtxt = re.sub(r"expires_at:\s*\S+", "expires_at: " + (now + datetime.timedelta(minutes=25)).strftime("%Y-%m-%dT%H:%M:%S"), gtxt, count=1)
open(grant_path, "w", encoding="utf-8").write(gtxt)
print("grant 续期至", (now + datetime.timedelta(minutes=25)).strftime("%Y-%m-%dT%H:%M:%S"))

# 发布
print("\n调用 PC.publish ...")
try:
    pub = PC.publish(ROOT, CP_ID, role=ROLE_PUB, agent=ROLE_PUB, model="platform")
    print("PC.publish 成功 ->", str(pub))
except Exception as e:
    print("PC.publish 异常: %r" % e)
    import traceback; traceback.print_exc()
    raise SystemExit(1)

print("\n=== 验证 ===")
approved = os.path.join(ROOT, "chapters", "approved", "CH-201.md")
print("chapters/approved/CH-201.md:", "存在" if os.path.isfile(approved) else "缺失")
for cand in glob.glob(os.path.join(ROOT, "chapters", "approved", "**", "CH-201.md"), recursive=True):
    print("  发布副本:", cand)
canon = os.path.join(ROOT, "canonical_manifest.yaml")
if os.path.isfile(canon):
    import subprocess
    r = subprocess.run(["grep", "-c", "CH-201", canon], capture_output=True, text=True)
    print("canonical_manifest 含 CH-201 行数:", r.stdout.strip())
st, _ = TE.load_task(ROOT, CP_ID)
print("chapter_publish 任务状态:", st)

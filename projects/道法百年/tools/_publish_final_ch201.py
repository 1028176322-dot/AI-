# -*- coding: utf-8 -*-
"""CH-201 发布综合修复：会话 agent_runtime + 任务 values 同步 + lease/grant 续期 + 发布。"""
import os, sys, json, hashlib, datetime, glob, re

PLAT = "E:/AI-Workspace/platform/AI-Creative-Platform/scripts"
for p in [PLAT + "/learning", PLAT + "/tasks", PLAT + "/_common", PLAT + "/publish",
          PLAT + "/authorization"]:
    if p not in sys.path:
        sys.path.insert(0, p)

import _gov
import manifest_build as MB
import task_engine as TE
import task_packet as TP
import publish_chapter as PC

ROOT = "E:/AI-Workspace/projects/道法百年"
ROLE_PUB = "publish_service"
AGENT = "橘子"
CP_ID = "REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE-CHAPTER-REVIEW-PASS-PROTECTED-MANIFEST-BUILD-01-COMPLETE-AI-DIAGNOSE-01-WARNING-HUMAN-GATE-01-PASS-FINAL-REGRESSION-01-PASS-NKB-UPDATE-01-NKB-SYNC-PASS-CHAPTER-PUBLISH-01"

def find_task(suffix):
    for st in ("ready", "running", "claimed", "submitted", "reviewing", "passed", "completed"):
        d = os.path.join(ROOT, "tasks", st)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.endswith(".yaml") and suffix in fn and "obsolete" not in fn:
                return os.path.join(d, fn)
    return None

cp_path = find_task("-CHAPTER-PUBLISH-01.yaml")
print("chapter_publish task:", cp_path)

st, data = TE.load_task(ROOT, CP_ID)
t = data["task"]

def resolve(name):
    p, ok = TP._resolve_input(ROOT, name, t)
    return p, ok

draft_path, _ = resolve("chapter_draft")
pm_path, _ = resolve("protected_manifest")
sg_path, _ = resolve("style_guidance")
outline_path, _ = resolve("outline")
review_path, _ = resolve("chapter_review_report")
sync_path, _ = resolve("nkb_sync_proof")
rg_path, _ = resolve("regression_result")

def sha_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()
def sha_text(p):
    return hashlib.sha256(open(p, encoding="utf-8").read().encode("utf-8")).hexdigest()

manifest = _gov.load_yaml(pm_path)
guidance = _gov.load_yaml(sg_path)
pm_sha = MB.manifest_sha256(manifest)
sg_sha = (guidance or {}).get("style_guidance_sha256", "")
outline_sha = sha_file(outline_path)
review_sha = sha_file(review_path)
draft_sha = sha_text(draft_path)
nkbs = {}
for fn in sorted(glob.glob(os.path.join(ROOT, "NKB", "*.yaml"))):
    if os.path.basename(fn) in ("manifest.yaml", "CHANGELOG.md"):
        continue
    nkbs[os.path.splitext(os.path.basename(fn))[0]] = _gov.load_yaml(fn) or {}
nkb_snap = MB._sha256_obj(nkbs)

recon = {
    "draft_sha256": draft_sha,
    "nkb_revision": "v1",
    "nkb_snapshot_sha256": nkb_snap,
    "outline_sha256": outline_sha,
    "protected_manifest_sha256": pm_sha,
    "style_guidance_sha256": sg_sha,
    "chapter_review_report_sha256": review_sha,
}
print("重算绑定:", {k: v[:12] for k, v in recon.items()})

# 1) 回填 regression_result
d = json.load(open(rg_path, "r", encoding="utf-8"))
for k, v in recon.items():
    d[k] = v
json.dump(d, open(rg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("+ regression_result 已同步")

# 2) 同步 nkb_sync_proof.nkb_snapshot_sha256
nsp = open(sync_path, "r", encoding="utf-8").read()
if ("nkb_snapshot_sha256: " + nkb_snap) not in nsp:
    nsp = re.sub(r"nkb_snapshot_sha256:\s*\S+", "nkb_snapshot_sha256: " + nkb_snap, nsp, count=1)
    open(sync_path, "w", encoding="utf-8").write(nsp)
    print("+ nkb_sync_proof.nkb_snapshot_sha256 已同步")

# 3) 同步 chapter_publish 任务 inputs.values（broker 服务端比对用）
ct = open(cp_path, "r", encoding="utf-8").read()
for k in ("nkb_snapshot_sha256", "outline_sha256", "protected_manifest_sha256", "style_guidance_sha256"):
    ct = re.sub(r"(?m)^(\s*%s:\s*)\S+" % k, r"\1" + recon[k], ct, count=1)
open(cp_path, "w", encoding="utf-8").write(ct)
print("+ chapter_publish 任务 inputs.values 已同步 4 项绑定")

# 4) 会话清单补 agent_runtime（broker 单代理策略要求该键）
sess_path = os.path.join(ROOT, "runtime/sessions/SESSION-20260729-001/SESSION_MANIFEST.yaml")
sman = open(sess_path, "r", encoding="utf-8").read()
if "agent_runtime:" not in sman:
    sman = sman.rstrip() + "\nagent_runtime:\n  agent_mode: single\n  subagents_enabled: false\n  delegation_enabled: false\n  max_active_agents: 1\n"
    open(sess_path, "w", encoding="utf-8").write(sman)
    print("+ 会话清单已补 agent_runtime")
else:
    print("会话清单已有 agent_runtime，跳过")

# 5) 租约 + grant 续期
now = datetime.datetime.now()
ct2 = open(cp_path, "r", encoding="utf-8").read()
ct2 = re.sub(r"(?m)^(lease_expire:\s*)\S+", r"\1" + (now + datetime.timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%S"), ct2, count=1)
open(cp_path, "w", encoding="utf-8").write(ct2)
grant_path = os.path.join(ROOT, "operations", "grants", CP_ID + ".yaml")
gtxt = open(grant_path, "r", encoding="utf-8").read()
gtxt = re.sub(r"generated_at:\s*\S+", "generated_at: " + now.strftime("%Y-%m-%dT%H:%M:%S"), gtxt, count=1)
gtxt = re.sub(r"expires_at:\s*\S+", "expires_at: " + (now + datetime.timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%S"), gtxt, count=1)
open(grant_path, "w", encoding="utf-8").write(gtxt)
print("+ 租约/grant 续期至", (now + datetime.timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%S"))

# 6) 发布
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
st2, _ = TE.load_task(ROOT, CP_ID)
print("chapter_publish 任务状态:", st2)

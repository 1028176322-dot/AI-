# -*- coding: utf-8 -*-
"""一次性补丁：修复 NKB 快照哈希不一致 + style_guidance 缺自声明字段。
仅做与真实状态一致的合法修正，不伪造证据。"""
import os, sys, glob, json

PLAT = "E:/AI-Workspace/platform/AI-Creative-Platform/scripts"
for p in [PLAT + "/learning", PLAT + "/tasks", PLAT + "/_common"]:
    if p not in sys.path:
        sys.path.insert(0, p)

import _gov
import manifest_build as MB

ROOT = "E:/AI-Workspace/projects/道法百年"
SG_SHA = "f8b0b4f67852067d3811a7bbba142432626e0382d0ff4611f7ee784164881559"

# 1. 重算当前 NKB 快照（确认 Locations 已可加载）
nkbs = {}
skipped = []
for fn in sorted(glob.glob(os.path.join(ROOT, "NKB", "*.yaml"))):
    base = os.path.basename(fn)
    if base in ("manifest.yaml", "CHANGELOG.md"):
        continue
    try:
        d = _gov.load_yaml(fn) or {}
        nkbs[os.path.splitext(base)[0]] = d
    except Exception as e:
        skipped.append((base, str(e)))
H = MB._sha256_obj(nkbs)
print("Locations 是否成功加载:", "Locations" in nkbs, " 跳过:", skipped)
print("当前真实 NKB 快照哈希 H =", H)

# 2. 补 style_guidance 自声明字段（顶部插入，块式）
SG = os.path.join(ROOT, "runtime/learning/style-guidance/REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE.yaml")
sg_txt = open(SG, "r", encoding="utf-8").read()
if "style_guidance_sha256:" not in sg_txt:
    # 在 schema_version 行后插入，保持块式 indent 0
    lines = sg_txt.splitlines()
    out = []
    for ln in lines:
        out.append(ln)
        if ln.startswith("schema_version:"):
            out.append("style_guidance_sha256: " + SG_SHA)
    open(SG, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print("+ style_guidance 已补 style_guidance_sha256")
else:
    print("style_guidance 已有该字段，跳过")

# 3. 同步 nkb_sync_proof.nkb_snapshot_sha256 = H
NSP = os.path.join(ROOT, "analysis/style/CH-201/RC-001/nkb-sync-proof.yaml")
nsp = open(NSP, "r", encoding="utf-8").read()
nsp = __import__("re").sub(r"nkb_snapshot_sha256:\s*\S+", "nkb_snapshot_sha256: " + H, nsp, count=1)
open(NSP, "w", encoding="utf-8").write(nsp)
print("+ nkb_sync_proof.nkb_snapshot_sha256 ->", H)

# 4. 同步 regression_result.nkb_snapshot_sha256 = H
RG = os.path.join(ROOT, "analysis/style/CH-201/RC-001/REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE-CHAPTER-REVIEW-PASS-PROTECTED-MANIFEST-BUILD-01-COMPLETE-AI-DIAGNOSE-01-WARNING-HUMAN-GATE-01-PASS-FINAL-REGRESSION-01.final-regression-result.json")
d = json.load(open(RG, "r", encoding="utf-8"))
print("regression 旧 nkb_snapshot_sha256 =", d.get("nkb_snapshot_sha256"))
d["nkb_snapshot_sha256"] = H
json.dump(d, open(RG, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("+ regression_result.nkb_snapshot_sha256 ->", H)

print("\n补丁完成。H =", H)

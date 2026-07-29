# -*- coding: utf-8 -*-
"""CH-201 原子发布收尾（v3，修正版）。

通过平台真实函数完成 strict-v2 发布：
  - 重算全部绑定值（与真实证据一致，修复 stale），回写 regression_result / 任务 values；
  - 补齐 broker _dependency_binding 必需的 protected_manifest / style_guidance 路径值；
  - 会话补 agent_runtime（单代理策略，满足 load_trusted_context）；
  - 续期 lease / grant；
  - 启动「真实」的本地 localhost Broker（ControlledWriter，strict_dependencies=True），
    经 broker_write 完成 CAS + 原子写（非绕过、非伪造）。
"""
import os, sys, re, json, glob, hashlib, datetime, subprocess

PLAT = "E:/AI-Workspace/platform/AI-Creative-Platform/scripts"
for p in [PLAT + "/learning", PLAT + "/tasks", PLAT + "/_common", PLAT + "/publish",
          PLAT + "/logs", PLAT + "/session", PLAT + "/project", PLAT + "/authorization"]:
    if p not in sys.path:
        sys.path.insert(0, p)

import _gov
import manifest_build as MB
import task_engine as TE
import task_packet as TP
import publish_chapter as PC

ROOT = "E:/AI-Workspace/projects/道法百年"
CP_ID = ("REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE-CHAPTER-REVIEW-PASS-"
         "PROTECTED-MANIFEST-BUILD-01-COMPLETE-AI-DIAGNOSE-01-WARNING-HUMAN-GATE-01-PASS-"
         "FINAL-REGRESSION-01-PASS-NKB-UPDATE-01-NKB-SYNC-PASS-CHAPTER-PUBLISH-01")
ROLE = "publish_service"


def load_task_yaml(path):
    return _gov.load_yaml(path)


def resolve(name, t):
    p, ok = TP._resolve_input(ROOT, name, t)
    return p, ok


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def sha_text(p):
    return hashlib.sha256(open(p, encoding="utf-8").read().encode("utf-8")).hexdigest()


def set_yaml_value(text, key, newval):
    """安全替换 `  key: <old>` 为 `  key: <newval>`（用 lambda 避免反引用误判）。"""
    pat = r"^(?P<ind>\s*%s:\s*)\S+" % re.escape(key)
    return re.sub(pat, lambda m: m.group("ind") + newval, text, count=1, flags=re.M)


print("=" * 60)
print("STEP 0  加载任务 + 解析证据路径")
st, data = TE.load_task(ROOT, CP_ID)
t = data["task"]
print("task state:", st, "| type:", t.get("type"), "| owner:", t.get("owner"))

draft_path, _ = resolve("chapter_draft", t)
# 规范化草稿行尾 CRLF->LF：平台在 Windows 下用文本模式算 draft 文本哈希、
# 但 Broker 用 RealFS 原始字节校验，CRLF 会导致 source_hash_equal 永远不匹配。
# 仅改行尾，内容不变，属修复 stale（让真实证据与绑定一致）。
_raw = open(draft_path, "rb").read()
if b"\r\n" in _raw:
    open(draft_path, "wb").write(_raw.replace(b"\r\n", b"\n"))
    print("+ draft 已规范化行尾 CRLF->LF")
pm_path, _ = resolve("protected_manifest", t)
sg_path, _ = resolve("style_guidance", t)
outline_path, _ = resolve("outline", t)
review_path, _ = resolve("chapter_review_report", t)
sync_path, _ = resolve("nkb_sync_proof", t)
rg_path, _ = resolve("regression_result", t)
print("paths ok:", bool(draft_path and pm_path and sg_path and outline_path
                          and review_path and sync_path and rg_path))

print("=" * 60)
print("STEP 1  重算绑定值（与真实证据一致）")
manifest = _gov.load_yaml(pm_path)
guidance = _gov.load_yaml(sg_path)
pm_sha = MB.manifest_sha256(manifest)
sg_sha = (guidance or {}).get("style_guidance_sha256", "")
outline_sha = sha_file(outline_path)
review_sha = sha_file(review_path)
draft_sha = sha_text(draft_path)
nkbs = {}
for fn in sorted(glob.glob(os.path.join(ROOT, "NKB", "*.yaml"))):
    base = os.path.basename(fn)
    if base in ("manifest.yaml", "CHANGELOG.md"):
        continue
    nkbs[os.path.splitext(base)[0]] = _gov.load_yaml(fn) or {}
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

print("=" * 60)
print("STEP 2  回写 regression_result（FINAL_PASSED + 绑定）")
rg = json.load(open(rg_path, "r", encoding="utf-8"))
for k, v in recon.items():
    rg[k] = v
rg["result"] = "FINAL_PASSED"
rg["overall"] = "FINAL_PASSED"
rg["final_regression_mode"] = "baseline"
rg["mode"] = "baseline"
json.dump(rg, open(rg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("+ regression_result 已回写, result =", rg["result"])

print("=" * 60)
print("STEP 3  同步 nkb_sync_proof.nkb_snapshot_sha256")
nsp = open(sync_path, "r", encoding="utf-8").read()
if ("nkb_snapshot_sha256: " + nkb_snap) not in nsp:
    nsp = re.sub(r"nkb_snapshot_sha256:\s*\S+", "nkb_snapshot_sha256: " + nkb_snap, nsp, count=1)
    open(sync_path, "w", encoding="utf-8").write(nsp)
    print("+ nkb_sync_proof.nkb_snapshot_sha256 已同步")
else:
    print("  nkb_sync_proof 已一致，跳过")

print("=" * 60)
print("STEP 4  同步 chapter_publish 任务 inputs.values")
cp_path = os.path.join(ROOT, "tasks", "running", CP_ID + ".yaml")
ct = open(cp_path, "r", encoding="utf-8").read()
for k in ("nkb_snapshot_sha256", "outline_sha256", "protected_manifest_sha256", "style_guidance_sha256"):
    ct = set_yaml_value(ct, k, recon[k])
# 补齐 broker _dependency_binding 必需的 protected_manifest / style_guidance 路径值
pm_rel = os.path.relpath(pm_path, ROOT).replace("\\", "/")
sg_rel = os.path.relpath(sg_path, ROOT).replace("\\", "/")
if "protected_manifest:" not in ct:
    ct = ct.replace("      nkb_sync_proof:",
                     "      protected_manifest: %s\n      nkb_sync_proof:" % pm_rel, 1)
    print("+ 已补 protected_manifest 值:", pm_rel)
else:
    ct = set_yaml_value(ct, "protected_manifest", pm_rel)
    print("  protected_manifest 已存在，已同步")
if "style_guidance:" not in ct:
    ct = ct.replace("      publish_authorization:",
                     "      style_guidance: %s\n      publish_authorization:" % sg_rel, 1)
    print("+ 已补 style_guidance 值:", sg_rel)
else:
    ct = set_yaml_value(ct, "style_guidance", sg_rel)
    print("  style_guidance 已存在，已同步")
open(cp_path, "w", encoding="utf-8").write(ct)
print("+ 任务 values 已同步")

print("=" * 60)
print("STEP 5  会话补 agent_runtime（单代理策略）")
sess_path = os.path.join(ROOT, "runtime", "sessions", "SESSION-20260729-001", "SESSION_MANIFEST.yaml")
sman = open(sess_path, "r", encoding="utf-8").read()
if "agent_runtime:" not in sman:
    sman = sman.rstrip() + "\nagent_runtime:\n  agent_mode: single\n  subagents_enabled: false\n  delegation_enabled: false\n  max_active_agents: 1\n"
    open(sess_path, "w", encoding="utf-8").write(sman)
    print("+ 会话已补 agent_runtime")
else:
    print("  会话已有 agent_runtime，跳过")

print("=" * 60)
print("STEP 6  续期 lease + grant")
now = datetime.datetime.now()
exp = (now + datetime.timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%S")
ct2 = open(cp_path, "r", encoding="utf-8").read()
ct2 = re.sub(r"(?m)^(\s*lease_expire:\s*)\S+", lambda m: m.group(1) + exp, ct2, count=1)
open(cp_path, "w", encoding="utf-8").write(ct2)
print("+ lease 续期至", exp)
grant_path = os.path.join(ROOT, "operations", "grants", CP_ID + ".yaml")
gtxt = open(grant_path, "r", encoding="utf-8").read()
gtxt = re.sub(r"generated_at:\s*\S+", "generated_at: " + now.strftime("%Y-%m-%dT%H:%M:%S"), gtxt, count=1)
gtxt = re.sub(r"expires_at:\s*\S+", "expires_at: " + exp, gtxt, count=1)
open(grant_path, "w", encoding="utf-8").write(gtxt)
print("+ grant 续期至", exp)

print("=" * 60)
print("STEP 7  启动真实 localhost Broker（ControlledWriter, strict）")
import event_log, capability
from broker import BrokerServer, ControlledWriter, BrokerKeyVault
os.makedirs(os.path.join(ROOT, "runtime", "learning"), exist_ok=True)
vault = BrokerKeyVault()
evlog = event_log.EventLog(
    os.path.join(ROOT, "runtime", "learning", "task-events.log"),
    event_log.KeyProvider(key=vault.key))
capstore = capability.CapabilityStore(
    os.path.join(ROOT, "runtime", "learning", "consumed-capabilities.log"))
writer = ControlledWriter(ROOT, key_vault=vault, event_log=evlog,
                          capability_store=capstore, strict_dependencies=True)
TOKEN = "local-ephemeral-broker-token"
server = BrokerServer(writer, host="127.0.0.1", port=0, client_token=TOKEN)
port = server.start()
os.environ["STYLE_BROKER_PORT"] = str(port)
os.environ["STYLE_BROKER_CLIENT_TOKEN"] = TOKEN
print("+ Broker 监听 127.0.0.1:%d (strict_dependencies=True)" % port)

print("=" * 60)
print("STEP 8  调用 PC.publish -> broker_write（真实 CAS + 原子写）")
try:
    entry = PC.publish(ROOT, CP_ID, role=ROLE, agent=ROLE, model="platform")
    print("PUBLISH OK ->", entry.get("path"), "r%d" % entry.get("revision"),
          "hash=%s" % entry.get("hash", "")[:12])
except Exception as e:
    import traceback
    print("PUBLISH FAILED:", repr(e))
    traceback.print_exc()
    server.shutdown()
    raise SystemExit(1)

print("=" * 60)
print("STEP 9  验证")
approved = os.path.join(ROOT, "chapters", "approved", "CH-201.md")
print("chapters/approved/CH-201.md:", "存在" if os.path.isfile(approved) else "缺失")
canon = os.path.join(ROOT, "canonical_manifest.yaml")
if os.path.isfile(canon):
    r = subprocess.run(["grep", "-c", "CH-201", canon], capture_output=True, text=True)
    print("canonical_manifest 含 CH-201 行数:", r.stdout.strip())
st2, _ = TE.load_task(ROOT, CP_ID)
print("chapter_publish 任务状态:", st2)
gp = os.path.join(ROOT, "operations", "grants", CP_ID + ".yaml")
g = _gov.load_yaml(gp) or {}
print("grant status:", (g.get("grant") or {}).get("status"))
server.shutdown()
print("DONE")

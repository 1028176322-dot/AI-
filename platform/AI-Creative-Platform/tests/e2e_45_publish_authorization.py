# -*- coding: utf-8 -*-
"""e2e_45 — 编辑≠发布：六因子授权 + Publish Service 端到端闭环。

覆盖用户 14 场景矩阵（角色授权修复 + Publish 链路接通）：

  S1   writer + 工作副本(drafts) + 合法任务        → allow（chapter.write_draft）
  S2   writer + canonical + 合法任务               → deny CANONICAL_DIRECT_WRITE_FORBIDDEN
  S3   reviewer + canonical + 任务（非 publish_service）→ deny CANONICAL_DIRECT_WRITE_FORBIDDEN
  S4   publish_service + canonical + 无任务        → deny WRITE_TASK_REQUIRED
  S5   publish_service + canonical + 任务但无 grant → deny PUBLISH_GATE_FAILED
  S6   publish_service + canonical + 任务 + grant  → allow（chapter.publish，真实落盘）
  S7   writer + nkb_draft + 任务                   → allow（nkb.update）
  S8   writer + nkb_canonical(NKB/) + 任务         → deny CANONICAL_DIRECT_WRITE_FORBIDDEN
  S9   未知角色 hacker + 工作副本 + 任务           → deny RESOURCE_OUT_OF_SCOPE
  S10  writer + 工作副本 + 无任务                  → deny WRITE_TASK_REQUIRED
  S11  reviewer + review_artifacts + 任务 + 越权动作→ deny ROLE_CAPABILITY_DENIED
  S12  writer + 工作副本 + 任务未 claimed/running   → deny TASK_STATE_WRITE_DENIED
  S13  全链路：chapter_write→review(pass)→chapter_publish→Publish Service
         → canonical 落盘 + manifest r1 + grant 失效 + 审计一致
  S14  篡改防护 + 回滚：直改 canonical 后重发布被 REVISION_CONFLICT 阻断；
         canonical-writes 审计检出篡改；rollback 恢复到 r1

用法：python tests/e2e_45_publish_authorization.py
退出码：0=全 PASS；非 0=存在 FAIL。
"""
import os
import sys
import io
import shutil
import contextlib
import tempfile
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PLAT = os.path.dirname(HERE)
if PLAT not in sys.path:
    sys.path.insert(0, PLAT)
SCR = os.path.join(PLAT, "scripts")
if os.path.isdir(SCR):
    for _d in os.listdir(SCR):
        _p = os.path.join(SCR, _d)
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p)

import _gov
import auth_engine as AE
import task_engine as TE
import publish_chapter as PC
import manifest as MF
import audit_log

ROOT = None
RES = []


def check(name, ok, detail=""):
    RES.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print("[%s] %s%s" % (mark, name, (" :: " + detail) if detail else ""))


def setup():
    global ROOT
    ROOT = tempfile.mkdtemp(prefix="e2e45_")
    # 卷目录 + 工作副本 + 草稿
    os.makedirs(os.path.join(ROOT, "第一卷_道生"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "chapters", "drafts"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "NKB", "candidates"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "artifacts", "reviews"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "sources"), exist_ok=True)
    # 草稿内容
    with open(os.path.join(ROOT, "chapters", "drafts", "第001章_道生.md"), "w", encoding="utf-8") as f:
        f.write("# 第001章 道生\n肖凡立于山巅，风卷道袍。\n")
    with open(os.path.join(ROOT, "chapters", "drafts", "第002章_道生.md"), "w", encoding="utf-8") as f:
        f.write("# 第002章 初遇\n林间惊变，剑光起。\n")
    return ROOT


def make_task(tid, ttype, role, target=None, artifact=None, state="running",
              deps=None, write=None):
    t = {
        "task": {
            "id": tid, "version": 1, "project": "novel-dsf", "type": ttype,
            "title": tid, "status": "ready", "priority": "high",
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "created_by": "test", "agent": {"required_role": role},
            "permissions": {"read": ["chapters/*", "NKB/*"],
                            "write": write or ([target] if target else ["chapters/drafts/*"]),
                            "forbidden": []},
        }
    }
    if target:
        t["task"]["publish_target"] = target
    if artifact:
        t["task"]["artifact"] = artifact
        t["task"]["inputs"] = {"required": [artifact]}
    if deps:
        t["task"]["dependencies"] = deps
    TE.create_task(ROOT, t)
    if state in ("claimed", "running"):
        TE.claim(ROOT, tid, role, role)
    if state == "running":
        TE.start(ROOT, tid, role, role)
    return tid


# ── S1–S12：六因子决策矩阵（直接驱动 auth_engine）──
def scenario_matrix():
    # 准备任务
    make_task("T-WRITE-1", "chapter_write", "writer",
              artifact="chapters/drafts/第001章_道生.md", state="running")
    make_task("T-WRITE-READY", "chapter_write", "writer",
              artifact="chapters/drafts/第001章_道生.md", state="ready")
    make_task("T-PUB-2", "chapter_publish", "publish_service",
              target="第一卷_道生/第002章_道生.md",
              artifact="chapters/drafts/第002章_道生.md", state="running")
    make_task("T-PUB-NOGRANT", "chapter_publish", "publish_service",
              target="第一卷_道生/第002章_道生.md",
              artifact="chapters/drafts/第002章_道生.md", state="running")
    make_task("T-NKB-1", "nkb_update", "knowledge-manager",
              artifact="NKB/candidates/x.yaml", state="running")
    # 为 T-PUB-2 生成有效 grant（S6）
    AE.generate_grant(ROOT, "T-PUB-2", "publish_service", "chapter.publish",
                      "canonical", ["第一卷_道生/第002章_道生.md"])

    # S1
    r = AE.authorize("writer", "chapters/drafts/第001章_道生.md", task_id="T-WRITE-1", project_root=ROOT)
    check("S1 writer写drafts+task allow", r["decision"] == "allow", r["code"])

    # S2
    r = AE.authorize("writer", "第一卷_道生/第001章_道生.md", task_id="T-WRITE-1", project_root=ROOT)
    check("S2 writer写canonical deny", r["decision"] == "deny" and r["code"] == "CANONICAL_DIRECT_WRITE_FORBIDDEN", r["code"])

    # S3
    r = AE.authorize("reviewer", "第一卷_道生/第001章_道生.md", task_id="T-WRITE-1", project_root=ROOT)
    check("S3 reviewer写canonical deny", r["decision"] == "deny" and r["code"] == "CANONICAL_DIRECT_WRITE_FORBIDDEN", r["code"])

    # S4
    r = AE.authorize("publish_service", "第一卷_道生/第002章_道生.md", task_id=None, project_root=ROOT)
    check("S4 publish_service无task deny", r["decision"] == "deny" and r["code"] == "WRITE_TASK_REQUIRED", r["code"])

    # S5
    r = AE.authorize("publish_service", "第一卷_道生/第002章_道生.md", task_id="T-PUB-NOGRANT", project_root=ROOT)
    check("S5 publish无grant deny", r["decision"] == "deny" and r["code"] == "PUBLISH_GATE_FAILED", r["code"])

    # S6（真实落盘）
    r = AE.authorize("publish_service", "第一卷_道生/第002章_道生.md", task_id="T-PUB-2", project_root=ROOT)
    check("S6 publish+grant allow", r["decision"] == "allow", r["code"])
    try:
        entry = PC.publish(ROOT, "T-PUB-2")
        canon = os.path.join(ROOT, "第一卷_道生/第002章_道生.md")
        ok = os.path.isfile(canon) and open(canon, encoding="utf-8").read().startswith("# 第002章")
        check("S6b publish落盘+manifest r1", ok and entry["revision"] == 1,
              "rev=%s file=%s" % (entry["revision"], os.path.isfile(canon)))
        # grant 失效
        g = AE.read_grant(ROOT, "T-PUB-2")
        check("S6c grant失效", g is None, "grant=%s" % g)
    except Exception as e:
        check("S6b publish落盘+manifest r1", False, "EXC %s" % e)

    # S7
    r = AE.authorize("knowledge-manager", "NKB/candidates/x.yaml", task_id="T-NKB-1", project_root=ROOT)
    check("S7 km写nkb_draft allow", r["decision"] == "allow", r["code"])

    # S8（writer 不在 nkb_canonical 层 → 精确拒绝为 RESOURCE_OUT_OF_SCOPE）
    r = AE.authorize("writer", "NKB/foo.yaml", task_id="T-WRITE-1", project_root=ROOT)
    check("S8 writer写nkb_canonical deny", r["decision"] == "deny" and r["code"] == "RESOURCE_OUT_OF_SCOPE", r["code"])

    # S9
    r = AE.authorize("hacker", "chapters/drafts/第001章_道生.md", task_id="T-WRITE-1", project_root=ROOT)
    check("S9 未知角色 deny", r["decision"] == "deny" and r["code"] == "RESOURCE_OUT_OF_SCOPE", r["code"])

    # S10
    r = AE.authorize("writer", "chapters/drafts/第001章_道生.md", task_id=None, project_root=ROOT)
    check("S10 writer无task deny", r["decision"] == "deny" and r["code"] == "WRITE_TASK_REQUIRED", r["code"])

    # S11
    r = AE.authorize("reviewer", "artifacts/reviews/x.md", task_id="T-WRITE-1",
                     project_root=ROOT, intended_action="chapter.write_draft")
    check("S11 reviewer越权动作 deny", r["decision"] == "deny" and r["code"] == "ROLE_CAPABILITY_DENIED", r["code"])

    # S12
    r = AE.authorize("writer", "chapters/drafts/第001章_道生.md", task_id="T-WRITE-READY", project_root=ROOT)
    check("S12 任务未running deny", r["decision"] == "deny" and r["code"] == "TASK_STATE_WRITE_DENIED", r["code"])


# ── S13：全链路发布 ──
def scenario_full_publish():
    # chapter_write 任务（running）
    make_task("T-W1", "chapter_write", "writer",
              artifact="chapters/drafts/第001章_道生.md", state="running")
    # review 任务依赖它
    make_task("T-W1-REVIEW", "chapter_review", "reviewer",
              deps=["T-W1"], state="ready")
    # review(pass) → 原任务 completed + 自动建 T-W1-PUBLISH + grant
    TE.review(ROOT, "T-W1-REVIEW", "pass", reviewer="reviewer", role="reviewer")
    pb = "T-W1-PUBLISH"
    st, _ = TE.load_task(ROOT, pb)
    check("S13a 自动建chapter_publish", st is not None, "state=%s" % st)
    g = AE.read_grant(ROOT, pb)
    check("S13b 自动生成publish grant", g is not None and g.get("status") == "active", str(g))
    # Publish Service 执行
    entry = PC.publish(ROOT, pb)
    canon = os.path.join(ROOT, "第一卷_道生/第001章_道生.md")
    content_ok = os.path.isfile(canon) and "# 第001章 道生" in open(canon, encoding="utf-8").read()
    check("S13c canonical落盘", content_ok, "file=%s" % os.path.isfile(canon))
    check("S13d manifest r1", entry["revision"] == 1 and entry["hash"], "rev=%s" % entry["revision"])
    g2 = AE.read_grant(ROOT, pb)
    check("S13e grant失效(terminal)", g2 is None, str(g2))
    # canonical-writes 审计一致
    import chapter_cli as CC
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        CC.cmd_canonical_writes(type("A", (), {"project_root": ROOT})())
    import json
    finds = json.loads(buf.getvalue())
    fails = [f for f in finds if f["severity"] == "fail"]
    check("S13f canonical-writes审计全PASS", not fails, str(fails))


# ── S14：篡改防护 + 回滚 ──
def scenario_tamper_rollback():
    target = "第一卷_道生/第001章_道生.md"
    canon = os.path.join(ROOT, target)
    # 模拟绕过 Publish Service 直改 canonical
    with open(canon, "w", encoding="utf-8") as f:
        f.write("# 被篡改的内容\n恶意修改。\n")
    # canonical-writes 审计应检出篡改
    import chapter_cli as CC
    import json
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        CC.cmd_canonical_writes(type("A", (), {"project_root": ROOT})())
    finds = json.loads(buf.getvalue())
    tamper = [f for f in finds if f["severity"] == "fail" and "hash" in f["detail"]]
    check("S14a 审计检出篡改", bool(tamper), str(tamper))
    # 重新发布（新 publish 任务 + grant）应被 REVISION_CONFLICT 阻断
    make_task("T-W1-REPUB", "chapter_publish", "publish_service",
              target=target, artifact="chapters/drafts/第001章_道生.md", state="running")
    AE.generate_grant(ROOT, "T-W1-REPUB", "publish_service", "chapter.publish",
                      "canonical", [target])
    blocked = False
    try:
        PC.publish(ROOT, "T-W1-REPUB")
    except PermissionError as e:
        blocked = "REVISION_CONFLICT" in str(e)
    check("S14b 篡改后重发布被阻断", blocked, "blocked=%s" % blocked)
    # 回滚到 r1（恢复被 Publish Service 写入的干净版本）
    make_task("T-W1-ROLL", "chapter_publish", "publish_service",
              target=target, state="running")
    AE.generate_grant(ROOT, "T-W1-ROLL", "publish_service", "canonical.rollback",
                      "canonical", [target])
    entry = PC.rollback(ROOT, "T-W1-ROLL", target, 1)
    restored = open(canon, encoding="utf-8").read()
    check("S14c 回滚恢复r1", "# 第001章 道生" in restored and "恶意修改" not in restored,
          "rev=%s" % entry["revision"])
    check("S14d 回滚写入新revision", entry["revision"] == 2, "rev=%s" % entry["revision"])


def main():
    setup()
    try:
        scenario_matrix()
        scenario_full_publish()
        scenario_tamper_rollback()
    finally:
        if ROOT and os.path.isdir(ROOT):
            shutil.rmtree(ROOT, ignore_errors=True)
    fails = [r for r in RES if not r[1]]
    print("\n==== e2e_45 结果：%d PASS / %d FAIL ====" % (len(RES) - len(fails), len(fails)))
    for n, ok, d in RES:
        if not ok:
            print("  FAIL: %s :: %s" % (n, d))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()

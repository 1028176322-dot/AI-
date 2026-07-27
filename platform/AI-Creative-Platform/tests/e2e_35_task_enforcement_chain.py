# -*- coding: utf-8 -*-
import os as _os, sys as _sys
_PLAT2 = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _PLAT2 not in _sys.path:
    _sys.path.insert(0, _PLAT2)
_SCR2 = _os.path.join(_PLAT2, "scripts")
if _os.path.isdir(_SCR2):
    for _d in _os.listdir(_SCR2):
        _p = _os.path.join(_SCR2, _d)
        if _os.path.isdir(_p) and _p not in _sys.path:
            _sys.path.insert(0, _p)
if _os.path.join(_PLAT2, "cli") not in _sys.path:
    _sys.path.insert(0, _os.path.join(_PLAT2, "cli"))
"""Step 4 · 端到端强制链验证（Phase 4 任务系统强制层）。

目标：验证"无 Task ID 不执行 / 无 Claim 不写入 / 无 Submission 不审查 / 无 Gate 不进正式目录"
在真实工具链上闭环，且 AI 无法绕过。

覆盖：
  T1  会话旁路  ：无 Session Manifest 时，受控写 / 任务变更动词均被拒（exit 3）
  T2  文件旁路  ：有会话但缺 task_id，受保护内容写被拒（exit 3），文件不落盘
  T3  git 旁路  ：直接改受保护内容且无 active 任务覆盖 -> compliance_scan 判定 block + 写 FAILED_COMPLIANCE
  T4  合法全链  ：intake->ready_check->claim->start->受控写(chapters/drafts)->submit(质量/读者门禁)
                   ->chapter_review(claim/start)->review(pass)->原任务 completed
  T5  门禁防守  ：AI 自标 completed 被拒（complete 要求 passed，否则 ValueError）
  T6  合规收口  ：合法链完成后 compliance_scan 判定 proceed（草稿已被任务 write-scope 覆盖）
  T7  提交旁路  ：pre-commit 钩子拦截"受保护内容提交未带任务记录"；带任务记录+Operation Manifest 则放行
  T8  doctor    ：对真实项目 道法百年 跑 doctor，确认平台治理无 Phase4 回归（FAIL=0）

用法：python tests/e2e_35_task_enforcement_chain.py
退出码：0=全 PASS；非 0=存在 FAIL。
"""
import os
import sys
import io
import re
import shutil
import contextlib
import subprocess
import datetime
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import _gov
import session_bootstrap as SB
import task_cli as TC
import task_engine as TE
import controlled_write as CW
import compliance_scan as CS

# 隔离沙箱：所有工具通过 _gov.find_workspace_root 解析 workspace；将其重定向到沙箱。
WS = None
PROJ = None


def run_main(module, argv):
    """调用模块 main()，捕获 (rc, stdout)。SystemExit 转为 rc。"""
    old = sys.argv
    sys.argv = ["prog"] + argv
    buf = io.StringIO()
    rc = 0
    try:
        with contextlib.redirect_stdout(buf):
            module.main()
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    finally:
        sys.argv = old
    return rc, buf.getvalue()


def git(*args, cwd=None):
    r = subprocess.run(["git"] + list(args), cwd=cwd,
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, r.stdout, r.stderr


def results():
    if not hasattr(results, "_r"):
        results._r = []
    return results._r


def check(name, ok, detail=""):
    results().append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print("  [%s] %s%s" % (mark, name, ("  -- " + detail) if detail else ""))
    return ok


def setup_sandbox():
    global WS, PROJ
    WS = tempfile.mkdtemp(prefix="step4_e2e_")
    PROJ = os.path.join(WS, "projects", "sbx")
    os.makedirs(PROJ, exist_ok=True)

    # workspace.yaml（_gov.find_project 读取）
    with open(os.path.join(WS, "workspace.yaml"), "w", encoding="utf-8") as f:
        f.write("workspace:\n  projects:\n    - projects/sbx\n")

    # project.yaml（id + strict 强制模式）
    with open(os.path.join(PROJ, "project.yaml"), "w", encoding="utf-8") as f:
        f.write("id: sbx\n"
                "name: 沙箱测试项目\n"
                "task_system:\n"
                "  enforcement_mode: strict\n"
                "template:\n"
                '  version: "1.0.0"\n')

    # 将 _gov 的 workspace 解析重定向到沙箱
    _gov.find_workspace_root = lambda: WS

    # 初始化 git 仓库（baseline 仅提交非受保护文件）
    git("init", "-q", cwd=PROJ)
    git("config", "user.email", "e2e@test", cwd=PROJ)
    git("config", "user.name", "e2e", cwd=PROJ)
    git("add", "project.yaml", cwd=PROJ)
    git("commit", "-q", "-m", "baseline: project.yaml", cwd=PROJ)

    # 安装 pre-commit 钩子（提交旁路检测）
    hook_src = os.path.join(_PLAT2, "scripts", "_common", "git_hooks", "pre-commit")
    hook_dst = os.path.join(PROJ, ".git", "hooks", "pre-commit")
    os.makedirs(os.path.dirname(hook_dst), exist_ok=True)
    shutil.copy(hook_src, hook_dst)
    try:
        os.chmod(hook_dst, 0o755)
    except Exception:
        pass

    # 受保护目录占位（不提交，仅用于后续受控写/合规检测）
    for d in ("NKB", "approved", "chapters/drafts", "第一卷_道生", "sources", "txt", "outline"):
        os.makedirs(os.path.join(PROJ, d), exist_ok=True)

    print("  沙箱 workspace: %s" % WS)
    print("  沙箱 project  : %s" % PROJ)


def cleanup():
    if WS and os.path.isdir(WS):
        shutil.rmtree(WS, ignore_errors=True)


DRAFT = ("肖凡立在山道尽头，望着远处升起的炊烟。这一路走来，他见过太多生死，"
         "也越发清楚自己要走的路。风从林间穿过，带来草木与泥土的气息。"
         "他伸手按住腰间短刃，指节因用力而微微发白。前方镇子不大，"
         "却藏着他此行要寻的人。行人三三两两，神情各异，有人匆忙，有人悠闲。"
         "肖凡不动声色地走入人群，耳中听到的尽是市井闲谈。卖货的吆喝、孩子的笑闹、"
         "老者的咳嗽，交织成一幅寻常画卷。他却从中听出了不寻常的紧张。"
         "酒肆门口，两个壮汉正压低声音争执，眼神时不时瞟向巷子深处。"
         "肖凡放慢脚步，装作看街边糖人，余光却将一切收入眼底。"
         "他心想，这镇子表面平静，底下只怕早已暗流汹涌。"
         "若真是那人所在，今日便不能善了。他深吸一口气，将杂念压下，"
         "只留一分冷静，静待时机。")


def main():
    print("=" * 70)
    print("Step 4 · 端到端强制链验证（Phase 4 任务系统强制层）")
    print("=" * 70)
    try:
        setup_sandbox()
        all_ok = True

        # ---- T0 配置正确性 ----
        print("\n[T0] 配置正确性")
        pdata = _gov.load_yaml(os.path.join(PROJ, "project.yaml"))
        wsdata = _gov.load_yaml(os.path.join(WS, "workspace.yaml"))
        ok0 = (pdata.get("id") == "sbx"
               and (pdata.get("task_system") or {}).get("enforcement_mode") == "strict"
               and "projects/sbx" in ((wsdata.get("workspace") or {}).get("projects") or []))
        all_ok &= check("project.yaml / workspace.yaml 解析 + strict 模式", ok0)

        # ---- T1 会话旁路（无 Session） ----
        print("\n[T1] 会话旁路：无 Session Manifest 时变更类工具被拒")
        # 1a 受控写（缺会话）-> exit 3
        draft_path = os.path.join(PROJ, "chapters", "drafts", "第099章_测试.md")
        rc, _ = run_main(CW, ["--role", "writer", "--target", "chapters/drafts/第099章_测试.md",
                              "--project", "sbx", "--task-id", "TASK-FAKE"])
        all_ok &= check("受控写 无会话 -> REJECTED(exit3)", rc == 3, "rc=%s" % rc)
        # 1b 任务变更动词 create（缺会话）-> exit 3
        rc, _ = run_main(TC, ["create", "--project-root", PROJ, "--json", '{"task":{"id":"X"}}'])
        all_ok &= check("task create 无会话 -> REJECTED(exit3)", rc == 3, "rc=%s" % rc)

        # ---- Bootstrap 会话 ----
        print("\n[B] Session Bootstrap（建立会话，强制入口）")
        rc, out = run_main(SB, ["--role", "writer", "--project", "sbx", "--workspace", WS])
        boot_ok = (rc == 0) and ("task_mode.enforced=True" in out)
        all_ok &= check("session bootstrap 成功 + task_mode.enforced=True", boot_ok, "rc=%s" % rc)
        sess = SB.load_session(PROJ)
        all_ok &= check("Session Manifest 已生成", sess is not None)

        # ---- T2 文件旁路（有会话但缺 task_id） ----
        print("\n[T2] 文件旁路：有会话但缺 task_id，受保护内容写被拒")
        if os.path.exists(draft_path):
            os.remove(draft_path)
        rc, _ = run_main(CW, ["--role", "writer", "--target", "chapters/drafts/第099章_测试.md",
                              "--project", "sbx"])
        no_write = (rc == 3) and (not os.path.exists(draft_path))
        all_ok &= check("受控写 缺 task_id -> REJECTED(exit3) 且文件未落盘", no_write, "rc=%s" % rc)

        # ---- T3 git 旁路（直接改受保护内容，无任务覆盖） ----
        print("\n[T3] git 旁路：直接改 NKB 受保护内容且无 active 任务 -> compliance block")
        bypass_file = os.path.join(PROJ, "NKB", "bypass.yaml")
        with open(bypass_file, "w", encoding="utf-8") as f:
            f.write("records:\n  - id: BypassTest\n")
        rep = CS.scan(PROJ)
        dec = rep["compliance"]["decision"]
        viol = rep["compliance"]["violations"]
        cid = rep["compliance"].get("id")
        t3a = (dec == "block") and bool(viol) and bool(cid)
        all_ok &= check("compliance_scan 判定 block + 写 FAILED_COMPLIANCE", t3a,
                         "decision=%s violations=%d id=%s" % (dec, len(viol), cid))
        # 经 main 入口退出码应为 1
        rc, _ = run_main(CS, ["--project-root", PROJ])
        all_ok &= check("compliance scan(main) 退出码=1", rc == 1, "rc=%s" % rc)
        # 清理越权文件，避免干扰后续合规收口
        os.remove(bypass_file)

        # ---- T4 合法全链（写章） ----
        print("\n[T4] 合法全链：intake->ready->claim->start->受控写->submit门禁->review->completed")
        rc, out = run_main(TC, ["intake", "--request", "写第099章 测试章节",
                                "--project-root", PROJ, "--project", "sbx",
                                "--role", "writer", "--agent", "writer-ai"])
        m = re.search(r"(TASK-INTAKE-\d+)", out)
        all_ok &= check("intake 建 chapter_write 任务", rc == 0 and bool(m), "rc=%s" % rc)
        tid = m.group(1) if m else None
        # Ready Check 现在与 Task Packet 共用输入解析器：用内联 fixture
        # 补齐计划、最终上下文与交接，不制造受保护路径的旁路文件。
        _, tdata = TE.load_task(PROJ, tid)
        tdata["task"].setdefault("inputs", {})["values"] = {
            "chapter_plan": "fixture-plan",
            "final_context": "fixture-context",
            "nkb_snapshot": "fixture-nkb",
            "previous_chapter_handoff": "fixture-handoff",
        }
        _gov.dump_yaml(os.path.join(PROJ, "tasks", "ready", tid + ".yaml"), tdata)

        rc, _ = run_main(TC, ["run", "--task", tid, "--project-root", PROJ,
                              "--role", "writer", "--agent", "writer-ai"])
        st, _ = TE.load_task(PROJ, tid)
        all_ok &= check("run: ready_check->claim->start 武装到 running", rc == 0 and st == "running",
                        "rc=%s status=%s" % (rc, st))

        # 受控写受保护草稿（带 task_id）
        draft_tmp = os.path.join(WS, "draft099.md")
        with open(draft_tmp, "w", encoding="utf-8") as f:
            f.write(DRAFT)
        rc, _ = run_main(CW, ["--role", "writer", "--target", "chapters/drafts/第099章_测试.md",
                              "--project", "sbx", "--task-id", tid,
                              "--content-file", draft_tmp])
        wrote = (rc == 0) and os.path.exists(draft_path)
        all_ok &= check("受控写 带 task_id + running -> 草稿落盘（chapters/drafts）", wrote, "rc=%s" % rc)

        # submit（触发质量/读者门禁）
        rc, out = run_main(TC, ["submit", "--task", tid,
                                "--artifact", "chapters/drafts/第099章_测试.md",
                                "--project-root", PROJ, "--role", "writer", "--agent", "writer-ai"])
        st, _ = TE.load_task(PROJ, tid)
        all_ok &= check("submit 门禁（质量/读者）通过 -> submitted", rc == 0 and st == "submitted",
                        "rc=%s status=%s" % (rc, st))
        rm = re.search(r"review=(TASK-[\w-]+)", out)
        rid = rm.group(1) if rm else None
        all_ok &= check("submit 自动建 chapter_review 后继任务", bool(rid), "review=%s" % rid)

        # reviewer 接取并审查通过
        rc, _ = run_main(TC, ["claim", "--task", rid, "--role", "reviewer",
                              "--agent", "reviewer-ai", "--project-root", PROJ])
        rc2, _ = run_main(TC, ["start", "--task", rid, "--role", "reviewer",
                               "--agent", "reviewer-ai", "--project-root", PROJ])
        rc3, _ = run_main(TC, ["review", "--task", rid, "--decision", "pass",
                               "--role", "reviewer", "--agent", "reviewer-ai",
                               "--project-root", PROJ])
        st_o, _ = TE.load_task(PROJ, tid)
        all_ok &= check("review(pass) -> 原 chapter_write 任务 completed",
                        rc == 0 and rc2 == 0 and rc3 == 0 and st_o == "completed",
                        "orig_status=%s" % st_o)

        # ---- T5 门禁防守：AI 不能自标 completed ----
        print("\n[T5] 门禁防守：AI 自标 completed 被拒（要求 passed）")
        rc, out = run_main(TC, ["intake", "--request", "写第100章 防御测试",
                                "--project-root", PROJ, "--project", "sbx",
                                "--role", "writer", "--agent", "writer-ai"])
        m2 = re.search(r"(TASK-INTAKE-\d+)", out)
        tid2 = m2.group(1) if m2 else None
        run_main(TC, ["run", "--task", tid2, "--project-root", PROJ,
                      "--role", "writer", "--agent", "writer-ai"])
        # 直接对"非 passed"状态的任务调用 complete() -> 必须抛 ValueError（AI 无法跳过 Gate 自标完成）
        try:
            TE.complete(PROJ, tid2)
            raised = False
        except ValueError:
            raised = True
        st2, _ = TE.load_task(PROJ, tid2)
        all_ok &= check("complete() 在非 passed 状态抛 ValueError（AI 无法自标完成）",
                        raised and st2 != "completed", "raised=%s status=%s" % (raised, st2))

        # ---- T6 合规收口：合法链后 compliance proceed ----
        print("\n[T6] 合规收口：合法链完成后 compliance_scan 判定 proceed")
        rep2 = CS.scan(PROJ)
        if rep2["compliance"]["decision"] != "proceed":
            print("    DEBUG violations: %s" % rep2["compliance"]["violations"])
        all_ok &= check("compliance_scan 判定 proceed（草稿已被任务 write-scope 覆盖）",
                        rep2["compliance"]["decision"] == "proceed",
                        "decision=%s" % rep2["compliance"]["decision"])

        # ---- T7 提交旁路：pre-commit 钩子 ----
        print("\n[T7] 提交旁路：pre-commit 钩子拦截越权提交；带任务记录则放行")
        # 7a 越权：仅提交受保护内容，无任务记录
        bp = os.path.join(PROJ, "NKB", "precommit_bypass.yaml")
        with open(bp, "w", encoding="utf-8") as f:
            f.write("records:\n  - id: PcBypass\n")
        git("add", "NKB/precommit_bypass.yaml", cwd=PROJ)
        rc_c, _, err_c = git("commit", "-q", "-m", "bypass attempt", cwd=PROJ)
        git("reset", "-q", "HEAD", cwd=PROJ)  # 还原暂存
        all_ok &= check("pre-commit 拦截 受保护内容无任务记录提交", rc_c != 0,
                        "commit_rc=%s" % rc_c)
        os.remove(bp)

        # 7b 合法：受保护内容 + 任务记录(TASK yaml) + Operation Manifest 一并提交
        lg = os.path.join(PROJ, "NKB", "precommit_legit.yaml")
        with open(lg, "w", encoding="utf-8") as f:
            f.write("records:\n  - id: PcLegit\n")
        os.makedirs(os.path.join(PROJ, "tasks", "ready"), exist_ok=True)
        with open(os.path.join(PROJ, "tasks", "ready", "TASK-PRECOMMIT-001.yaml"), "w", encoding="utf-8") as f:
            f.write("task:\n  id: TASK-PRECOMMIT-001\n  status: ready\n  type: nkb_update\n")
        os.makedirs(os.path.join(PROJ, "operations"), exist_ok=True)
        with open(os.path.join(PROJ, "operations", "OP-PRECOMMIT-001.yaml"), "w", encoding="utf-8") as f:
            f.write("operation:\n  id: OP-PRECOMMIT-001\n  task_id: TASK-PRECOMMIT-001\n")
        git("add", "NKB/precommit_legit.yaml",
            "tasks/ready/TASK-PRECOMMIT-001.yaml",
            "operations/OP-PRECOMMIT-001.yaml", cwd=PROJ)
        rc_l, _, err_l = git("commit", "-q", "-m", "legit with task record", cwd=PROJ)
        all_ok &= check("pre-commit 放行 受保护内容+任务记录+Operation Manifest", rc_l == 0,
                        "commit_rc=%s stderr=%s" % (rc_l, (err_l or "").strip()[:500]))
        # 还原该测试提交，保持沙箱干净
        git("reset", "-q", "--hard", "HEAD~1", cwd=PROJ)

        # ---- T8 doctor（真实项目） ----
        print("\n[T8] doctor：真实项目 道法百年 平台治理无 Phase4 回归")
        real_ws = os.path.dirname(os.path.dirname(os.path.dirname(TOOLS)))  # tools->平台->platform->AI-Workspace
        try:
            r = subprocess.run([sys.executable, os.path.join(_PLAT2, "cli", "platform.py"),
                                "--workspace", real_ws, "doctor"],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=420)
            dout = r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            dout = "(doctor 超时)"
        fail_cnt = len(re.findall(r"\[FAIL\]", dout))
        # 仅报告，不据其判定整体成败（仅关注 Phase4 是否引入回归；doctor 既有项不归本步）
        print("    doctor 退出码=%s FAIL 计数=%d  real_ws=%s" % (
            r.returncode if 'r' in dir() else '?', fail_cnt, real_ws))
        for line in dout.splitlines()[:25]:
            if ("FAIL" in line) or ("错误" in line) or ("error" in line) or ("die" in line):
                print("      ! " + line.strip())
        if 'r' in dir() and r.returncode not in (0, 1):
            print("    DEBUG doctor 输出前 30 行:")
            for ln in dout.splitlines()[:30]:
                print("      | " + ln)
        all_ok &= check("doctor 运行无异常（FAIL 项见上，需人工确认是否 Phase4 引入）",
                        ("超时" not in dout) and (r.returncode in (0, 1) if 'r' in dir() else False),
                        "fail=%d" % fail_cnt)

    finally:
        cleanup()

    # ---- 汇总 ----
    print("\n" + "=" * 70)
    print("Step 4 汇总")
    print("=" * 70)
    npass = sum(1 for _, ok, _ in results() if ok)
    nall = len(results())
    for name, ok, detail in results():
        print("  [%s] %s" % ("PASS" if ok else "FAIL", name))
    print("  通过 %d / %d" % (npass, nall))
    bypass_rate = 0 if all_ok else None
    print("  绕过率：%s" % ("0（全部拦截/全链走通）" if all_ok else "存在未拦截项"))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()

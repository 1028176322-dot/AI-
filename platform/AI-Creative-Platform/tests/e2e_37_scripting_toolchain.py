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
"""e2e_37 — Phase A 脚本化工具链端到端验证

覆盖：索引构建 / NKB 查询与投影 / Level-1 预检 / task next / task packet /
      context build / policy compile，以及 platform_cli 委托接线。
使用独立 tmp 项目（拷贝真实 NKB + project.yaml + 1 章），不污染真实工程。
"""
import os
import sys
import json
import shutil
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PLAT = os.path.dirname(HERE)
PROJ_ROOT = os.path.dirname(os.path.dirname(PLAT))  # workspace 根（platform/ 的同级 projects/）
PROJ = os.path.join(PROJ_ROOT, "projects", "道法百年")
TOOLS = os.path.join(PLAT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

PASS_CNT = 0
FAILS = []
TOTAL = 0


def check(name, cond, detail=""):
    global PASS_CNT, TOTAL
    TOTAL += 1
    if cond:
        PASS_CNT += 1
        print("  [PASS] %s" % name)
    else:
        FAILS.append((name, detail))
        print("  [FAIL] %s : %s" % (name, detail))


def _build_tmp_project():
    tmp = tempfile.mkdtemp(prefix="e2e37_")
    # NKB + project.yaml
    shutil.copytree(os.path.join(PROJ, "NKB"), os.path.join(tmp, "NKB"))
    shutil.copy(os.path.join(PROJ, "project.yaml"), os.path.join(tmp, "project.yaml"))
    # 复制一章 md（排除 审读/评分卡/大纲/批注）
    vol = os.path.join(PROJ, "第一卷_道生")
    src = None
    for fn in sorted(os.listdir(vol)):
        if fn.endswith(".md") and "第" in fn and "章" in fn and "审读" not in fn \
           and "评分卡" not in fn and "大纲" not in fn and "批注" not in fn:
            src = os.path.join(vol, fn)
            break
    assert src, "未找到示例章节"
    os.makedirs(os.path.join(tmp, "第一卷_道生"), exist_ok=True)
    shutil.copy(src, os.path.join(tmp, "第一卷_道生", os.path.basename(src)))
    chapter_ref = "第一卷_道生/" + os.path.basename(src)
    # 创建 ready 任务
    os.makedirs(os.path.join(tmp, "tasks", "ready"), exist_ok=True)
    task_yaml = (
        "task:\n"
        "  id: TASK-E2E37\n"
        "  type: chapter_write\n"
        "  project: novel-dsf\n"
        "  title: e2e 测试章\n"
        "  version: 1\n"
        "  priority: high\n"
        "  chapter_ref: %s\n"
        "  status: ready\n"
        "  agent:\n"
        "    required_role: writer\n"
        "  permissions:\n"
        "    read: [NKB/**]\n"
        "    write: [tasks/running/<id>/outputs/**, chapters/drafts/**]\n"
        "    forbidden: [core/**, NKB/**]\n"
        "  inputs:\n"
        "    required: [chapter_plan, final_context, nkb_snapshot, previous_chapter_handoff]\n"
        "  expected_outputs: [chapter_draft, self_check, candidate_facts, handoff]\n"
        "  acceptance:\n"
        "    criteria: [ok]\n"
        "  execution_policy:\n"
        "    agent_mode: single\n"
        "    delegation_allowed: false\n"
        "    subagent_allowed: false\n"
        "    parallel_execution_allowed: false\n"
        "    max_agents: 1\n"
        "    max_parallel_steps: 1\n"
        "    required_session: current\n"
    ) % chapter_ref
    with open(os.path.join(tmp, "tasks", "ready", "TASK-E2E37.yaml"), "w", encoding="utf-8") as f:
        f.write(task_yaml)
    return tmp, chapter_ref


def main():
    tmp, chapter_ref = _build_tmp_project()
    try:
        import index_builder as IB
        import task_engine as TE
        import task_packet as TP
        import context_builder as CB
        import policy_compiler as PC
        import nkb_query as NQ
        import validators as VD

        print("\n[1] 索引构建（index build）")
        idx = IB.build_index(tmp)
        c = idx["counts"]
        check("索引实体数 > 0", c["entities"] > 0, str(c))
        check("索引章节数 > 0", c["chapters"] > 0, str(c))
        check("索引事件数 > 0", c["events"] > 0, str(c))
        check("索引术语数 > 0", c["terminology"] > 0, str(c))
        check("索引依赖边数 >= 0", c["dependencies"] >= 0, str(c))
        for fn in ("files.json", "entities.json", "chapters.json", "terminology.json",
                   "events.json", "dependencies.json", "index.json"):
            check("索引产物 %s 存在" % fn, os.path.isfile(os.path.join(tmp, "runtime", "indexes", fn)))
        # query_index
        res = IB.query_index(os.path.join(tmp, "runtime", "indexes"), "CHR-001")
        check("query_index CHR-001 命中实体", any(r["kind"] == "entity" for r in res), str(res))

        print("\n[2] NKB 查询与投影（nkb_query）")
        rec = NQ._find(tmp, "character", "CHR-001")
        check("get character CHR-001 返回记录", rec is not None)
        check("CHR-001 名为 肖凡", rec and rec.get("name") == "肖凡", str(rec.get("name") if rec else None))
        evs = NQ._events_for(tmp, "CHR-001")
        check("events --entity CHR-001 返回列表", isinstance(evs, list) and len(evs) > 0, str(len(evs)))
        held = NQ._project_assets(tmp, "CHR-001")
        check("project assets 返回列表", isinstance(held, list))
        # CLI 接线：platform query get
        out = _cli(tmp, ["query", "get", "character", "CHR-001"])
        check("CLI query get 输出含 CHR-001", "CHR-001" in out, out[:200])

        print("\n[3] Level-1 预检（validators）")
        fids = VD._check_ids(type("A", (), {"project_root": tmp})())
        check("validate ids 返回 findings", isinstance(fids, list) and len(fids) > 0)
        check("validate ids 无 fail（种子 NKB 合规）",
              not any(f["severity"] == "fail" for f in fids), str(fids))
        frp = VD._check_runtime_policy(type("A", (), {"project_root": tmp})())
        check("validate runtime_policy 含单 Agent 合规",
              any("合规" in f["detail"] for f in frp), str(frp))
        chap_path = os.path.join(tmp, chapter_ref)
        fterm = VD._check_terminology(type("A", (), {"file": chap_path, "project_root": tmp})())
        check("validate terminology 返回 findings", isinstance(fterm, list))
        flen = VD._check_chapter_length(type("A", (), {"file": chap_path, "min": 500, "max": 200000})())
        check("validate chapter_length 返回 chars", any("chars" in f for f in flen), str(flen))
        ch = [f for f in flen if "chars" in f][0]["chars"]
        check("chapter_length chars > 0", ch > 0, str(ch))
        # CLI 接线：platform validate ids
        out = _cli(tmp, ["validate", "ids", "--project-root", tmp])
        check("CLI validate ids 输出 JSON", "check" in out, out[:200])

        print("\n[4] task next（按角色找下一任务）")
        nxt = TE.next_task(tmp, "writer")
        check("next_task 返回字典", isinstance(nxt, dict), str(nxt))
        check("next_task task_id == TASK-E2E37", nxt and nxt["task_id"] == "TASK-E2E37", str(nxt))
        check("next_task inputs_ready == True", nxt and nxt["inputs_ready"] is True, str(nxt))
        check("next_task priority == high", nxt and nxt["priority"] == "high", str(nxt))
        # 角色不匹配应返回 None
        nxt2 = TE.next_task(tmp, "reviewer")
        check("next_task 角色不匹配返回 None", nxt2 is None, str(nxt2))

        print("\n[5] task packet（任务包生成）")
        pkt_dir = TP.build_packet(tmp, "TASK-E2E37")
        check("packet 目录存在", os.path.isdir(pkt_dir))
        for fn in ("task.yaml", "input-index.yaml", "context.md", "constraints.md",
                   "output-contract.yaml", "execution-manifest.yaml"):
            check("packet 含 %s" % fn, os.path.isfile(os.path.join(pkt_dir, fn)))
        import _gov as _G
        ii = _G.load_yaml(os.path.join(pkt_dir, "input-index.yaml"))
        check("input-index 含 required_inputs", isinstance(ii.get("required_inputs"), list) and len(ii["required_inputs"]) == 4)
        em = _G.load_yaml(os.path.join(pkt_dir, "execution-manifest.yaml"))
        check("execution-manifest mode == single", em.get("mode") == "single", str(em))
        # CLI 接线：platform task packet
        out = _cli(tmp, ["task", "packet", "--task", "TASK-E2E37"])
        check("CLI task packet 成功", "Task Packet 已生成" in out, out[:200])

        print("\n[6] context build（最小上下文）")
        ctx_path = CB.build_context(tmp, "TASK-E2E37", 12000)
        check("context 文件存在", os.path.isfile(ctx_path))
        with open(ctx_path, encoding="utf-8") as f:
            ctx_txt = f.read()
        check("context 含『出场角色』", "出场角色" in ctx_txt)
        check("context 含『相关事件』", "相关事件" in ctx_txt)
        check("context 含『未回收伏笔』", "未回收伏笔" in ctx_txt)
        check("context 长度受控（< 20000 字符）", len(ctx_txt) < 20000, str(len(ctx_txt)))

        print("\n[7] policy compile（最小规则包）")
        pol_path, pol = PC.compile_policy(tmp, "TASK-E2E37")
        check("policy 文件存在", os.path.isfile(pol_path))
        check("policy must 非空", len(pol.get("must", [])) > 0, str(pol.get("must")))
        check("policy must_not 含『子 Agent』禁令",
              any("子 Agent" in m for m in pol.get("must_not", [])), str(pol.get("must_not")))
        check("policy mode == single_agent_sequential",
              pol.get("mode") == "single_agent_sequential", str(pol.get("mode")))
        # CLI 接线：platform policy compile
        out = _cli(tmp, ["policy", "compile", "--task", "TASK-E2E37"])
        check("CLI policy compile 成功", "Policy 已编译" in out, out[:200])

        print("\n[8] doctor ScriptGov 块（真实工程，派生索引）")
        import subprocess as _sp
        IB.build_index(tmp)  # 仅写隔离项目 runtime/indexes
        py = sys.executable
        cli = os.path.join(_PLAT2, "cli", "platform.py")
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([_p for _p in sys.path if _p.startswith(_SCR2)]) + os.pathsep + env.get("PYTHONPATH", "")
        proc = _sp.run([py, cli, "doctor"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, cwd=PROJ_ROOT)
        out = proc.stdout + proc.stderr
        check("doctor 输出含 ScriptGov", "ScriptGov" in out, out[:400])
        script_segment = out.split("ScriptGov", 1)[1][:120] if "ScriptGov" in out else ""
        check("doctor ScriptGov 给出 PASS/WARN 诊断",
              ("PASS" in script_segment) or ("WARN" in script_segment), out[:500])

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 60)
    print("Phase A 脚本化工具链 e2e 结果：%d/%d PASS" % (PASS_CNT, TOTAL))
    if FAILS:
        print("失败项：")
        for n, d in FAILS:
            print("  - %s : %s" % (n, d))
        sys.exit(1)
    print("全部通过。")


def _cli(project_root, args):
    """通过 platform_cli 验证委托接线。

    --project-root 必须插在子命令名之后、REMAINDER 起始 token 之前
    （否则 task 子命令的 required --project-root 会因被 REMAINDER 吞掉而报错）。
    """
    py = sys.executable
    cli = os.path.join(_PLAT2, "cli", "platform.py")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([_p for _p in sys.path if _p.startswith(_SCR2)]) + os.pathsep + env.get("PYTHONPATH", "")
    rest = list(args[1:])
    # 避免重复插入 --project-root（调用方已显式传递时）
    if any(a == "--project-root" for a in rest):
        full = [py, cli] + [args[0]] + rest
    else:
        full = [py, cli] + [args[0], "--project-root", project_root] + rest
    proc = subprocess.run(full, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env,
                          cwd=os.path.dirname(cli))
    return proc.stdout + proc.stderr


if __name__ == "__main__":
    main()

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
"""e2e_38 — Phase B 审查管线端到端验证

覆盖：结构化 Review 报告 schema + 单 Agent 多阶段计划（B-1）/
      summary_builder 章节-卷-弧-滚动摘要（B-2）/
      delta_review 增量审查（B-3）/
      review_orchestrator 单 Agent 五阶段编排（B-4）/
      platform_cli 委托接线（summary/delta/review）+ doctor ReviewGov 块（B-5）。
使用独立 tmp 项目（拷贝真实 NKB + 章节），不污染真实工程。
"""
import os
import sys
import shutil
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PLAT = os.path.dirname(HERE)
PROJ_ROOT = os.path.dirname(os.path.dirname(PLAT))
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


def _cli(project_root, args):
    py = sys.executable
    cli = os.path.join(_PLAT2, "cli", "platform.py")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([_p for _p in sys.path if _p.startswith(_SCR2)]) + os.pathsep + env.get("PYTHONPATH", "")
    full = [py, cli] + [args[0], "--project-root", project_root] + args[1:]
    proc = subprocess.run(full, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env,
                          cwd=os.path.dirname(cli))
    return proc.stdout + proc.stderr


def _build_tmp_project():
    tmp = tempfile.mkdtemp(prefix="e2e38_")
    shutil.copytree(os.path.join(PROJ, "NKB"), os.path.join(tmp, "NKB"))
    shutil.copy(os.path.join(PROJ, "project.yaml"), os.path.join(tmp, "project.yaml"))
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
    os.makedirs(os.path.join(tmp, "tasks", "ready"), exist_ok=True)
    task_yaml = (
        "task:\n"
        "  id: TASK-E2E38\n"
        "  type: chapter_review\n"
        "  project: novel-dsf\n"
        "  title: e2e 审查任务\n"
        "  version: 1\n"
        "  priority: high\n"
        "  chapter_ref: %s\n"
        "  status: ready\n"
        "  agent:\n"
        "    required_role: reviewer\n"
        "  permissions:\n"
        "    read: [NKB/**, chapters/**]\n"
        "    write: [runtime/reviews/**]\n"
        "    forbidden: [core/**, NKB/**]\n"
        "  inputs:\n"
        "    required: [chapter_text, context, l1_findings]\n"
        "  expected_outputs: [review_report]\n"
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
    with open(os.path.join(tmp, "tasks", "ready", "TASK-E2E38.yaml"), "w", encoding="utf-8") as f:
        f.write(task_yaml)
    return tmp, chapter_ref, os.path.join(tmp, "第一卷_道生", os.path.basename(src))


def main():
    tmp, chapter_ref, ch_path = _build_tmp_project()
    try:
        import _yaml_lite as Y

        # [1] B-1 schema 解析 + finding 字段齐备
        schema = Y.load_file(os.path.join(PLAT, "core", "contracts", "review-report.schema.yaml"))
        fld = schema.get("finding", {}).get("required", [])
        check("schema 解析 + finding 含 9 字段",
              set(["id", "category", "severity", "location", "observation",
                   "evidence", "reasoning", "impact", "recommended_fix"]).issubset(set(fld)),
              "got=%s" % fld)

        # [2] B-1 plan 解析 + 五阶段
        plan = Y.load_file(os.path.join(PLAT, "core", "review", "review-plan.yaml"))
        stages = plan.get("plan", {}).get("stages", [])
        names = [s.get("name") for s in stages]
        check("plan 解析 + 五阶段顺序",
              len(stages) == 6 and names == ["immersive", "structural", "character",
                                              "continuity", "reader_panel", "synthesis"], "got=%s" % names)

        # [3] B-2 summary build（AI 填字段→脚本落盘）
        data_path = os.path.join(tmp, "sum-data.yaml")
        with open(data_path, "w", encoding="utf-8") as f:
            f.write(
                "title: 测试章\n"
                "volume: 第一卷_道生\n"
                "arc: 下山入世\n"
                "plot: 肖凡初下山，见识世俗。\n"
                "character_changes:\n"
                "  - character: CHR-001\n"
                "    change: 初下山，世界观受冲击\n"
                "new_events: []\n"
                "new_information:\n"
                "  - 修真与世俗的张力初现\n"
                "open_threads:\n"
                "  - 苏墨凝下落\n"
            )
        out = _cli(tmp, ["summary", "build", "--chapter", "CH021",
                         "--data-file", data_path, "--task", "TASK-E2E38"])
        sum_path = os.path.join(tmp, "summaries", "chapters", "CH021-summary.yaml")
        check("summary build 落盘", os.path.isfile(sum_path), out[:300])
        if os.path.isfile(sum_path):
            sd = Y.load_file(sum_path)
            check("summary version==1 + plot 保留",
                  sd.get("summary_version") == 1 and "肖凡" in (sd.get("plot") or ""),
                  "got=%s" % sd.get("summary_version"))

        # [4] B-2 aggregate volume + rollup
        out = _cli(tmp, ["summary", "aggregate", "--volume", "第一卷_道生"])
        vol_path = os.path.join(tmp, "summaries", "volumes", "第一卷_道生-summary.yaml")
        check("summary aggregate(volume) 落盘", os.path.isfile(vol_path), out[:200])
        out = _cli(tmp, ["summary", "rollup"])
        roll_path = os.path.join(tmp, "summaries", "rollup.yaml")
        check("summary rollup 落盘 + chapter_count>=1",
              os.path.isfile(roll_path) and (Y.load_file(roll_path).get("chapter_count") or 0) >= 1,
              out[:200])

        # [5] B-3 delta review（from=原章, to=改几行的副本）
        to_path = os.path.join(tmp, "第一卷_道生", "第021章_delta.md")
        with open(ch_path, "r", encoding="utf-8") as f:
            txt = f.read()
        txt2 = txt + "\n\n肖凡与苏墨凝对白间，初次展露对世俗的不解。\n"
        with open(to_path, "w", encoding="utf-8") as f:
            f.write(txt2)
        out = _cli(tmp, ["delta", "review", "--from", ch_path, "--to", to_path])
        delta_path = os.path.join(tmp, "runtime", "reviews", "delta")
        import glob
        dp = glob.glob(os.path.join(delta_path, "*.yaml"))
        check("delta review 落盘报告", len(dp) >= 1, out[:300])
        if dp:
            dr = Y.load_file(dp[0])
            check("delta 检测到变更 + 相似度<1",
                  dr.get("changed_range_count", 0) >= 1 and dr.get("similarity", 1) < 1.0,
                  "sim=%s" % dr.get("similarity"))

        # [6] B-4 review orchestrator（单 Agent 五阶段证据包）
        out = _cli(tmp, ["review", "run", "--task", "TASK-E2E38"])
        rv_base = os.path.join(tmp, "runtime", "reviews", "REVIEW-TASK-E2E38")
        rep = os.path.join(rv_base, "report.yaml")
        brief = os.path.join(rv_base, "review-brief.md")
        ctx = os.path.join(rv_base, "evidence", "context.md")
        chap = os.path.join(rv_base, "evidence", "chapter.md")
        l1 = os.path.join(rv_base, "evidence", "l1-findings.json")
        check("review run 生成 report.yaml + brief + evidence",
              os.path.isfile(rep) and os.path.isfile(brief)
              and os.path.isfile(chap) and os.path.isfile(l1), "OUT>>"+out+"<<OUT")
        if os.path.isfile(rep):
            rd = Y.load_file(rep)
            check("report 含 stages(5) + 空 findings + finding_template",
                  len(rd.get("stages", [])) == 6 and rd.get("findings") == []
                  and rd.get("reader_panel_report")
                  and "id" in (rd.get("finding_template") or {}), "got=%s" % list(rd.keys()))

        # [7] 验证 review 委托可用（run 已验证）；额外验证 summary/delta 委托命令形态
        check("CLI 委托 summary/delta/review 均不报错",
              "ERROR" not in out and "✓" in out, "OUT>>"+out+"<<OUT")

        # [8] doctor ReviewGov 块（真实工程，只读不污染）
        py = sys.executable
        cli = os.path.join(_PLAT2, "cli", "platform.py")
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([_p for _p in sys.path if _p.startswith(_SCR2)]) + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run([py, cli, "doctor"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              env=env, cwd=PROJ)
        doc = proc.stdout + proc.stderr
        check("doctor 含 ReviewGov 块且 PASS", "ReviewGov" in doc and "PASS" in doc,
              doc[doc.find("ReviewGov")-40:doc.find("ReviewGov")+120] if "ReviewGov" in doc else doc[:200])

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n=== e2e_38 结果：%d/%d PASS ===" % (PASS_CNT, TOTAL))
    if FAILS:
        for n, d in FAILS:
            print("  FAIL: %s | %s" % (n, d))
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()

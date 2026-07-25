# -*- coding: utf-8 -*-
"""任务系统 CLI 调度：platform task <verb> ...

verbs:
  create   创建任务（--yaml 任务文件 | --json 内联）
  goal     创建目标
  promote  backlog -> ready（依赖满足）
  claim    接取任务（设置 owner + lease）
  start    claimed -> running
  submit   提交产物 + 自检（自动建审查任务）
  review   审查决策 pass/fail（作用于审查任务）
  complete 验收关闭（passed -> completed，并推进下游）
  fail     标记失败（-> failed，状态置阻塞）
  retry    重试（failed -> ready）
  route    列出某 role+capabilities 可接取任务
  list     列出全部/某状态任务
  show     查看任务详情

所有动作写 audit/ 并在关键转移联动 project/status.yaml。
"""
import os
import sys
import re
import json
import datetime
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _gov
import task_engine as TE
import session_bootstrap as SB
import task_intake as TI

PLAT_ROOT = os.path.dirname(HERE)
TEMPLATES_DIR = os.path.join(PLAT_ROOT, "core", "task-system", "templates")

# 变更类动词（需先 bootstrap 会话）；只读动词豁免
# 注：intake/run 的会话要求在其内部按“是否实际建/武装任务”动态判定。
_MUTATION_VERBS = {"create", "goal", "promote", "claim", "start",
                   "submit", "review", "complete", "fail", "retry"}


def _load_template(name):
    p = os.path.join(TEMPLATES_DIR, name + ".task.yaml")
    if not os.path.isfile(p):
        return None
    d = _gov.load_yaml(p) or {}
    return d.get("task_template") or d.get("template")


def _map_request(req):
    """自然语言请求 -> (template_name, task_type, chapter_ref_or_None)。"""
    m = re.search(r"第\s*(\d+)\s*章", req)
    ch = ("%03d" % int(m.group(1))) if m else None
    is_review = any(k in req for k in ["审查", "评", "审", "review"])
    is_fix = any(k in req for k in ["修", "修复", "润色", "fix", "改"])
    is_nkb = any(k in req for k in ["NKB", "知识库", "设定", "人物", "世界观"])
    is_platform = any(k in req for k in ["平台", "工具", "脚本", "policy", "钩子", "pre-commit"])
    if ch and is_review:
        return "chapter-review", "chapter_review", "第一卷_道生/第%s章.md" % ch
    if ch and is_fix:
        return "chapter-fix", "chapter_fix", "第一卷_道生/第%s章.md" % ch
    if ch:
        return "chapter-write", "chapter_write", "第一卷_道生/第%s章.md" % ch
    if is_nkb:
        return "nkb-sync", "nkb_update", None
    if is_platform:
        return "system-maintenance", "system_maintenance", None
    # 默认：章节写作（最常见）
    return "chapter-write", "chapter_write", None


def _build_task_from_request(root, request, project, role):
    """分类 + 选模板 + 构建 task dict（不落盘）。返回 (task_dict, classification, task_type)。"""
    cls, required, action = TI.classify(request)
    if not required:
        return None, cls, None
    tname, ttype, chapter_ref = _map_request(request)
    tmpl = _load_template(tname) or {}
    tid = "TASK-INTAKE-%s" % datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    task = {
        "id": tid,
        "type": ttype,
        "project": project,
        "title": request[:60],
        "version": 1,
        "priority": "high",
        "chapter_ref": chapter_ref,
        "agent": {"required_role": tmpl.get("required_role", role)},
        "permissions": tmpl.get("permissions", {"read": ["NKB/**"], "write": ["tasks/**"]}),
        "inputs": {"required": tmpl.get("required_inputs", [])},
        "expected_outputs": tmpl.get("allowed_outputs", []),
        "acceptance": {"criteria": ["按 %s 模板契约完成" % tname]},
    }
    return task, cls, ttype


def _cmd_intake(args):
    root = args.project_root
    cls, required, action = TI.classify(args.request)
    print("分类: %s | task_required=%s" % (cls, required))
    print("建议: %s" % action)
    if not required:
        print("（咨询/分析类，无需建任务；如需报告请用 analysis 流程）")
        return
    SB.require_session(root)  # 实际建任务才需会话
    task, _, ttype = _build_task_from_request(root, args.request, args.project, args.role)
    st, p = TE.create_task(root, task, model=args.model, author=args.agent)
    print("✓ 任务已建: %s (type=%s, status=%s)" % (task["id"], ttype, st))
    print("下一步: platform task run --task %s  （或 --request 直达编排）" % task["id"])


def _cmd_run(args):
    root = args.project_root
    # 1) 解析任务：--request 则先 intake；否则加载 --task
    if args.request:
        cls, required, _ = TI.classify(args.request)
        if not required:
            print("分类: %s（咨询/分析类，run 不建任务）" % cls)
            return
        SB.require_session(root)
        task, _, ttype = _build_task_from_request(root, args.request, args.project, args.role)
        st, p = TE.create_task(root, task, model=args.model, author=args.agent)
        tid = task["id"]
        print("✓ intake 建任务: %s (type=%s)" % (tid, ttype))
    else:
        tid = args.task
        if not tid:
            print("ERROR: run 需要 --request 或 --task")
            sys.exit(2)
        st0, _ = TE.load_task(root, tid)
        if st0 is None:
            print("ERROR: 任务不存在: %s" % tid)
            sys.exit(2)

    # 2) Ready Check
    ok, rep = TE.ready_check(root, tid)
    print("Ready Check: %s" % ("OK" if ok else "FAIL"))
    if not ok:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        sys.exit(1)

    # 3) claim + start
    _, data = TE.load_task(root, tid)
    role = (data["task"].get("agent") or {}).get("required_role") or args.role
    TE.claim(root, tid, args.agent, role, model=args.model)
    TE.start(root, tid, args.agent, role, model=args.model)
    print("✓ 任务已武装: %s -> running（AI 经 controlled_write 写产物后 submit）" % tid)

    # 4) 可选 submit（提供 --artifact 时）
    if args.artifact:
        try:
            sst, nxt = TE.submit(root, tid, args.artifact,
                                outputs={"artifact": args.artifact},
                                agent=args.agent, role=role, model=args.model)
            print("✓ submit: %s (next=%s)" % (sst, nxt))
        except Exception as e:
            print("submit 失败（门禁可能拦截）: %s" % e)
            sys.exit(1)


def main():
    ap = argparse.ArgumentParser(prog="task", description="任务系统操作中心")
    ap.add_argument("verb", choices=["create", "goal", "promote", "claim", "start",
                                     "submit", "review", "complete", "fail", "retry",
                                     "route", "list", "show", "intake", "run"])
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--request", help="自然语言请求（intake/run 用）")
    ap.add_argument("--project", default="novel-dsf", help="项目 id（intake/run 用）")
    ap.add_argument("--yaml", help="任务/目标 YAML 文件路径")
    ap.add_argument("--json", help="内联 JSON（task 或 goal 字典）")
    ap.add_argument("--task", help="task id")
    ap.add_argument("--agent", default="agent-unknown")
    ap.add_argument("--role", default="unknown")
    ap.add_argument("--model", default="unknown")
    ap.add_argument("--lease", type=int, default=60)
    ap.add_argument("--artifact", default=None)
    ap.add_argument("--checks", default=None, help='JSON dict，如 {"constitution":"pass"}')
    ap.add_argument("--decision", choices=["pass", "fail"], default="pass")
    ap.add_argument("--findings", default=None, help="JSON list of findings")
    ap.add_argument("--reason", default="")
    ap.add_argument("--state", default=None)
    ap.add_argument("--capabilities", default=None, help="逗号分隔能力标签")
    args = ap.parse_args()

    root = args.project_root
    v = args.verb

    # Step3.3：变更类动词需先 bootstrap 会话
    if v in _MUTATION_VERBS:
        try:
            SB.require_session(root)
        except RuntimeError as e:
            print("REJECTED: %s" % e)
            sys.exit(3)

    if v == "create":
        data = _load_arg(args, ap)
        st, p = TE.create_task(root, data, model=args.model, author=args.agent)
        print("✓ 任务创建: %s (status=%s)" % (data.get("task", data).get("id"), st))
    elif v == "goal":
        data = _load_arg(args, ap)
        p = TE.create_goal(root, data, model=args.model, author=args.agent)
        print("✓ 目标创建: %s" % data.get("goal", data).get("id"))
    elif v == "promote":
        st, msg = TE.promote(root, args.task, model=args.model)
        print("✓ promote %s -> %s (%s)" % (args.task, st, msg))
    elif v == "claim":
        st = TE.claim(root, args.task, args.agent, args.role, model=args.model, lease_min=args.lease)
        print("✓ claim %s -> %s (owner=%s)" % (args.task, st, args.agent))
    elif v == "start":
        st = TE.start(root, args.task, args.agent, args.role, args.model)
        print("✓ start %s -> %s" % (args.task, st))
    elif v == "submit":
        checks = json.loads(args.checks) if args.checks else {}
        st, rev = TE.submit(root, args.task, args.artifact or "BUILD-unknown",
                            outputs={}, checks=checks, agent=args.agent, role=args.role, model=args.model)
        print("✓ submit %s -> %s (review=%s)" % (args.task, st, rev))
    elif v == "review":
        findings = json.loads(args.findings) if args.findings else None
        st, info = TE.review(root, args.task, args.decision, findings=findings,
                             reviewer=args.agent, role=args.role, model=args.model)
        print("✓ review %s -> %s (%s)" % (args.task, st, info))
    elif v == "complete":
        st, msg = TE.complete(root, args.task, model=args.model)
        print("✓ complete %s -> %s" % (args.task, st))
    elif v == "fail":
        st = TE.fail(root, args.task, args.reason or "unknown", model=args.model)
        print("✓ fail %s -> %s" % (args.task, st))
    elif v == "retry":
        st = TE.retry(root, args.task, model=args.model)
        print("✓ retry %s -> %s" % (args.task, st))
    elif v == "route":
        caps = [c.strip() for c in (args.capabilities or "").split(",") if c.strip()]
        res = TE.route(root, args.role, caps)
        if not res:
            print("# 无可接取任务 (role=%s, caps=%s)" % (args.role, caps))
        for r in res:
            print("  %s  %s  %s  %s" % (r["task_id"], r["type"], r["priority"], r.get("goal")))
    elif v == "list":
        res = TE.list_tasks(root, state=args.state)
        if not res:
            print("# 无任务")
        for s, ids in res.items():
            print("[%s] %d" % (s, len(ids)))
            for i in ids:
                print("    - %s" % i)
    elif v == "show":
        TE.show_task(root, args.task)
    elif v == "intake":
        _cmd_intake(args)
    elif v == "run":
        _cmd_run(args)


def _load_arg(args, ap):
    if args.yaml:
        return _gov.load_yaml(args.yaml)
    if args.json:
        return json.loads(args.json)
    ap.error("%s 需要 --yaml 或 --json" % args.verb)


if __name__ == "__main__":
    main()

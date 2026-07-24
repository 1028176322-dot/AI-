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
import json
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _gov
import task_engine as TE


def main():
    ap = argparse.ArgumentParser(prog="task", description="任务系统操作中心")
    ap.add_argument("verb", choices=["create", "goal", "promote", "claim", "start",
                                     "submit", "review", "complete", "fail", "retry",
                                     "route", "list", "show"])
    ap.add_argument("--project-root", required=True)
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


def _load_arg(args, ap):
    if args.yaml:
        return _gov.load_yaml(args.yaml)
    if args.json:
        return json.loads(args.json)
    ap.error("%s 需要 --yaml 或 --json" % args.verb)


if __name__ == "__main__":
    main()
